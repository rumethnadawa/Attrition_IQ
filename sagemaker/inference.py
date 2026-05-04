"""
=============================================================
  AttritionIQ — SageMaker Custom Inference Handler
  Handles preprocessing → prediction → postprocessing
=============================================================
"""

import os
import json
import joblib
import numpy as np
import pandas as pd


def model_fn(model_dir):
    """Called once at endpoint startup to load all artifacts."""
    print(f"Loading model artifacts from {model_dir}...")
    artifacts = {
        "model":         joblib.load(os.path.join(model_dir, "model.joblib")),
        "feature_names": joblib.load(os.path.join(model_dir, "feature_names.joblib")),
        "scaler":        joblib.load(os.path.join(model_dir, "scaler.joblib")),
        "encoders":      joblib.load(os.path.join(model_dir, "encoders.joblib")),
    }
    print("Model loaded successfully.")
    return artifacts


def input_fn(request_body, content_type="application/json"):
    """Parse incoming request body into a DataFrame."""
    if content_type == "application/json":
        data = json.loads(request_body)
        if isinstance(data, dict):
            return pd.DataFrame([data])
        elif isinstance(data, list):
            return pd.DataFrame(data)
    raise ValueError(f"Unsupported content type: {content_type}")


def predict_fn(input_df, artifacts):
    """Apply preprocessing and run inference."""
    model         = artifacts["model"]
    feature_names = artifacts["feature_names"]
    encoders      = artifacts["encoders"]

    # Encode categorical columns
    for col, le in encoders.items():
        if col in input_df.columns:
            try:
                input_df[col] = le.transform(input_df[col])
            except ValueError:
                # Unseen label — fallback to 0
                input_df[col] = 0

    # Ensure correct feature order
    input_df = input_df.reindex(columns=feature_names, fill_value=0)

    probabilities = model.predict_proba(input_df)
    predictions   = model.predict(input_df)

    return {
        "predictions":   predictions.tolist(),
        "probabilities": probabilities.tolist(),
    }


def output_fn(prediction, accept="application/json"):
    """Serialize prediction to JSON response."""
    results = []
    for pred, probs in zip(prediction["predictions"], prediction["probabilities"]):
        leave_prob = float(probs[1])
        stay_prob  = float(probs[0])
        results.append({
            "prediction":       "Leave" if pred == 1 else "Stay",
            "leave_probability": leave_prob,
            "stay_probability":  stay_prob,
        })

    if accept == "application/json":
        return json.dumps(results[0] if len(results) == 1 else results), accept
    raise ValueError(f"Unsupported accept type: {accept}")
