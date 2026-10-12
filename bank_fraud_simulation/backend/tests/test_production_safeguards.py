import unittest

from sqlalchemy import inspect

from backend.app import app as default_app
from backend.app import create_app
from backend.config import validate_production_config
from backend.extensions import db
from backend.models.user import User


class ProductionSafeguardTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        with default_app.app_context():
            db.session.remove()
            db.engine.dispose()

    def setUp(self):
        self.apps = []

    def tearDown(self):
        for app in self.apps:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()

    def create_test_app(self, **overrides):
        settings = {
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
        }
        settings.update(overrides)
        app = create_app(settings)
        self.apps.append(app)
        return app

    def test_login_is_rate_limited_with_json_response(self):
        app = self.create_test_app()
        client = app.test_client()

        statuses = [
            client.post(
                "/api/auth/login",
                json={"email": "missing@example.test", "password": "not-the-password"},
            ).status_code
            for _ in range(6)
        ]

        self.assertEqual(statuses, [401, 401, 401, 401, 401, 429])
        response = client.post(
            "/api/auth/login",
            json={"email": "missing@example.test", "password": "not-the-password"},
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(
            response.get_json(),
            {"message": "Too many attempts. Please wait before trying again."},
        )

    def test_registration_can_be_disabled(self):
        client = self.create_test_app().test_client()

        statuses = [
            client.post(
                "/api/auth/register",
                json={
                    "name": f"New Customer {attempt}",
                    "email": f"new{attempt}@example.test",
                    "password": "a-long-enough-password",
                },
            ).status_code
            for attempt in range(4)
        ]

        self.assertEqual(statuses, [403, 403, 403, 429])

    def test_rate_limit_uses_client_ip_from_configured_proxy(self):
        client = self.create_test_app(TRUSTED_PROXY_COUNT=1).test_client()
        headers = {"X-Forwarded-For": "198.51.100.10"}

        statuses = [
            client.post(
                "/api/auth/login",
                json={"email": "missing@example.test", "password": "not-the-password"},
                headers=headers,
            ).status_code
            for _ in range(6)
        ]
        another_ip_response = client.post(
            "/api/auth/login",
            json={"email": "missing@example.test", "password": "not-the-password"},
            headers={"X-Forwarded-For": "198.51.100.11"},
        )

        self.assertEqual(statuses, [401, 401, 401, 401, 401, 429])
        self.assertEqual(another_ip_response.status_code, 401)

    def test_migration_builds_schema_without_create_all(self):
        app = self.create_test_app(AUTO_CREATE_DB=False)
        result = app.test_cli_runner().invoke(args=["db", "upgrade"])

        self.assertEqual(result.exit_code, 0, result.output)
        with app.app_context():
            table_names = set(inspect(db.engine).get_table_names())
        self.assertIn("alembic_version", table_names)
        self.assertTrue({
            "users",
            "accounts",
            "cards",
            "transactions",
            "fraud_alerts",
            "fraud_cases",
            "notifications",
            "police_reports",
        }.issubset(table_names))
        downgrade = app.test_cli_runner().invoke(args=["db", "downgrade", "base"])
        self.assertEqual(downgrade.exit_code, 0, downgrade.output)
        with app.app_context():
            self.assertNotIn("users", inspect(db.engine).get_table_names())
        reapply = app.test_cli_runner().invoke(args=["db", "upgrade"])
        self.assertEqual(reapply.exit_code, 0, reapply.output)

    def test_production_configuration_rejects_unsafe_settings(self):
        safe_config = {
            "SECRET_KEY": "Aa1!bC2@dE3#fG4$hI5%jK6^mL7&nO8*pQ9(",
            "JWT_SECRET_KEY": "Zx9!wV8@uT7#sR6$qP5%oN4^mL3&kJ2*iH1(",
            "DEMO_MODE": False,
            "PUBLIC_REGISTRATION_ENABLED": False,
            "SQLALCHEMY_DATABASE_URI": "postgresql://app:password@localhost/bank",
            "CORS_ORIGINS": ["https://bank.example"],
            "AUTO_CREATE_DB": False,
            "RATELIMIT_STORAGE_URI": "rediss://cache.example:6379/0",
            "TRUSTED_PROXY_COUNT": 1,
        }

        validate_production_config(safe_config)
        validate_production_config({
            **safe_config,
            "SMS_MODE": "msg91",
            "MSG91_AUTH_KEY": "test-auth-key",
            "MSG91_TEMPLATE_ID": "approved-flow-id",
        })

        for key, value in (
            ("DEMO_MODE", True),
            ("CORS_ORIGINS", ["https://*"]),
            ("SECRET_KEY", "weak"),
            ("RATELIMIT_STORAGE_URI", "memory://"),
            ("TRUSTED_PROXY_COUNT", 0),
            ("SMS_MODE", "unknown-provider"),
        ):
            with self.subTest(setting=key):
                with self.assertRaises(RuntimeError):
                    validate_production_config({**safe_config, key: value})
        with self.assertRaises(RuntimeError):
            validate_production_config({**safe_config, "SMS_MODE": "msg91"})

    def test_local_demo_seed_is_not_created_when_disabled(self):
        app = self.create_test_app()
        with app.app_context():
            self.assertEqual(User.query.count(), 0)

    def test_security_headers_are_set(self):
        response = self.create_test_app().test_client().get(
            "/",
            base_url="https://bank.example",
        )

        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Strict-Transport-Security"], "max-age=31536000")

    def test_forwarded_https_is_trusted_only_when_proxy_is_configured(self):
        forwarded_headers = {"X-Forwarded-Proto": "https"}
        untrusted_response = self.create_test_app().test_client().get(
            "/",
            headers=forwarded_headers,
        )
        trusted_response = self.create_test_app(TRUSTED_PROXY_COUNT=1).test_client().get(
            "/",
            headers=forwarded_headers,
        )

        self.assertNotIn("Strict-Transport-Security", untrusted_response.headers)
        self.assertEqual(
            trusted_response.headers["Strict-Transport-Security"],
            "max-age=31536000",
        )


if __name__ == "__main__":
    unittest.main()
