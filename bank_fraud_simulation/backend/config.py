import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEVELOPMENT_SECRET = "development-only-secret-change-before-deploy-2026"
DEVELOPMENT_JWT_SECRET = "development-only-jwt-secret-change-before-deploy-2026"


def _environment_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError(f"{name} must be set to true or false.")
    return normalized in {"true", "1", "yes"}


def _cors_origins():
    return [
        origin.strip().rstrip("/")
        for origin in os.getenv("CORS_ORIGINS", "http://127.0.0.1:5000,http://localhost:5000").split(",")
        if origin.strip()
    ]


def _trusted_proxy_count():
    value = os.getenv("TRUSTED_PROXY_COUNT", "0")
    try:
        count = int(value)
    except ValueError as error:
        raise ValueError("TRUSTED_PROXY_COUNT must be a non-negative integer.") from error
    if count < 0:
        raise ValueError("TRUSTED_PROXY_COUNT must be a non-negative integer.")
    return count


class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY") or DEVELOPMENT_SECRET
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or DEVELOPMENT_JWT_SECRET
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or (
        f"sqlite:///{(BASE_DIR / 'backend' / 'instance' / 'bank_fraud_simulation.db').as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    JWT_ACCESS_TOKEN_EXPIRES = 3600
    MAX_CONTENT_LENGTH = 1024 * 1024
    DEMO_MODE = _environment_bool("DEMO_MODE", True)
    AUTO_CREATE_DB = _environment_bool("AUTO_CREATE_DB", True)
    PUBLIC_REGISTRATION_ENABLED = _environment_bool("PUBLIC_REGISTRATION_ENABLED", True)
    CORS_ORIGINS = _cors_origins()
    RATELIMIT_STORAGE_URI = os.getenv("REDIS_URL", "memory://")
    RATELIMIT_HEADERS_ENABLED = True
    TRUSTED_PROXY_COUNT = _trusted_proxy_count()
    SMS_MODE = os.getenv("SMS_MODE", "simulation").strip().lower()
    SMS_DEFAULT_COUNTRY_CODE = os.getenv("SMS_DEFAULT_COUNTRY_CODE", "91").lstrip("+")
    SMS_API_TIMEOUT_SECONDS = 8
    MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY")
    MSG91_TEMPLATE_ID = os.getenv("MSG91_TEMPLATE_ID")


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    DEMO_MODE = _environment_bool("DEMO_MODE", False)
    AUTO_CREATE_DB = _environment_bool("AUTO_CREATE_DB", False)
    PUBLIC_REGISTRATION_ENABLED = _environment_bool("PUBLIC_REGISTRATION_ENABLED", False)
    CORS_ORIGINS = _cors_origins() if os.getenv("CORS_ORIGINS") else []
    RATELIMIT_STORAGE_URI = os.getenv("REDIS_URL")


def validate_production_config(app_config):
    errors = []
    secret_key = app_config.get("SECRET_KEY")
    jwt_secret_key = app_config.get("JWT_SECRET_KEY")

    if (
        not secret_key
        or len(secret_key) < 32
        or len(set(secret_key)) < 16
        or secret_key == DEVELOPMENT_SECRET
    ):
        errors.append("Set SECRET_KEY to a unique, random value of at least 32 characters.")
    if (
        not jwt_secret_key
        or len(jwt_secret_key) < 32
        or len(set(jwt_secret_key)) < 16
        or jwt_secret_key == DEVELOPMENT_JWT_SECRET
    ):
        errors.append("Set JWT_SECRET_KEY to a separate random value of at least 32 characters.")
    if secret_key and jwt_secret_key and secret_key == jwt_secret_key:
        errors.append("SECRET_KEY and JWT_SECRET_KEY must be different values.")
    if app_config.get("DEMO_MODE"):
        errors.append("DEMO_MODE must be false in production.")
    if app_config.get("PUBLIC_REGISTRATION_ENABLED"):
        errors.append("PUBLIC_REGISTRATION_ENABLED must be false in production.")

    database_uri = app_config.get("SQLALCHEMY_DATABASE_URI") or ""
    parsed_database_uri = urlsplit(database_uri)
    if not database_uri or parsed_database_uri.scheme.startswith("sqlite"):
        errors.append("Set DATABASE_URL to a persistent production database; SQLite is not supported in production.")
    if not app_config.get("CORS_ORIGINS"):
        errors.append("Set CORS_ORIGINS to the exact HTTPS origin(s) serving the frontend.")
    elif any(
        urlsplit(origin).scheme != "https"
        or not urlsplit(origin).hostname
        or urlsplit(origin).username
        or urlsplit(origin).password
        or urlsplit(origin).path not in {"", "/"}
        or urlsplit(origin).query
        or urlsplit(origin).fragment
        or "*" in origin
        for origin in app_config["CORS_ORIGINS"]
    ):
        errors.append("Every production CORS_ORIGINS entry must use HTTPS.")
    if app_config.get("AUTO_CREATE_DB"):
        errors.append("AUTO_CREATE_DB must be false in production; apply schema changes explicitly.")
    if app_config.get("TRUSTED_PROXY_COUNT", 0) < 1:
        errors.append("Set TRUSTED_PROXY_COUNT to the number of trusted HTTPS reverse proxies.")
    sms_mode = str(app_config.get("SMS_MODE", "simulation")).lower()
    if sms_mode not in {"simulation", "msg91"}:
        errors.append("SMS_MODE must be simulation or msg91.")
    if sms_mode == "msg91" and (
        not app_config.get("MSG91_AUTH_KEY")
        or not app_config.get("MSG91_TEMPLATE_ID")
    ):
        errors.append("Configure MSG91_AUTH_KEY and MSG91_TEMPLATE_ID when SMS_MODE=msg91.")
    rate_limit_uri = app_config.get("RATELIMIT_STORAGE_URI") or ""
    parsed_rate_limit_uri = urlsplit(rate_limit_uri)
    if parsed_rate_limit_uri.scheme not in {"redis", "rediss"} or not parsed_rate_limit_uri.hostname:
        errors.append("Set REDIS_URL to shared Redis storage for production rate limiting.")

    if errors:
        raise RuntimeError("Invalid production configuration: " + " ".join(errors))


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
