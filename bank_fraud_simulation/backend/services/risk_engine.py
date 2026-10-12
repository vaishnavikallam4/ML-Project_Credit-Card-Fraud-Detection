from __future__ import annotations


def get_risk_level(score: float) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 45:
        return "MEDIUM"
    return "LOW"


def calculate_overall_risk(ml_probability: float, behavior_score: float, amount: float) -> dict:
    amount_factor = 0.0
    if amount >= 100000:
        amount_factor = 35
    elif amount >= 50000:
        amount_factor = 25
    elif amount >= 20000:
        amount_factor = 15
    elif amount >= 8000:
        amount_factor = 8

    overall_score = max(ml_probability * 100, behavior_score) + amount_factor
    overall_score = min(overall_score, 100.0)

    return {
        "overall_risk_score": round(overall_score, 2),
        "risk_level": get_risk_level(overall_score),
    }
