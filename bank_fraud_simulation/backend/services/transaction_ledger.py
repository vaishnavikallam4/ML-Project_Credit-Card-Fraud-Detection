def transaction_direction(transaction_type):
    normalized = (transaction_type or "").strip().lower()
    if normalized in {"credit", "credited", "deposit", "salary", "refund", "incoming"}:
        return "CREDIT"
    return "DEBIT"


def apply_transaction_to_account(transaction):
    account = transaction.account
    if not account:
        return "The transaction is not linked to an account."

    amount = float(transaction.amount)
    if transaction_direction(transaction.transaction_type) == "CREDIT":
        account.balance += amount
        return None

    if account.balance < amount:
        return "The account has insufficient funds for this transaction."
    account.balance -= amount
    return None
