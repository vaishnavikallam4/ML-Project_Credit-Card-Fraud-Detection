from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

MODEL_DIR = Path(__file__).resolve().parents[1] / "model"
MODEL_DIR.mkdir(exist_ok=True, parents=True)


def build_mock_dataset():
    rows = []
    merchants = ["amazon", "flipkart", "luxury", "travel", "casino", "gift", "food", "general"]
    countries = ["IN", "US", "UAE", "SG", "AU", "GB"]
    transaction_types = ["online_purchase", "card_present", "cash_withdrawal", "international_transfer", "subscription"]

    for i in range(2000):
        amount = 100 + (i * 7.3) % 100000
        merchant = merchants[i % len(merchants)]
        country = countries[i % len(countries)]
        tx_type = transaction_types[i % len(transaction_types)]
        hour = (i * 17) % 24
        is_weekend = 1 if i % 7 in {5, 6} else 0
        customer_avg_amount = 5000 + (i * 9) % 25000
        recent_txn_count = (i * 3) % 12
        device_risk = (i % 10) / 10.0
        is_international = 1 if country not in {"IN"} else 0

        risk = 0
        if amount > 75000:
            risk += 0.28
        if merchant in {"luxury", "casino", "travel"}:
            risk += 0.25
        if is_international:
            risk += 0.2
        if hour < 5:
            risk += 0.1
        if recent_txn_count >= 5:
            risk += 0.18
        if device_risk > 0.7:
            risk += 0.15

        target = 1 if (i % 100 < 8 or risk > 0.8) else 0
        rows.append({
            "amount": amount,
            "transaction_hour": hour,
            "is_weekend": is_weekend,
            "merchant_category": merchant,
            "transaction_type": tx_type,
            "country": country,
            "is_international": is_international,
            "customer_avg_amount": customer_avg_amount,
            "recent_txn_count": recent_txn_count,
            "device_risk": device_risk,
            "is_fraud": target,
        })

    return pd.DataFrame(rows)


def train_model():
    df = build_mock_dataset()
    y = df["is_fraud"]
    X = df.drop(columns=["is_fraud"])

    numeric_features = [
        "amount",
        "transaction_hour",
        "is_weekend",
        "is_international",
        "customer_avg_amount",
        "recent_txn_count",
        "device_risk",
    ]
    categorical_features = ["merchant_category", "transaction_type", "country"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric_features),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical_features),
        ]
    )

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    X_train_pre = preprocessor.fit_transform(X_train)
    X_test_pre = preprocessor.transform(X_test)

    model = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=42)
    smote = SMOTE(random_state=42)
    X_train_bal, y_train_bal = smote.fit_resample(X_train_pre, y_train)
    model.fit(X_train_bal, y_train_bal)

    y_pred = model.predict(X_test_pre)
    metrics = {
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "classification_report": classification_report(y_test, y_pred, output_dict=True),
    }

    joblib.dump(model, MODEL_DIR / "fraud_model.joblib")
    joblib.dump(preprocessor, MODEL_DIR / "fraud_preprocessor.joblib")

    with open(MODEL_DIR / "training_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print("Training complete. Model saved to", MODEL_DIR)
    print(classification_report(y_test, y_pred))
    return model


if __name__ == "__main__":
    train_model()
