from datetime import datetime

from backend.models.transaction import Transaction


def analyze_behavior(user_id: int, amount: float, transaction_time: datetime | None = None):
    transaction_time = transaction_time or datetime.utcnow()
    previous = (
        Transaction.query.filter(
            Transaction.user_id == user_id,
            Transaction.transaction_time < transaction_time,
        )
        .order_by(Transaction.transaction_time.desc())
        .limit(50)
        .all()
    )

    if not previous:
        score = 35.0 if amount >= 20000 else 12.0
        signals = ["No previous transaction history available for behavioral comparison."]
        return {
            "behavior_score": round(score, 2),
            "risk_level": "MEDIUM" if score >= 30 else "LOW",
            "signals": signals,
            "history_count": 0,
            "average_amount": 0.0,
        }

    avg = sum(float(tx.amount) for tx in previous) / len(previous)
    ratio = amount / avg if avg else 1.0

    score = 0.0
    signals = []

    if amount >= 50000:
        score += 35
        signals.append("Amount is far above the customer’s typical pattern.")
    elif amount >= 15000:
        score += 20
        signals.append("Amount is substantially above the user’s usual spending.")

    if ratio >= 5:
        score += 25
        signals.append("Transaction amount deviates sharply from the customer's historical spending.")
    elif ratio >= 2:
        score += 12
        signals.append("Amount is at least double the customer’s recent average spend.")

    if 0 <= transaction_time.hour < 5:
        score += 20
        signals.append("Transaction occurred during an unusual late-night period.")

    recent_txns = [
        tx for tx in previous if (transaction_time - tx.transaction_time).total_seconds() < 3600
    ]
    if len(recent_txns) >= 3:
        score += 18
        signals.append("Multiple transactions have occurred in a very short time window.")

    if score > 100:
        score = 100.0

    return {
        "behavior_score": round(score, 2),
        "risk_level": "HIGH" if score >= 75 else "MEDIUM" if score >= 45 else "LOW",
        "signals": signals or ["Transaction is consistent with recent customer activity."],
        "history_count": len(previous),
        "average_amount": round(avg, 2),
    }
