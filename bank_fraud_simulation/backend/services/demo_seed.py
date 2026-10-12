from backend.extensions import db
from backend.models.account import Account
from backend.models.card import Card
from backend.models.user import User


def seed_demo_data():
    if User.query.filter_by(email="customer@demo.bank").first():
        return

    customer = User(
        name="Vaishnavi Sharma",
        email="customer@demo.bank",
        phone="+91 98765 43210",
        role="CUSTOMER",
        address="Hyderabad, Telangana",
    )
    customer.set_password("Demo@123")

    admin = User(
        name="Aditi Admin",
        email="admin@demo.bank",
        phone="+91 90000 11111",
        role="BANK_ADMIN",
        address="Head Office, Bengaluru",
    )
    admin.set_password("Demo@123")

    db.session.add_all([customer, admin])
    db.session.flush()

    account = Account(
        user_id=customer.user_id,
        account_number="SIM-1000001",
        account_type="Savings",
        balance=100000.0,
        status="ACTIVE",
    )
    db.session.add(account)
    db.session.flush()

    card = Card(
        user_id=customer.user_id,
        account_id=account.account_id,
        card_type="Visa",
        last_four="4821",
        expiry_month="12",
        expiry_year="2029",
        status="ACTIVE",
    )
    db.session.add(card)
    db.session.commit()
