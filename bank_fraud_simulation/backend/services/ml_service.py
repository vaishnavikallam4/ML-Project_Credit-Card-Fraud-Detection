import os
from pathlib import Path

import joblib
import pandas as pd

MODEL_PATH = Path(__file__).resolve().parents[1] / "model" / "fraud_model.joblib"
PREPROCESSOR_PATH = Path(__file__).resolve().parents[1] / "model" / "fraud_preprocessor.joblib"


def _feature_columns():
    return [
        "amount",
        "transaction_hour",
        "is_weekend",
        "merchant_category",
        "transaction_type",
        "country",
        "is_international",
        "customer_avg_amount",
        "recent_txn_count",
        "device_risk",
    ]


def _build_feature_row(transaction_payload: dict):
    merchant_category = str(transaction_payload.get("merchant_category") or "general").strip().lower()
    transaction_type = str(transaction_payload.get("transaction_type") or "online_purchase").strip().lower()
    country = str(transaction_payload.get("country") or "IN").strip().upper()
    amount = float(transaction_payload.get("amount", 0.0) or 0.0)
    transaction_hour = int(transaction_payload.get("transaction_hour", 12))
    is_weekend = int(bool(transaction_payload.get("is_weekend", transaction_hour >= 18)))
    is_international = int(bool(transaction_payload.get("is_international", country not in {"IN", "INDIA"})))
    customer_avg_amount = float(transaction_payload.get("customer_avg_amount", max(amount, 5000.0)))
    recent_txn_count = int(transaction_payload.get("recent_txn_count", 0))
    device_risk = float(transaction_payload.get("device_risk", 0.0))

    return {
        "amount": amount,
        "transaction_hour": transaction_hour,
        "is_weekend": is_weekend,
        "merchant_category": merchant_category,
        "transaction_type": transaction_type,
        "country": country,
        "is_international": is_international,
        "customer_avg_amount": customer_avg_amount,
        "recent_txn_count": recent_txn_count,
        "device_risk": device_risk,
    }


def predict_fraud(transaction_payload: dict):
    if not MODEL_PATH.exists() or not PREPROCESSOR_PATH.exists():
        raise FileNotFoundError("Model files are not trained yet. Run the training pipeline first.")

    model = joblib.load(MODEL_PATH)
    preprocessor = joblib.load(PREPROCESSOR_PATH)

    row = _build_feature_row(transaction_payload)
    df = pd.DataFrame([row])

    transformed = preprocessor.transform(df)
    probability = model.predict_proba(transformed)[0][1]
    prediction = "FRAUDULENT" if probability >= 0.5 else "LEGITIMATE"

    return {
        "fraud_probability": float(probability),
        "prediction": prediction,
        "risk_level": "HIGH" if probability >= 0.7 else "MEDIUM" if probability >= 0.4 else "LOW",
    }
