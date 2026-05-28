# AttritionIQ 🧠

> **ML-Powered HR Employee Attrition Prediction Platform**  
> Predicts whether an employee is likely to leave — deployed on AWS with a full CI/CD pipeline.

[![CI/CD](https://github.com/rumethnadawa/Attrition_IQ/actions/workflows/deploy.yml/badge.svg?branch=AttritionIQ)](https://github.com/rumethnadawa/Attrition_IQ/actions/workflows/deploy.yml)
![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![AWS](https://img.shields.io/badge/AWS-11%20Services-orange?logo=amazon-aws)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-green?logo=fastapi)
![Docker](https://img.shields.io/badge/Docker-ECS%20Fargate-blue?logo=docker)

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [ML Pipeline](#ml-pipeline)
- [AWS Services](#aws-services)
- [CI/CD Pipeline](#cicd-pipeline)
- [API Reference](#api-reference)
- [Setup & Running](#setup--running)
- [Project Structure](#project-structure)

---

## Overview

AttritionIQ uses the **IBM HR Analytics Employee Attrition dataset** (1,470 employees, 35 features) to predict which employees are likely to leave the company. It compares 5 machine learning models, selects the best by ROC-AUC, and deploys it as a REST API on AWS ECS Fargate with a complete MLOps + CI/CD pipeline.

**Problem:** Employee attrition costs companies 50–200% of an employee's annual salary.  
**Solution:** Predict at-risk employees early so HR can intervene with retention strategies.

---

## Architecture

```
Developer Push (AttritionIQ branch)
         │
         ▼
┌─────────────────── GitHub Actions CI/CD ───────────────────┐
│                                                             │
│  [Test] ──► [Build+Scan+ECR] ──► [SageMaker Train]         │
│                                         │                   │
│                               [ECS Fargate Deploy]          │
│                                         │                   │
│                               [Health Verify] ──► [SNS]    │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────── AWS Cloud ──────────────────────────────────┐
│                                                             │
│  FastAPI App (ECS Fargate)                                  │
│      │                                                      │
│      ├──► Amazon S3          (model artifacts + charts)     │
│      ├──► Amazon DynamoDB    (prediction logs)              │
│      ├──► Amazon SNS         (high-risk HR alerts >70%)     │
│      └──► Amazon SageMaker   (managed inference endpoint)   │
│                                                             │
│  Security & Ops:                                            │
│      ├──► AWS IAM            (scoped roles)                 │
│      ├──► AWS Secrets Manager(secure credentials)           │
│      ├──► Amazon CloudWatch  (logs + dashboards + alarms)   │
│      └──► Amazon ECR         (Docker image registry)        │
└─────────────────────────────────────────────────────────────┘
```

---

## ML Pipeline

The `analysis_pipeline.py` script runs the full end-to-end ML workflow:

### 1. Data Exploration
- Dataset: IBM HR Analytics — 1,470 employees × 35 features
- Target: `Attrition` (Yes/No) — 16% attrition rate (class imbalance)

### 2. Exploratory Data Analysis (EDA)
| Plot | Insight |
|---|---|
| Attrition distribution | 84% Stay vs 16% Leave — significant imbalance |
| Boxplots (Age, Income, Years) | Lower income + younger age → higher attrition |
| Countplots (OverTime, Dept) | OverTime = Yes is the #1 attrition predictor |
| Correlation heatmap | MonthlyIncome ↔ JobLevel strongly correlated |

### 3. Pre-processing
| Step | Method | Reason |
|---|---|---|
| Drop constants | Remove `EmployeeCount`, `Over18`, `StandardHours`, `EmployeeNumber` | No predictive value |
| Encode target | `Yes→1`, `No→0` | Binary classification |
| Label encode | Applied to all categorical columns | Tree models handle ordinal well |
| Train/Test split | 80/20 stratified | Preserves class balance |
| **SMOTE** | Synthetic Minority Oversampling | Fixes class imbalance (training only) |
| StandardScaler | Applied for LR and SVM only | Tree models don't need scaling |

### 4. Model Fitting — 5 Models Compared
| Model | Justification |
|---|---|
| Logistic Regression | Fast baseline; interpretable linear boundary |
| Decision Tree | Fully interpretable; captures non-linear patterns |
| Random Forest | Ensemble; handles high-dimensional data well |
| Gradient Boosting | Sequential boosting; high accuracy on tabular data |
| Support Vector Machine | Effective in high-dimensional feature spaces |

### 5. Model Evaluation
- **Metrics:** Accuracy, ROC-AUC, 5-fold Cross-Validation AUC
- **Plots:** ROC curves (all models), Confusion matrices, Feature importance, SHAP summary
- **Best model selection:** Highest ROC-AUC → hyperparameter tuning with `RandomizedSearchCV`

### 6. Model Deployment
- Best model saved to `models/best_model.pkl` + uploaded to S3
- Served via FastAPI `/predict` endpoint
- SageMaker endpoint available for managed inference

---

## AWS Services

| # | Service | Purpose |
|---|---|---|
| 1 | **Amazon S3** | Model artifacts, dataset, EDA/evaluation charts |
| 2 | **Amazon DynamoDB** | Logs every prediction with timestamp + outcome |
| 3 | **Amazon SNS** | HR alerts (>70% leave probability) + CI/CD notifications |
| 4 | **Amazon ECR** | Docker container image registry |
| 5 | **Amazon ECS (Fargate)** | Serverless container hosting for FastAPI |
| 6 | **Amazon SageMaker** | Managed ML training (Spot instances) + inference endpoint |
| 7 | **AWS Secrets Manager** | Secure storage of all application secrets |
| 8 | **Amazon CloudWatch** | Container logs, metrics dashboard, CPU/memory alarms |
| 9 | **AWS IAM** | Scoped roles for ECS, SageMaker, GitHub Actions |
| 10 | **Amazon EC2 (VPC)** | Default VPC, subnets, security group for ECS task |
| 11 | **AWS STS** | Account ID resolution for ECR/SageMaker ARNs |

---

## CI/CD Pipeline

6-stage automated pipeline triggered on every push to `AttritionIQ` branch:

```
Stage 1 — 🧪 Test
  └─ pytest tests/ (7 tests, AWS mocked)

Stage 2 — 🐳 Build, Scan & Push
  ├─ docker build
  ├─ Trivy vulnerability scan (CRITICAL + HIGH CVEs)
  └─ docker push → Amazon ECR

Stage 3 — 🤖 SageMaker Training
  ├─ Upload dataset to S3
  ├─ Launch ml.m5.xlarge Spot training job
  └─ Quality gate: fail if ROC-AUC < 0.70

Stage 4 — 🚀 Deploy to ECS Fargate
  └─ Zero-downtime rolling update

Stage 5 — ✅ Verify Deployment
  └─ Poll /health endpoint for up to 3 minutes

Stage 6 — 📣 SNS Notification
  └─ Email: ✅ success or ❌ failure + link to logs
```

---

## API Reference

### `GET /health`
Health check endpoint (used by ECS and CI/CD).
```json
{ "status": "ok", "service": "AttritionIQ" }
```

### `POST /predict`
Predict whether an employee will leave.

**Request body** (all fields required):
```json
{
  "Age": 28,
  "BusinessTravel": "Travel_Frequently",
  "Department": "Sales",
  "DistanceFromHome": 20,
  "OverTime": "Yes",
  "MonthlyIncome": 2500,
  "JobSatisfaction": 1,
  "MaritalStatus": "Single",
  ...
}
```

**Response:**
```json
{
  "prediction": "Leave",
  "leave_probability": 0.82,
  "stay_probability": 0.18
}
```

### `GET /charts`
Returns URLs to all EDA and evaluation charts stored in S3.

**Interactive Docs:** `http://<your-ecs-ip>:8000/docs`

---

## Setup & Running

### Prerequisites
- Python 3.11+
- AWS CLI configured (`aws configure`)
- Docker Desktop

### 1. Clone & Install
```bash
git clone https://github.com/rumethnadawa/Attrition_IQ.git
cd Attrition_IQ
git checkout AttritionIQ
pip install -r requirements.txt
```

### 2. Configure AWS Infrastructure (run once)
```bash
# Create S3 bucket
python setup_s3.py

# Create DynamoDB table
python setup_dynamo.py

# Create SNS topic + subscribe your email
python setup_sns.py --email your@email.com

# Store secrets securely
python setup_secrets.py

# Set up CloudWatch dashboard + alarms
python setup_cloudwatch.py

# Set AWS monthly budget alert ($20)
python setup_budget.py --email your@email.com --limit 20
```

### 3. Run the ML Pipeline
```bash
python analysis_pipeline.py
# Outputs: models/, outputs/, outputs/eda/
```

### 4. Run the API Locally
```bash
uvicorn app:app --reload --port 8000
# Open: http://localhost:8000/docs
```

### 5. Deploy to AWS
```bash
# Option A: Run the deployment script manually
python deploy_ecs.py

# Option B: Push to AttritionIQ branch (triggers GitHub Actions CI/CD)
git push origin AttritionIQ
```

### 6. Set Up Keyless CI/CD (OIDC — Recommended)
```bash
python setup_oidc.py --repo rumethnadawa/Attrition_IQ
# Then add AWS_ROLE_ARN to GitHub Secrets
# Then remove AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
```

### GitHub Secrets Required

| Secret | Description |
|---|---|
| `AWS_ROLE_ARN` | IAM role ARN for OIDC auth (preferred) |
| `AWS_ACCESS_KEY_ID` | Fallback access key (rotate + migrate to OIDC) |
| `AWS_SECRET_ACCESS_KEY` | Fallback secret key |
| `S3_BUCKET` | S3 bucket name |
| `SNS_TOPIC_ARN` | SNS topic ARN for notifications |

---

## Project Structure

```
AttritionIQ/
├── analysis_pipeline.py      # Full ML pipeline (EDA → train → evaluate → S3)
├── app.py                    # FastAPI deployment API
├── sagemaker_pipeline.py     # SageMaker training + endpoint orchestrator
├── deploy_ecs.py             # ECS Fargate provisioning script
│
├── setup_s3.py               # Create S3 bucket
├── setup_dynamo.py           # Create DynamoDB table
├── setup_sns.py              # Create SNS topic + email subscription
├── setup_secrets.py          # Push secrets to AWS Secrets Manager
├── setup_cloudwatch.py       # Create CloudWatch dashboard + alarms
├── setup_budget.py           # Create AWS monthly budget alert
├── setup_oidc.py             # Set up GitHub Actions OIDC (keyless auth)
│
├── sagemaker/
│   ├── train.py              # SageMaker training script
│   ├── inference.py          # SageMaker inference handler
│   └── requirements.txt      # SageMaker container dependencies
│
├── tests/
│   └── test_app.py           # 7 pytest tests (health, charts, predict)
│
├── .github/
│   ├── workflows/deploy.yml          # 6-stage CI/CD pipeline
│   └── scripts/verify_deployment.py # Post-deploy health check
│
├── Dockerfile                # python:3.11-slim container
├── requirements.txt          # All Python dependencies (pinned)
├── .gitignore                # .env, models/, outputs/, *.pem excluded
└── WA_Fn-UseC_-HR-Employee-Attrition.csv  # IBM HR dataset
```

---

## 🔐 Security Notes

- `.env` is **never committed** (in `.gitignore`)
- All secrets stored in **AWS Secrets Manager**
- Migrate to **OIDC** (`setup_oidc.py`) to eliminate long-term AWS keys entirely
- ECR images scanned for CVEs on every push (Trivy)
- IAM roles follow least-privilege principle

---

*Built for CS4042 Machine Learning — Semester 7 | AttritionIQ by Rumeth Nadawa*
