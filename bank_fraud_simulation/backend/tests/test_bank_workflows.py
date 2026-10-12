import unittest
from unittest.mock import Mock, patch

from flask_jwt_extended import create_access_token

from backend.app import create_app
from backend.extensions import db
from backend.models.account import Account
from backend.models.card import Card
from backend.models.communication_message import CommunicationMessage
from backend.models.fraud_alert import FraudAlert
from backend.models.fraud_case import FraudCase
from backend.models.notification import Notification
from backend.models.transaction import Transaction
from backend.models.user import User


class BankWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "AUTO_CREATE_DB": True,
            "DEMO_MODE": False,
            "PUBLIC_REGISTRATION_ENABLED": False,
            "JWT_SECRET_KEY": "test-jwt-secret-with-more-than-thirty-two-characters",
            "CORS_ORIGINS": ["http://localhost:5000"],
            "RATELIMIT_STORAGE_URI": "memory://",
            "TRUSTED_PROXY_COUNT": 0,
            "SMS_MODE": "simulation",
            "MSG91_AUTH_KEY": None,
            "MSG91_TEMPLATE_ID": None,
        })
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        self.customer = self._create_user("customer@example.test", "CUSTOMER")
        self.other_customer = self._create_user("other@example.test", "CUSTOMER")
        self.admin = self._create_user("admin@example.test", "BANK_ADMIN")
        self.account = self._create_account(self.customer, "SIM-TEST-100", 1000.0)
        self.other_account = self._create_account(self.other_customer, "SIM-TEST-200", 500.0)
        self.card = self._create_card(self.customer, self.account, "1111")
        self.other_card = self._create_card(self.other_customer, self.other_account, "2222")
        self.customer_headers = self._auth_headers(self.customer)
        self.admin_headers = self._auth_headers(self.admin)

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.app_context.pop()

    @staticmethod
    def _create_user(email, role):
        user = User(name=email.split("@")[0], email=email, role=role)
        user.set_password("test-password-123")
        db.session.add(user)
        db.session.flush()
        return user

    @staticmethod
    def _create_account(user, account_number, balance):
        account = Account(
            user_id=user.user_id,
            account_number=account_number,
            account_type="Savings",
            balance=balance,
            status="ACTIVE",
        )
        db.session.add(account)
        db.session.flush()
        return account

    @staticmethod
    def _create_card(user, account, last_four):
        card = Card(
            user_id=user.user_id,
            account_id=account.account_id,
            card_type="Visa",
            last_four=last_four,
            expiry_month="12",
            expiry_year="2030",
            status="ACTIVE",
        )
        db.session.add(card)
        db.session.flush()
        return card

    def _auth_headers(self, user):
        token = create_access_token(identity=str(user.user_id))
        return {"Authorization": f"Bearer {token}"}

    def _create_transaction(self, user, account, card, amount, status):
        transaction = Transaction(
            user_id=user.user_id,
            account_id=account.account_id,
            card_id=card.card_id,
            merchant="Test merchant",
            location="Test location",
            amount=amount,
            transaction_type="debit",
            status=status,
            risk_level="HIGH",
            prediction="FRAUD",
        )
        db.session.add(transaction)
        db.session.flush()
        return transaction

    def test_customers_only_see_their_own_transactions(self):
        own_transaction = self._create_transaction(
            self.customer, self.account, self.card, 25.0, "AUTHORIZED"
        )
        self._create_transaction(
            self.other_customer, self.other_account, self.other_card, 40.0, "AUTHORIZED"
        )
        for user, transaction in (
            (self.customer, own_transaction),
            (self.other_customer, Transaction.query.filter_by(user_id=self.other_customer.user_id).one()),
        ):
            db.session.add(FraudAlert(
                user_id=user.user_id,
                transaction_id=transaction.transaction_id,
                risk_level="HIGH",
                status="OPEN",
                message="Suspicious transaction.",
            ))
            db.session.add(Notification(
                user_id=user.user_id,
                transaction_id=transaction.transaction_id,
                channel="IN_APP",
                message="Transaction notification.",
                status="SENT",
            ))
        db.session.commit()

        response = self.client.get("/api/transactions", headers=self.customer_headers)
        accounts_response = self.client.get("/api/accounts", headers=self.customer_headers)
        cards_response = self.client.get("/api/cards", headers=self.customer_headers)
        alerts_response = self.client.get("/api/alerts", headers=self.customer_headers)
        profile_response = self.client.get("/api/auth/me", headers=self.customer_headers)
        admin_directory_response = self.client.get(
            "/api/admin/users",
            headers=self.customer_headers,
        )
        notifications_response = self.client.get(
            "/api/notifications",
            headers=self.customer_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["transaction_id"] for item in response.get_json()["transactions"]],
            [own_transaction.transaction_id],
        )
        self.assertEqual(len(accounts_response.get_json()["accounts"]), 1)
        self.assertEqual(len(cards_response.get_json()["cards"]), 1)
        self.assertEqual(len(alerts_response.get_json()["alerts"]), 1)
        self.assertEqual(len(notifications_response.get_json()["notifications"]), 1)
        self.assertEqual(profile_response.get_json()["user"]["role"], "CUSTOMER")
        self.assertEqual(admin_directory_response.status_code, 403)

    def test_customer_login_returns_customer_role(self):
        response = self.client.post(
            "/api/auth/login",
            json={
                "email": self.customer.email,
                "password": "test-password-123",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["role"], "CUSTOMER")
        profile_response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {response.get_json()['access_token']}"},
        )
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.get_json()["user"]["user_id"], self.customer.user_id)

    def test_customer_fraud_report_and_admin_conversation_are_case_linked(self):
        transaction = self._create_transaction(
            self.customer, self.account, self.card, 75.0, "PENDING"
        )
        alert = FraudAlert(
            user_id=self.customer.user_id,
            transaction_id=transaction.transaction_id,
            risk_level="HIGH",
            status="OPEN",
            message="Suspicious transaction.",
        )
        db.session.add(alert)
        db.session.commit()

        report = self.client.post(
            f"/api/alerts/transactions/{transaction.transaction_id}/respond",
            json={"response": "NO"},
            headers=self.customer_headers,
        )
        self.assertEqual(report.status_code, 200)
        case_id = report.get_json()["case_id"]
        self.assertIsNotNone(case_id)
        self.assertEqual(self.card.status, "HOLD")

        admin_cases = self.client.get("/api/cases", headers=self.admin_headers)
        case_payload = next(
            item for item in admin_cases.get_json()["cases"]
            if item["case_id"] == case_id
        )
        self.assertEqual(case_payload["customer_name"], self.customer.name)

        customer_message = self.client.post(
            "/api/messages",
            json={
                "message": "Please share the transaction details and block my card.",
                "case_id": case_id,
                "card_id": self.card.card_id,
                "requested_card_action": "BLOCKED",
            },
            headers=self.customer_headers,
        )
        self.assertEqual(customer_message.status_code, 201)

        admin_messages = self.client.get(
            f"/api/messages/customers/{self.customer.user_id}",
            headers=self.admin_headers,
        )
        self.assertEqual(admin_messages.status_code, 200)
        self.assertEqual(
            admin_messages.get_json()["messages"][0]["requested_card_action"],
            "BLOCKED",
        )
        self.assertEqual(
            admin_messages.get_json()["messages"][0]["case_id"],
            case_id,
        )

        reply = self.client.post(
            f"/api/messages/customers/{self.customer.user_id}",
            json={
                "message": "We are reviewing this transaction.",
                "case_id": case_id,
            },
            headers=self.admin_headers,
        )
        self.assertEqual(reply.status_code, 201)
        customer_messages = self.client.get(
            "/api/messages",
            headers=self.customer_headers,
        )
        self.assertEqual(customer_messages.status_code, 200)
        self.assertEqual(len(customer_messages.get_json()["messages"]), 2)
        self.assertEqual(CommunicationMessage.query.count(), 2)

    def test_customer_can_confirm_an_authorized_transaction_once(self):
        transaction = self._create_transaction(
            self.customer, self.account, self.card, 75.0, "AUTHORIZED"
        )

        initial_transactions = self.client.get(
            "/api/transactions",
            headers=self.customer_headers,
        ).get_json()["transactions"]
        initial_transaction = next(
            item for item in initial_transactions
            if item["transaction_id"] == transaction.transaction_id
        )
        self.assertIsNone(initial_transaction["customer_review_status"])

        confirmation = self.client.post(
            f"/api/alerts/transactions/{transaction.transaction_id}/respond",
            json={"response": "YES"},
            headers=self.customer_headers,
        )
        self.assertEqual(confirmation.status_code, 200)

        reviewed_transactions = self.client.get(
            "/api/transactions",
            headers=self.customer_headers,
        ).get_json()["transactions"]
        reviewed_transaction = next(
            item for item in reviewed_transactions
            if item["transaction_id"] == transaction.transaction_id
        )
        self.assertEqual(reviewed_transaction["customer_review_status"], "CONFIRMED")
        self.assertEqual(reviewed_transaction["card_id"], self.card.card_id)

        duplicate_confirmation = self.client.post(
            f"/api/alerts/transactions/{transaction.transaction_id}/respond",
            json={"response": "YES"},
            headers=self.customer_headers,
        )
        self.assertEqual(duplicate_confirmation.status_code, 409)

    def test_customer_can_report_an_authorized_transaction_from_history(self):
        transaction = self._create_transaction(
            self.customer, self.account, self.card, 75.0, "AUTHORIZED"
        )

        report = self.client.post(
            f"/api/alerts/transactions/{transaction.transaction_id}/respond",
            json={"response": "NO"},
            headers=self.customer_headers,
        )
        self.assertEqual(report.status_code, 200)
        self.assertIsNotNone(report.get_json()["case_id"])
        self.assertEqual(self.card.status, "HOLD")

        reviewed_transactions = self.client.get(
            "/api/transactions",
            headers=self.customer_headers,
        ).get_json()["transactions"]
        reviewed_transaction = next(
            item for item in reviewed_transactions
            if item["transaction_id"] == transaction.transaction_id
        )
        self.assertEqual(reviewed_transaction["customer_review_status"], "REPORTED")

    def test_admin_profile_returns_phone_alert_log_without_duplicate_notifications(self):
        db.session.add_all([
            Notification(
                user_id=self.customer.user_id,
                channel="IN_APP",
                message="In-app-only update.",
                status="SENT",
            ),
            Notification(
                user_id=self.customer.user_id,
                channel="SMS",
                message="Phone alert.",
                status="SIMULATED",
            ),
        ])
        db.session.commit()

        response = self.client.get(
            f"/api/admin/users/{self.customer.user_id}",
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertNotIn("notifications", payload)
        self.assertEqual(len(payload["sms_messages"]), 1)
        self.assertEqual(payload["sms_messages"][0]["message"], "Phone alert.")

    def test_customer_report_holds_card_and_admin_can_resolve_case(self):
        transaction = self._create_transaction(
            self.customer, self.account, self.card, 75.0, "PENDING"
        )
        db.session.add(FraudCase(
            user_id=self.customer.user_id,
            card_id=self.card.card_id,
            transaction_id=transaction.transaction_id,
            case_status="OPEN",
            customer_response="NO",
        ))
        db.session.commit()

        report = self.client.post(
            f"/api/alerts/transactions/{transaction.transaction_id}/respond",
            json={"response": "NO"},
            headers=self.customer_headers,
        )

        self.assertEqual(report.status_code, 409)
        self.assertEqual(self.card.status, "ACTIVE")

        db.session.query(FraudCase).delete()
        db.session.commit()
        report = self.client.post(
            f"/api/alerts/transactions/{transaction.transaction_id}/respond",
            json={"response": "NO"},
            headers=self.customer_headers,
        )
        self.assertEqual(report.status_code, 200)
        self.assertEqual(transaction.status, "FRAUD_REPORTED")
        self.assertEqual(self.card.status, "HOLD")

        case = FraudCase.query.filter_by(transaction_id=transaction.transaction_id).one()
        resolution = self.client.post(
            f"/api/cases/{case.case_id}/resolve",
            json={"decision": "FRAUD"},
            headers=self.admin_headers,
        )
        self.assertEqual(resolution.status_code, 200)
        self.assertEqual(transaction.status, "FRAUDULENT")
        self.assertEqual(self.card.status, "BLOCKED")

    def test_false_alarm_releases_hold_and_posts_a_pending_debit_once(self):
        transaction = self._create_transaction(
            self.customer, self.account, self.card, 125.0, "FRAUD_REPORTED"
        )
        self.card.status = "HOLD"
        case = FraudCase(
            user_id=self.customer.user_id,
            card_id=self.card.card_id,
            transaction_id=transaction.transaction_id,
            case_status="OPEN",
            customer_response="NO",
        )
        db.session.add(case)
        db.session.commit()

        resolution = self.client.post(
            f"/api/cases/{case.case_id}/resolve",
            json={"decision": "FALSE_ALARM"},
            headers=self.admin_headers,
        )
        self.assertEqual(resolution.status_code, 200)
        self.assertEqual(self.account.balance, 875.0)
        self.assertEqual(self.card.status, "ACTIVE")
        self.assertEqual(transaction.status, "AUTHORIZED")

        duplicate = self.client.post(
            f"/api/cases/{case.case_id}/resolve",
            json={"decision": "FALSE_ALARM"},
            headers=self.admin_headers,
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.account.balance, 875.0)

    def test_customer_cannot_use_an_inactive_account_card(self):
        self.account.status = "CLOSED"
        db.session.commit()

        response = self.client.post(
            "/api/transactions",
            json={
                "card_id": self.card.card_id,
                "amount": 20.0,
                "merchant": "Test merchant",
                "transaction_type": "debit",
            },
            headers=self.customer_headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("account is closed", response.get_json()["message"])
        self.assertEqual(Transaction.query.count(), 0)

    def test_account_creation_rejects_invalid_or_negative_balance(self):
        for balance in ("not-a-number", -1, float("nan"), float("inf")):
            with self.subTest(balance=balance):
                response = self.client.post(
                    "/api/accounts",
                    json={
                        "account_number": f"SIM-INVALID-{str(balance).replace('.', '')}",
                        "account_type": "Savings",
                        "balance": balance,
                    },
                    headers=self.customer_headers,
                )
                self.assertEqual(response.status_code, 400)
        self.assertEqual(Account.query.count(), 2)

    @patch("backend.services.sms_service.requests.post")
    def test_transaction_sends_sms_using_msg91_flow_when_configured(self, post):
        provider_response = Mock(status_code=200)
        provider_response.json.return_value = {"type": "success"}
        post.return_value = provider_response
        self.customer.phone = "+91 98765 43210"
        self.app.config.update({
            "SMS_MODE": "msg91",
            "MSG91_AUTH_KEY": "test-auth-key",
            "MSG91_TEMPLATE_ID": "approved-flow-id",
        })
        db.session.commit()

        response = self.client.post(
            "/api/transactions",
            json={
                "card_id": self.card.card_id,
                "amount": 25.0,
                "merchant": "Test merchant",
                "location": "Hyderabad",
                "transaction_type": "debit",
            },
            headers=self.customer_headers,
        )

        self.assertEqual(response.status_code, 201)
        sms_result = response.get_json()["sms_message"]
        self.assertEqual(sms_result["status"], "ACCEPTED")
        self.assertIn("not confirmed", sms_result["delivery_note"])
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "https://control.msg91.com/api/v5/flow/")
        self.assertEqual(post.call_args.kwargs["headers"]["authkey"], "test-auth-key")
        recipient = post.call_args.kwargs["json"]["recipients"][0]
        self.assertEqual(recipient["mobiles"], "919876543210")
        self.assertIn("debited", recipient["VAR1"])
        self.assertEqual(
            Notification.query.filter_by(channel="SMS").one().status,
            "ACCEPTED",
        )

    @patch("backend.services.sms_service.requests.post")
    def test_sms_provider_rejection_is_reported_without_undoing_transaction(self, post):
        post.return_value = Mock(status_code=401)
        self.customer.phone = "+91 98765 43210"
        self.app.config.update({
            "SMS_MODE": "msg91",
            "MSG91_AUTH_KEY": "test-auth-key",
            "MSG91_TEMPLATE_ID": "approved-flow-id",
        })
        db.session.commit()

        response = self.client.post(
            "/api/transactions",
            json={
                "card_id": self.card.card_id,
                "amount": 25.0,
                "merchant": "Test merchant",
                "location": "Hyderabad",
                "transaction_type": "debit",
            },
            headers=self.customer_headers,
        )

        self.assertEqual(response.status_code, 201)
        result = response.get_json()
        self.assertEqual(result["sms_message"]["status"], "FAILED")
        self.assertIn("SMS alert was not sent", result["message"])
        self.assertEqual(Transaction.query.count(), 1)
        self.assertEqual(Notification.query.filter_by(channel="SMS").one().status, "FAILED")


if __name__ == "__main__":
    unittest.main()
