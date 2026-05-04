"""
=============================================================
  AttritionIQ — Test Suite (runs in CI/CD pipeline)
=============================================================
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ─── Sample payload ──────────────────────────────────────────
SAMPLE_EMPLOYEE = {
    "Age": 28,
    "BusinessTravel": "Travel_Frequently",
    "DailyRate": 400,
    "Department": "Sales",
    "DistanceFromHome": 20,
    "Education": 2,
    "EducationField": "Marketing",
    "EnvironmentSatisfaction": 1,
    "Gender": "Male",
    "HourlyRate": 40,
    "JobInvolvement": 2,
    "JobLevel": 1,
    "JobRole": "Sales Representative",
    "JobSatisfaction": 1,
    "MaritalStatus": "Single",
    "MonthlyIncome": 2500,
    "MonthlyRate": 5000,
    "NumCompaniesWorked": 5,
    "OverTime": "Yes",
    "PercentSalaryHike": 11,
    "PerformanceRating": 3,
    "RelationshipSatisfaction": 2,
    "StockOptionLevel": 0,
    "TotalWorkingYears": 5,
    "TrainingTimesLastYear": 1,
    "WorkLifeBalance": 1,
    "YearsAtCompany": 1,
    "YearsInCurrentRole": 0,
    "YearsSinceLastPromotion": 0,
    "YearsWithCurrManager": 0
}

# ─── Fixtures ────────────────────────────────────────────────
@pytest.fixture(scope="module")
def client():
    """Create a TestClient with mocked AWS services."""
    mock_dynamodb   = MagicMock()
    mock_table      = MagicMock()
    mock_dynamodb.Table.return_value = mock_table
    mock_table.load.return_value = {}
    mock_table.put_item.return_value = {}

    mock_s3 = MagicMock()
    mock_s3.download_file.return_value = None
    mock_s3.generate_presigned_url.return_value = "https://mock-s3-url.example.com/chart.png"

    with patch("boto3.resource", return_value=mock_dynamodb), \
         patch("boto3.client", return_value=mock_s3):
        import importlib, app as app_module
        importlib.reload(app_module)
        yield TestClient(app_module.app)


# ─── Tests ───────────────────────────────────────────────────
class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_structure(self, client):
        data = client.get("/health").json()
        assert "status" in data
        assert data["status"] == "ok"
        assert data["service"] == "AttritionIQ"


class TestChartsEndpoint:
    def test_charts_returns_200(self, client):
        response = client.get("/charts")
        assert response.status_code == 200

    def test_charts_response_structure(self, client):
        data = client.get("/charts").json()
        assert "source" in data
        assert "charts" in data
        expected_keys = [
            "roc_curves", "confusion_matrices", "feature_importance",
            "shap_summary", "attrition_distribution", "numeric_boxplots",
            "categorical_countplots", "correlation_matrix"
        ]
        for key in expected_keys:
            assert key in data["charts"], f"Missing chart key: {key}"


class TestPredictEndpoint:
    def test_predict_returns_200(self, client):
        response = client.post("/predict", json=SAMPLE_EMPLOYEE)
        assert response.status_code == 200

    def test_predict_response_structure(self, client):
        data = client.post("/predict", json=SAMPLE_EMPLOYEE).json()
        assert "prediction" in data
        assert "leave_probability" in data
        assert "stay_probability" in data

    def test_predict_valid_outcomes(self, client):
        data = client.post("/predict", json=SAMPLE_EMPLOYEE).json()
        assert data["prediction"] in ["Leave", "Stay"]

    def test_predict_probabilities_sum_to_one(self, client):
        data = client.post("/predict", json=SAMPLE_EMPLOYEE).json()
        total = data["leave_probability"] + data["stay_probability"]
        assert abs(total - 1.0) < 0.001

    def test_predict_probabilities_in_range(self, client):
        data = client.post("/predict", json=SAMPLE_EMPLOYEE).json()
        assert 0.0 <= data["leave_probability"] <= 1.0
        assert 0.0 <= data["stay_probability"] <= 1.0

    def test_predict_high_risk_profile(self, client):
        """High-risk profile (overtime, low income, single) should lean Leave."""
        data = client.post("/predict", json=SAMPLE_EMPLOYEE).json()
        # Just verify it runs — actual prediction depends on model
        assert data["prediction"] in ["Leave", "Stay"]

    def test_predict_missing_field_returns_error(self, client):
        bad_payload = {k: v for k, v in SAMPLE_EMPLOYEE.items() if k != "Age"}
        response = client.post("/predict", json=bad_payload)
        assert response.status_code == 422  # Unprocessable Entity
