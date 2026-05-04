from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pandas as pd
import numpy as np
import joblib
from sklearn.preprocessing import LabelEncoder
import os
import uuid
import datetime
from dotenv import load_dotenv
import boto3

load_dotenv()

app = FastAPI(title="AttritionIQ — HR Attrition Prediction API")

# AWS region
AWS_REGION = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
S3_BUCKET  = os.getenv('S3_BUCKET_NAME')

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
TABLE_NAME = "HR_Attrition_Predictions"

# Initialize S3 client
s3_client = boto3.client('s3', region_name=AWS_REGION)

# ── SNS: High-risk attrition alerts ─────────────────────────
SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')
sns_client = boto3.client('sns', region_name=AWS_REGION) if SNS_TOPIC_ARN else None
SNS_RISK_THRESHOLD = 0.70   # alert when leave prob exceeds this

# ── SageMaker: managed inference endpoint ───────────────────
SAGEMAKER_ENDPOINT = os.getenv('SAGEMAKER_ENDPOINT_NAME')
sm_runtime = boto3.client('sagemaker-runtime', region_name=AWS_REGION) if SAGEMAKER_ENDPOINT else None

print(f"SNS alerts    : {'enabled' if sns_client else 'disabled (SNS_TOPIC_ARN not set)'}")
print(f"SageMaker     : {'endpoint=' + SAGEMAKER_ENDPOINT if sm_runtime else 'disabled (using local model)'}")

