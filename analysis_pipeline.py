"""
=============================================================
  IBM HR Analytics - Employee Attrition Prediction
  Full ML Training Pipeline with EDA
=============================================================
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')   # non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import joblib
import os
import shap
import boto3
from dotenv import load_dotenv

load_dotenv()

from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold, RandomizedSearchCV
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.metrics import (
    accuracy_score, classification_report, confusion_matrix,
    roc_auc_score, roc_curve, ConfusionMatrixDisplay
)
from imblearn.over_sampling import SMOTE

warnings.filterwarnings('ignore')

# *********************************************
#  PATHS
# *********************************************
DATA_PATH    = "WA_Fn-UseC_-HR-Employee-Attrition.csv"
OUTPUT_DIR   = "outputs"
MODEL_DIR    = "models"
EDA_DIR      = "outputs/eda"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(EDA_DIR, exist_ok=True)

print("=" * 60)
print("  IBM HR Analytics – Attrition Prediction Pipeline")
print("=" * 60)

# *********************************************
#  STEP 1 - LOAD DATA
# *********************************************
print("\n[1/6] Loading dataset...")
df = pd.read_csv(DATA_PATH)

print(f"  -> Shape        : {df.shape}")
print(f"  -> Columns      : {list(df.columns)}")
print(f"  -> Missing vals : {df.isnull().sum().sum()}")
print(f"\n  Target distribution (Attrition):")
print(df['Attrition'].value_counts())
print(f"\n  Class imbalance ratio:")
print(df['Attrition'].value_counts(normalize=True).round(3))

# *********************************************
#  STEP 2 - EXPLORATORY DATA ANALYSIS (EDA)
# *********************************************
print("\n[2/6] Performing Exploratory Data Analysis...")

# 2a. Target Distribution Plot
plt.figure(figsize=(6, 4))
sns.countplot(x='Attrition', data=df, palette='Set2')
plt.title('Attrition Distribution')
plt.savefig(f"{EDA_DIR}/attrition_distribution.png", dpi=100)
plt.close()

# 2b. Numeric Features Boxplots vs Attrition
numeric_cols = ['Age', 'MonthlyIncome', 'YearsAtCompany', 'DistanceFromHome']
fig, axes = plt.subplots(2, 2, figsize=(12, 10))
for idx, col in enumerate(numeric_cols):
    row, col_idx = idx // 2, idx % 2
    sns.boxplot(x='Attrition', y=col, data=df, ax=axes[row, col_idx], palette='Set2')
    axes[row, col_idx].set_title(f'{col} vs Attrition')
plt.tight_layout()
plt.savefig(f"{EDA_DIR}/numeric_boxplots.png", dpi=100)
plt.close()

# 2c. Categorical Features vs Attrition
cat_cols_eda = ['Department', 'Gender', 'MaritalStatus', 'OverTime']
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
for idx, col in enumerate(cat_cols_eda):
    row, col_idx = idx // 2, idx % 2
    sns.countplot(x=col, hue='Attrition', data=df, ax=axes[row, col_idx], palette='Set2')
    axes[row, col_idx].set_title(f'{col} by Attrition')
    axes[row, col_idx].tick_params(axis='x', rotation=15)
plt.tight_layout()
plt.savefig(f"{EDA_DIR}/categorical_countplots.png", dpi=100)
plt.close()

# 2d. Correlation Matrix (Numeric only)
# Encode Attrition temporarily for correlation
df_corr = df.copy()
df_corr['Attrition'] = df_corr['Attrition'].map({'Yes': 1, 'No': 0})
num_df = df_corr.select_dtypes(include=[np.number])
# Drop constant columns first
num_df.drop(columns=['EmployeeCount', 'StandardHours'], errors='ignore', inplace=True)
corr = num_df.corr()
plt.figure(figsize=(14, 12))
sns.heatmap(corr, cmap='coolwarm', annot=False, fmt=".2f")
plt.title('Correlation Matrix')
plt.tight_layout()
plt.savefig(f"{EDA_DIR}/correlation_matrix.png", dpi=150)
plt.close()
print("  -> EDA plots saved to outputs/eda/")

# *********************************************
#  STEP 3 - PRE-PROCESSING
# *********************************************
print("\n[3/6] Pre-processing...")

# 3a. Drop useless constant columns
DROP_COLS = ['EmployeeCount', 'EmployeeNumber', 'Over18', 'StandardHours']
df.drop(columns=DROP_COLS, inplace=True, errors='ignore')
print(f"  -> Dropped constant columns: {DROP_COLS}")

# 3b. Encode target: Yes -> 1, No -> 0
df['Attrition'] = df['Attrition'].map({'Yes': 1, 'No': 0})

# 3c. Identify categorical columns
cat_cols = df.select_dtypes(include='object').columns.tolist()
print(f"  -> Categorical columns to encode: {cat_cols}")

# 3d. Label encode all categoricals
le = LabelEncoder()
for col in cat_cols:
    df[col] = le.fit_transform(df[col])
print("  -> Label encoding applied")

# 3e. Feature / Target split
X = df.drop('Attrition', axis=1)
y = df['Attrition']

# 3f. Train / Test split (80/20, stratified)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)
print(f"  -> Train set: {X_train.shape} | Test set: {X_test.shape}")

# 3g. Handle class imbalance with SMOTE (on training data only)
smote = SMOTE(random_state=42)
X_train_sm, y_train_sm = smote.fit_resample(X_train, y_train)
print(f"  -> After SMOTE -> Train: {X_train_sm.shape} | Distribution: {pd.Series(y_train_sm).value_counts().to_dict()}")

# 3h. Feature scaling (needed for LR and SVM)
scaler = StandardScaler()
X_train_sc = scaler.fit_transform(X_train_sm)
X_test_sc  = scaler.transform(X_test)
print("  -> StandardScaler applied")

# Save scaler for deployment
joblib.dump(scaler, f"{MODEL_DIR}/scaler.pkl")

# *********************************************
#  STEP 4 - MODEL TRAINING
# *********************************************
print("\n[4/6] Training models...")

models = {
    "Logistic Regression":       LogisticRegression(max_iter=1000, class_weight='balanced', random_state=42),
    "Decision Tree":             DecisionTreeClassifier(max_depth=6, class_weight='balanced', random_state=42),
    "Random Forest":             RandomForestClassifier(n_estimators=200, class_weight='balanced', random_state=42),
    "Gradient Boosting":         GradientBoostingClassifier(n_estimators=200, learning_rate=0.05, max_depth=4, random_state=42),
    "Support Vector Machine":    SVC(kernel='rbf', probability=True, class_weight='balanced', random_state=42),
}

cv      = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
results = {}

for name, model in models.items():
    print(f"\n  - Training: {name}")

    # Use scaled data for LR and SVM, raw SMOTE data for tree-based
    if name in ["Logistic Regression", "Support Vector Machine"]:
        X_tr, X_te = X_train_sc, X_test_sc
    else:
        X_tr, X_te = X_train_sm, X_test

    model.fit(X_tr, y_train_sm)

    y_pred      = model.predict(X_te)
    y_prob      = model.predict_proba(X_te)[:, 1]

    acc         = accuracy_score(y_test, y_pred)
    roc_auc     = roc_auc_score(y_test, y_prob)
    cv_scores   = cross_val_score(model, X_tr, y_train_sm, cv=cv, scoring='roc_auc')

    results[name] = {
        "model":        model,
        "y_pred":       y_pred,
        "y_prob":       y_prob,
        "accuracy":     acc,
        "roc_auc":      roc_auc,
        "cv_mean":      cv_scores.mean(),
        "cv_std":       cv_scores.std(),
        "X_te":         X_te,
    }

    print(f"    Accuracy : {acc:.4f}")
    print(f"    ROC-AUC  : {roc_auc:.4f}")
    print(f"    CV AUC   : {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

# *********************************************
#  STEP 5 - EVALUATION & PLOTS
# *********************************************
print("\n[5/6] Evaluating & generating plots...")

# Comparison Table
summary = pd.DataFrame([
    {
        "Model":        name,
        "Accuracy":     f"{r['accuracy']:.4f}",
        "ROC-AUC":      f"{r['roc_auc']:.4f}",
        "CV AUC Mean":  f"{r['cv_mean']:.4f}",
    }
    for name, r in results.items()
])
print("\n  -- Model Comparison ----------------------------------")
print(summary.to_string(index=False))
summary.to_csv(f"{OUTPUT_DIR}/model_comparison.csv", index=False)

# ROC Curves
fig, ax = plt.subplots(figsize=(9, 6))
colors = ['#4361ee', '#3a0ca3', '#7209b7', '#f72585', '#4cc9f0']
for (name, r), color in zip(results.items(), colors):
    fpr, tpr, _ = roc_curve(y_test, r['y_prob'])
    ax.plot(fpr, tpr, label=f"{name} (AUC={r['roc_auc']:.3f})", color=color, lw=2)
ax.plot([0, 1], [0, 1], 'k--', lw=1)
ax.set_xlabel("False Positive Rate", fontsize=12)
ax.set_ylabel("True Positive Rate", fontsize=12)
ax.set_title("ROC Curves – All Models", fontsize=14, fontweight='bold')
ax.legend(fontsize=9)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/roc_curves.png", dpi=150)
plt.close()

# Confusion Matrices
fig, axes = plt.subplots(2, 3, figsize=(16, 10))
axes = axes.flatten()
for idx, (name, r) in enumerate(results.items()):
    cm = confusion_matrix(y_test, r['y_pred'])
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=['Stay', 'Leave'])
    disp.plot(ax=axes[idx], colorbar=False, cmap='Blues')
    axes[idx].set_title(name, fontsize=10, fontweight='bold')
axes[-1].set_visible(False)
plt.suptitle("Confusion Matrices – All Models", fontsize=14, fontweight='bold', y=1.01)
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/confusion_matrices.png", dpi=150, bbox_inches='tight')
plt.close()

# Feature Importance (Random Forest)
rf_model    = results["Random Forest"]["model"]
feat_imp    = pd.Series(rf_model.feature_importances_, index=X.columns).sort_values(ascending=False)
top_features= feat_imp.head(15)

fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.barh(top_features.index[::-1], top_features.values[::-1],
               color=sns.color_palette("viridis", 15))
ax.set_xlabel("Importance Score", fontsize=12)
ax.set_title("Top 15 Feature Importances (Random Forest)", fontsize=14, fontweight='bold')
ax.grid(axis='x', alpha=0.3)
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/feature_importance.png", dpi=150)
plt.close()

# Classification Report (best model)
best_name = max(results, key=lambda n: results[n]['roc_auc'])
best_r    = results[best_name]
print(f"\n  -- Best Model: {best_name} --------------------------")
print(classification_report(y_test, best_r['y_pred'], target_names=['Stay', 'Leave']))

# *********************************************
#  STEP 6 - HYPERPARAMETER TUNING & SHAP
# *********************************************
print(f"\n[6/7] Hyperparameter Tuning on Best Model ({best_name})...")

param_grid = {}
if best_name == "Random Forest":
    param_grid = {
        'n_estimators': [100, 200, 300],
        'max_depth': [None, 10, 20, 30],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf': [1, 2, 4]
    }
elif best_name == "Gradient Boosting":
    param_grid = {
        'n_estimators': [100, 200],
        'learning_rate': [0.01, 0.05, 0.1],
        'max_depth': [3, 4, 5]
    }
elif best_name == "Decision Tree":
    param_grid = {
        'max_depth': [4, 6, 8, 10],
        'min_samples_split': [2, 5, 10]
    }

if param_grid:
    print(f"  -> Tuning {best_name}...")
    X_tr = X_train_sm if best_name not in ["Logistic Regression", "Support Vector Machine"] else X_train_sc
    random_search = RandomizedSearchCV(best_r['model'], param_distributions=param_grid, 
                                       n_iter=5, cv=3, scoring='roc_auc', random_state=42, n_jobs=-1)
    random_search.fit(X_tr, y_train_sm)
    
    final_model = random_search.best_estimator_
    print(f"  -> Best Hyperparameters: {random_search.best_params_}")
    
    # Eval tuned model
    X_te = X_test if best_name not in ["Logistic Regression", "Support Vector Machine"] else X_test_sc
    tuned_prob = final_model.predict_proba(X_te)[:, 1]
    print(f"  -> Tuned ROC-AUC: {roc_auc_score(y_test, tuned_prob):.4f}")
else:
    print("  -> Using base model parameters")
    final_model = best_r['model']
    X_te = X_test if best_name not in ["Logistic Regression", "Support Vector Machine"] else X_test_sc

# SHAP Explainability
print(f"\n  -> Generating SHAP values for interpretability...")
if best_name in ["Random Forest", "Decision Tree", "Gradient Boosting"]:
    # SHAP provides exact interpretability for model predictions
    explainer = shap.TreeExplainer(final_model)
    shap_values = explainer.shap_values(X_te)
    plt.figure(figsize=(10, 8))
    # SHAP sometimes returns a list for classification
    if isinstance(shap_values, list):
        shap.summary_plot(shap_values[1], X_te, feature_names=X.columns, show=False)
    else:
        shap.summary_plot(shap_values, X_te, feature_names=X.columns, show=False)
    plt.savefig(f"{OUTPUT_DIR}/shap_summary.png", dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  -> SHAP summary plot saved to {OUTPUT_DIR}/shap_summary.png")
else:
    print("  -> SHAP specifically configured for tree-based models in this script.")

# *********************************************
#  STEP 7 - SAVE FINAL MODEL (DEPLOYMENT)
# *********************************************
print(f"\n[7/7] Saving final optimized model: {best_name}...")
joblib.dump(final_model, f"{MODEL_DIR}/best_model.pkl")
joblib.dump(list(X.columns),  f"{MODEL_DIR}/feature_names.pkl")
print(f"  -> Model saved  -> models/best_model.pkl")

# *********************************************
#  STEP 8 - UPLOAD ARTIFACTS TO S3
# *********************************************
print("\n[8/8] Uploading artifacts to Amazon S3...")
s3_bucket = os.getenv("S3_BUCKET_NAME")
if s3_bucket:
    s3 = boto3.client('s3')
    
    # Files to upload (local_path, s3_key)
    artifacts = [
        (DATA_PATH, "data/WA_Fn-UseC_-HR-Employee-Attrition.csv"),
        (f"{MODEL_DIR}/best_model.pkl", "models/best_model.pkl"),
        (f"{MODEL_DIR}/feature_names.pkl", "models/feature_names.pkl"),
    ]
    
    # Also upload scaler if it exists
    if os.path.exists(f"{MODEL_DIR}/scaler.pkl"):
        artifacts.append((f"{MODEL_DIR}/scaler.pkl", "models/scaler.pkl"))
        
    for local_path, s3_key in artifacts:
        print(f"  -> Uploading {local_path} to s3://{s3_bucket}/{s3_key}")
        try:
            s3.upload_file(local_path, s3_bucket, s3_key)
        except Exception as e:
            print(f"     ! Failed to upload {local_path}: {e}")
            
    print("  -> S3 Upload complete!")
else:
    print("  -> S3_BUCKET_NAME not found in .env, skipping upload.")

print("\n" + "=" * 60)
print("  ✅ Pipeline complete!")
print("=" * 60)
