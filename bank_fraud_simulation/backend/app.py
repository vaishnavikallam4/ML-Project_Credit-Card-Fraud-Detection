import os

import click
from flask import Flask, jsonify, render_template, request
from flask_limiter.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.middleware.proxy_fix import ProxyFix

from backend.config import config, validate_production_config
from backend.extensions import cors, db, jwt, limiter, migrate
from backend.models import Account, Card, Transaction, User
from backend.routes.accounts import accounts_bp
from backend.routes.admin import admin_bp
from backend.routes.alerts import alerts_bp
from backend.routes.auth import auth_bp
from backend.routes.cards import cards_bp
from backend.routes.cases import cases_bp
from backend.routes.notifications import notifications_bp
from backend.routes.messages import messages_bp
from backend.routes.transactions import transactions_bp
from backend.services.demo_seed import seed_demo_data


def create_app(test_config=None):
    app = Flask(__name__)
    config_name = os.getenv("FLASK_ENV", "development")
    if config_name not in config:
        raise ValueError(f"Unsupported FLASK_ENV: {config_name}")
    app.config.from_object(config[config_name])

    if test_config:
        app.config.update(test_config)

    if config_name == "production":
        validate_production_config(app.config)
    trusted_proxy_count = app.config["TRUSTED_PROXY_COUNT"]
    if trusted_proxy_count:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=trusted_proxy_count,
            x_proto=trusted_proxy_count,
        )

    db.init_app(app)
    jwt.init_app(app)
    limiter.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={
        r"/api/*": {"origins": app.config["CORS_ORIGINS"]},
    })

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(accounts_bp)
    app.register_blueprint(cards_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(cases_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(messages_bp)

    if app.config.get("AUTO_CREATE_DB"):
        with app.app_context():
            db.create_all()
            if app.config.get("DEMO_MODE"):
                seed_demo_data()

    @app.cli.command("init-db")
    def init_db_command():
        """Create missing database tables for a fresh installation."""
        with app.app_context():
            db.create_all()
            if app.config.get("DEMO_MODE"):
                seed_demo_data()
        print("Database tables initialized.")

    @app.cli.command("create-user")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--role", type=click.Choice(["CUSTOMER", "BANK_ADMIN"], case_sensitive=False), prompt=True)
    @click.option("--phone", default="", help="Optional phone number.")
    def create_user_command(name, email, role, phone):
        """Provision a customer or bank admin without exposing its password in shell history."""
        email = email.strip().lower()
        name = name.strip()
        phone = phone.strip() or None
        if not name or not email:
            raise click.ClickException("Name and email are required.")
        if User.query.filter_by(email=email).first():
            raise click.ClickException("A user with this email already exists.")
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        if len(password) < 12:
            raise click.ClickException("Provisioned-user passwords must contain at least 12 characters.")
        user = User(name=name, email=email, phone=phone, role=role.upper())
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except SQLAlchemyError as error:
            db.session.rollback()
            raise click.ClickException("Could not provision the user; check the email and database constraints.") from error
        click.echo(f"Provisioned {user.role} user {user.email}.")

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", (
            "default-src 'self'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        ))
        if request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @app.errorhandler(RateLimitExceeded)
    def handle_rate_limit_exceeded(error):
        response = jsonify({"message": "Too many attempts. Please wait before trying again."})
        response.status_code = 429
        return response

    @app.route("/api/health")
    def health():
        try:
            db.session.execute(text("SELECT user_id FROM users LIMIT 1"))
        except SQLAlchemyError:
            app.logger.exception("Database health check failed.")
            db.session.rollback()
            return jsonify({"status": "unhealthy", "service": "bank-fraud-simulator"}), 503
        return jsonify({"status": "healthy", "service": "bank-fraud-simulator"}), 200

    @app.route("/")
    def home():
        return render_template("index.html")

    return app

app = create_app()


if __name__ == "__main__":
    if os.getenv("FLASK_ENV", "development") == "production":
        raise RuntimeError("Do not use Flask's development server in production; use a WSGI server.")
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(debug=debug, port=5000)