def initialize_dynamodb():
    table = dynamodb.Table(TABLE_NAME)
    try:
        table.load()  # Raises ResourceNotFoundException if table doesn't exist
        print(f"DynamoDB table '{TABLE_NAME}' is ready.")
    except dynamodb.meta.client.exceptions.ResourceNotFoundException:
        print(f"Creating DynamoDB table '{TABLE_NAME}'...")
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {'AttributeName': 'prediction_id', 'KeyType': 'HASH'},
                {'AttributeName': 'timestamp', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'prediction_id', 'AttributeType': 'S'},
                {'AttributeName': 'timestamp', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        table.meta.client.get_waiter('table_exists').wait(TableName=TABLE_NAME)
        print("Table created successfully!")
    except Exception as e:
        # Log but don't crash — app can still serve predictions without DynamoDB
        print(f"[WARNING] Could not initialize DynamoDB table: {e}")

initialize_dynamodb()

# Mount static files for UI and Outputs
os.makedirs("static", exist_ok=True)
os.makedirs("outputs", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")

# Load model and feature names
MODEL_DIR = "models"
DATA_PATH = "WA_Fn-UseC_-HR-Employee-Attrition.csv"
os.makedirs(MODEL_DIR, exist_ok=True)

if S3_BUCKET:
    print(f"Syncing artifacts from S3 bucket: {S3_BUCKET}...")
    artifacts_to_download = [
        ("data/WA_Fn-UseC_-HR-Employee-Attrition.csv", DATA_PATH),
        ("models/best_model.pkl", f"{MODEL_DIR}/best_model.pkl"),
        ("models/feature_names.pkl", f"{MODEL_DIR}/feature_names.pkl"),
        ("models/scaler.pkl", f"{MODEL_DIR}/scaler.pkl")
    ]
    for s3_key, local_path in artifacts_to_download:
        try:
            s3_client.download_file(S3_BUCKET, s3_key, local_path)
            print(f"  -> Downloaded {s3_key} from S3.")
        except Exception as e:
            print(f"  ! Could not download {s3_key}: {e}")

model = joblib.load(f"{MODEL_DIR}/best_model.pkl")
feature_names = joblib.load(f"{MODEL_DIR}/feature_names.pkl")

# Re-create Label Encoders (same logic as analysis_pipeline.py)
df = pd.read_csv(DATA_PATH)
DROP_COLS = ['EmployeeCount', 'EmployeeNumber', 'Over18', 'StandardHours']
df.drop(columns=DROP_COLS, inplace=True, errors='ignore')
cat_cols = df.drop(columns=['Attrition'], errors='ignore').select_dtypes(include='object').columns.tolist()

encoders = {}
for col in cat_cols:
    le = LabelEncoder()
    le.fit(df[col])
    encoders[col] = le

class EmployeeData(BaseModel):
    Age: int
    BusinessTravel: str
    DailyRate: int
    Department: str
    DistanceFromHome: int
    Education: int
    EducationField: str
    EnvironmentSatisfaction: int
    Gender: str
    HourlyRate: int
    JobInvolvement: int
    JobLevel: int
    JobRole: str
    JobSatisfaction: int
    MaritalStatus: str
    MonthlyIncome: int
    MonthlyRate: int
    NumCompaniesWorked: int
    OverTime: str
    PercentSalaryHike: int
    PerformanceRating: int
    RelationshipSatisfaction: int
    StockOptionLevel: int
    TotalWorkingYears: int
    TrainingTimesLastYear: int
    WorkLifeBalance: int
    YearsAtCompany: int
    YearsInCurrentRole: int
    YearsSinceLastPromotion: int
    YearsWithCurrManager: int

@app.get("/health")
def health_check():
    """ECS / load balancer health check endpoint."""
    return {"status": "ok", "service": "AttritionIQ"}

@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.get("/charts")
def get_chart_urls():
    """
    Returns presigned S3 URLs (valid 1 hour) for all pipeline-generated charts.
    Falls back to local /outputs paths if S3 is not configured.
    """
    chart_keys = {
        "roc_curves":              "outputs/roc_curves.png",
        "confusion_matrices":      "outputs/confusion_matrices.png",
        "feature_importance":      "outputs/feature_importance.png",
        "shap_summary":            "outputs/shap_summary.png",
        "attrition_distribution":  "outputs/eda/attrition_distribution.png",
        "numeric_boxplots":        "outputs/eda/numeric_boxplots.png",
        "categorical_countplots":  "outputs/eda/categorical_countplots.png",
        "correlation_matrix":      "outputs/eda/correlation_matrix.png",
    }

    urls = {}
    if S3_BUCKET:
        for name, s3_key in chart_keys.items():
            try:
                url = s3_client.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': S3_BUCKET, 'Key': s3_key},
                    ExpiresIn=3600  # 1 hour
                )
                urls[name] = url
            except Exception as e:
                urls[name] = None
                print(f"Could not generate presigned URL for {s3_key}: {e}")
    else:
        # Fallback: local static paths
        local_map = {
            "roc_curves":             "/outputs/roc_curves.png",
            "confusion_matrices":     "/outputs/confusion_matrices.png",
            "feature_importance":     "/outputs/feature_importance.png",
            "shap_summary":           "/outputs/shap_summary.png",
            "attrition_distribution": "/outputs/eda/attrition_distribution.png",
            "numeric_boxplots":       "/outputs/eda/numeric_boxplots.png",
            "categorical_countplots": "/outputs/eda/categorical_countplots.png",
            "correlation_matrix":     "/outputs/eda/correlation_matrix.png",
        }
        urls = local_map

    return {"source": "s3" if S3_BUCKET else "local", "charts": urls}

@app.post("/predict")
def predict(data: EmployeeData):
    try:
        # Convert input to DataFrame
        # Compatibility for both pydantic v1 and v2
        data_dict = data.model_dump() if hasattr(data, 'model_dump') else data.dict()
        input_data = pd.DataFrame([data_dict])
        
        # Encode categorical columns
        for col in cat_cols:
            if col in input_data.columns:
                # Handle unseen labels by falling back to the first class if needed
                # (Assuming UI constraints will prevent unseen labels)
                input_data[col] = encoders[col].transform(input_data[col])
                
        # Ensure correct feature order as expected by the model
        input_df = input_data[feature_names]
        
        # Random Forest in the pipeline was trained on unscaled data (X_train_sm)
        # We only scale if the model is LR or SVM.
        is_tree_based = any(tree in str(type(model)) for tree in ["RandomForest", "GradientBoosting", "DecisionTree"])
        
        if not is_tree_based:
            scaler = joblib.load(f"{MODEL_DIR}/scaler.pkl")
            X = scaler.transform(input_df)
        else:
            X = input_df
            
        # ── Inference: SageMaker endpoint or local model ────────
        if sm_runtime and SAGEMAKER_ENDPOINT:
            import json as _json
            sm_payload = _json.dumps(input_df.values.tolist())
            sm_response = sm_runtime.invoke_endpoint(
                EndpointName = SAGEMAKER_ENDPOINT,
                ContentType  = 'application/json',
                Body         = sm_payload
            )
            sm_result  = _json.loads(sm_response['Body'].read())
            prediction = 1 if sm_result.get('prediction') == 'Leave' else 0
            probability = sm_result.get('leave_probability', 0.5)
        else:
            prediction  = model.predict(X)[0]
            probability = model.predict_proba(X)[0][1]

        prediction_result = "Leave" if prediction == 1 else "Stay"
        leave_prob = float(probability)
        stay_prob  = 1.0 - leave_prob

        # ── SNS: Alert HR if high attrition risk ─────────────────
        if sns_client and SNS_TOPIC_ARN and leave_prob >= SNS_RISK_THRESHOLD:
            try:
                age  = data_dict.get('Age', 'N/A')
                role = data_dict.get('JobRole', 'N/A')
                dept = data_dict.get('Department', 'N/A')
                sns_client.publish(
                    TopicArn = SNS_TOPIC_ARN,
                    Subject  = f'AttritionIQ ⚠️ High Risk Alert — {leave_prob:.0%} Leave Probability',
                    Message  = (
                        f'High attrition risk detected!\n\n'
                        f'  Risk Score  : {leave_prob:.1%} probability of leaving\n'
                        f'  Age         : {age}\n'
                        f'  Role        : {role}\n'
                        f'  Department  : {dept}\n'
                        f'  Overtime    : {data_dict.get("OverTime", "N/A")}\n\n'
                        f'Please review this employee\'s engagement and retention plan.'
                    )
                )
                print(f"SNS alert sent for high-risk prediction ({leave_prob:.1%})")
            except Exception as sns_err:
                print(f"SNS alert failed (non-critical): {sns_err}")
        
        # Save prediction log to DynamoDB
        try:
            table = dynamodb.Table(TABLE_NAME)
            log_item = data_dict.copy()
            log_item['prediction_id'] = str(uuid.uuid4())
            log_item['timestamp'] = datetime.datetime.utcnow().isoformat()
            log_item['predicted_outcome'] = prediction_result
            # DynamoDB requires floats to be Decimal, easiest workaround is string conversion
            log_item['leave_probability'] = str(leave_prob)
            table.put_item(Item=log_item)
        except Exception as db_err:
            print(f"Failed to log to DynamoDB: {db_err}")

        return {
            "prediction": prediction_result,
            "leave_probability": leave_prob,
            "stay_probability": stay_prob
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
