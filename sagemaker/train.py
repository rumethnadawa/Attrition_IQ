"""
=============================================================
  AttritionIQ — SageMaker Training Script
  Compatible with SageMaker SKLearn container
=============================================================
"""

import argparse
import os
import pandas as pd
import numpy as np
import joblib
import json

from sklearn.model_selection import train_test_split, RandomizedSearchCV, StratifiedKFold
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, classification_report
from imblearn.over_sampling import SMOTE


def model_fn(model_dir):
    """Load model — called by SageMaker endpoint at startup."""
    model        = joblib.load(os.path.join(model_dir, "model.joblib"))
    feature_names = joblib.load(os.path.join(model_dir, "feature_names.joblib"))
    scaler       = joblib.load(os.path.join(model_dir, "scaler.joblib"))
    encoders     = joblib.load(os.path.join(model_dir, "encoders.joblib"))
    return {"model": model, "feature_names": feature_names,
            "scaler": scaler, "encoders": encoders}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # Hyperparameters passed by SageMaker / CI pipeline
    parser.add_argument("--n-estimators",      type=int,   default=300)
    parser.add_argument("--max-depth",         type=int,   default=30)
    parser.add_argument("--min-samples-split", type=int,   default=2)
    parser.add_argument("--min-samples-leaf",  type=int,   default=1)
    parser.add_argument("--test-size",         type=float, default=0.2)
    parser.add_argument("--random-state",      type=int,   default=42)
    parser.add_argument("--roc-auc-threshold", type=float, default=0.70,
                        help="Minimum ROC-AUC to accept model")

    # SageMaker injects these automatically
    parser.add_argument("--model-dir", type=str,
                        default=os.environ.get("SM_MODEL_DIR", "/opt/ml/model"))
    parser.add_argument("--train",     type=str,
                        default=os.environ.get("SM_CHANNEL_TRAINING",
                                               "/opt/ml/input/data/training"))
    parser.add_argument("--output-data-dir", type=str,
                        default=os.environ.get("SM_OUTPUT_DATA_DIR",
                                               "/opt/ml/output/data"))
    # Passed as hyperparameter by sagemaker_pipeline.py
    parser.add_argument("--s3-bucket-name", type=str, default="")
    args = parser.parse_args()

    print("=" * 60)
    print("  AttritionIQ — SageMaker Training")
    print("=" * 60)
    print(f"  n_estimators      : {args.n_estimators}")
    print(f"  max_depth         : {args.max_depth}")
    print(f"  roc_auc_threshold : {args.roc_auc_threshold}")

    # ─── Load Data ──────────────────────────────────────────
    data_file = os.path.join(args.train, "WA_Fn-UseC_-HR-Employee-Attrition.csv")
    print(f"\n[1/5] Loading data from {data_file}...")
    df = pd.read_csv(data_file)
    print(f"  -> Shape: {df.shape}")

    # ─── Preprocessing ──────────────────────────────────────
    print("\n[2/5] Preprocessing...")
    DROP_COLS = ["EmployeeCount", "EmployeeNumber", "Over18", "StandardHours"]
    df.drop(columns=DROP_COLS, inplace=True, errors="ignore")
    df["Attrition"] = df["Attrition"].map({"Yes": 1, "No": 0})

    cat_cols = df.select_dtypes(include="object").columns.tolist()
    encoders = {}
    for col in cat_cols:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col])
        encoders[col] = le

    X = df.drop("Attrition", axis=1)
    y = df["Attrition"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.random_state, stratify=y
    )

    smote = SMOTE(random_state=args.random_state)
    X_train_sm, y_train_sm = smote.fit_resample(X_train, y_train)

    scaler = StandardScaler()
    scaler.fit(X_train_sm)     # fit only, used for LR/SVM fallback
    print(f"  -> Train: {X_train_sm.shape} | Test: {X_test.shape}")

    # ─── Train ──────────────────────────────────────────────
    print("\n[3/5] Training Random Forest...")
    model = RandomForestClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        min_samples_split=args.min_samples_split,
        min_samples_leaf=args.min_samples_leaf,
        class_weight="balanced",
        random_state=args.random_state,
        n_jobs=-1
    )
    model.fit(X_train_sm, y_train_sm)

    # ─── Evaluate ───────────────────────────────────────────
    print("\n[4/5] Evaluating...")
    y_prob = model.predict_proba(X_test)[:, 1]
    y_pred = model.predict(X_test)
    roc_auc = roc_auc_score(y_test, y_prob)
    print(f"  -> ROC-AUC : {roc_auc:.4f}")
    print(classification_report(y_test, y_pred, target_names=["Stay", "Leave"]))

    # Model quality gate — fail the job if below threshold
    if roc_auc < args.roc_auc_threshold:
        raise ValueError(
            f"Model ROC-AUC {roc_auc:.4f} is below threshold {args.roc_auc_threshold}. "
            f"Rejecting model — pipeline will NOT deploy."
        )

    # ─── Save Artifacts ─────────────────────────────────────
    print(f"\n[5/6] Saving artifacts to {args.model_dir}...")
    os.makedirs(args.model_dir, exist_ok=True)
    os.makedirs(args.output_data_dir, exist_ok=True)

    joblib.dump(model,             os.path.join(args.model_dir, "model.joblib"))
    joblib.dump(list(X.columns),  os.path.join(args.model_dir, "feature_names.joblib"))
    joblib.dump(scaler,            os.path.join(args.model_dir, "scaler.joblib"))
    joblib.dump(encoders,          os.path.join(args.model_dir, "encoders.joblib"))

    # Save metrics for the CI pipeline to read
    metrics = {"roc_auc": round(roc_auc, 4), "n_estimators": args.n_estimators}
    with open(os.path.join(args.output_data_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f)

    print("  -> All artifacts saved!")

    # ─── Register in SageMaker Model Registry ───────────────
    print(f"\n[6/6] Registering model in SageMaker Model Registry...")
    s3_bucket = args.s3_bucket_name or os.environ.get("S3_BUCKET_NAME", "")
    model_package_group = "AttritionIQ-Models"

    # Determine the model S3 URI (set by SageMaker after training)
    output_path = os.environ.get("SM_OUTPUT_DATA_DIR", args.output_data_dir)
    model_s3_uri = os.environ.get(
        "SM_MODEL_DIR",
        f"s3://{s3_bucket}/sagemaker/output/model.tar.gz" if s3_bucket else ""
    )

    if model_s3_uri and s3_bucket:
        try:
            import boto3
            sm_client = boto3.client("sagemaker")
            sm_client.create_model_package(
                ModelPackageGroupName=model_package_group,
                ModelPackageDescription=f"ROC-AUC: {roc_auc:.4f} | n_estimators: {args.n_estimators}",
                InferenceSpecification={
                    "Containers": [
                        {
                            "Image": os.environ.get("SAGEMAKER_CONTAINER_IMAGE", ""),
                            "ModelDataUrl": model_s3_uri,
                            "Framework": "SKLEARN",
                            "FrameworkVersion": "1.2-1",
                        }
                    ],
                    "SupportedContentTypes":  ["application/json"],
                    "SupportedResponseMIMETypes": ["application/json"],
                },
                ModelApprovalStatus="PendingManualApproval",  # Requires human sign-off
                ModelMetrics={
                    "ModelQuality": {
                        "Statistics": {
                            "ContentType": "application/json",
                            "S3Uri": f"s3://{s3_bucket}/sagemaker/metrics/metrics.json",
                        }
                    }
                },
            )
            print(f"  -> Registered in Model Registry: {model_package_group}")
            print(f"     Status: PendingManualApproval")
            print(f"     ROC-AUC: {roc_auc:.4f}")
            print(f"     Approve at: SageMaker Studio -> Model Registry -> {model_package_group}")
        except Exception as reg_err:
            # Non-fatal — training still succeeded
            print(f"  [WARN] Model Registry registration failed (non-critical): {reg_err}")
    else:
        print("  [SKIP] Model Registry: S3_BUCKET_NAME not available in environment.")

    print("=" * 60)
    print("  [DONE] SageMaker training complete!")
    print("=" * 60)
