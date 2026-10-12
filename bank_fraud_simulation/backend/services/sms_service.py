import re
from datetime import datetime

import requests
from flask import current_app


MSG91_FLOW_URL = "https://control.msg91.com/api/v5/flow/"


def _normalize_mobile(phone, country_code):
    value = str(phone or "").strip()
    if value.startswith("00"):
        value = value[2:]
    elif value.startswith("+"):
        value = value[1:]
    value = re.sub(r"[\s().-]", "", value)
    if not value.isdigit():
        return None
    if len(value) == 10:
        value = f"{country_code}{value}"
    elif value.startswith("0") and len(value) == 11:
        value = f"{country_code}{value[1:]}"
    if not 8 <= len(value) <= 15:
        return None
    return value


def deliver_sms_notification(notification, phone):
    mode = str(current_app.config.get("SMS_MODE", "simulation")).strip().lower()
    if mode == "simulation":
        notification.status = "SIMULATED"
        return notification.status
    if mode != "msg91":
        current_app.logger.error("SMS delivery is disabled because SMS_MODE is invalid.")
        notification.status = "FAILED"
        return notification.status

    auth_key = current_app.config.get("MSG91_AUTH_KEY")
    template_id = current_app.config.get("MSG91_TEMPLATE_ID")
    country_code = str(current_app.config.get("SMS_DEFAULT_COUNTRY_CODE", "91"))
    if not country_code.isdigit() or not 1 <= len(country_code) <= 3:
        current_app.logger.error("SMS_DEFAULT_COUNTRY_CODE must contain one to three digits.")
        notification.status = "FAILED"
        return notification.status
    mobile = _normalize_mobile(phone, country_code)
    if not auth_key or not template_id:
        current_app.logger.error("MSG91 SMS delivery is enabled but provider settings are missing.")
        notification.status = "FAILED"
        return notification.status
    if not mobile:
        current_app.logger.error(
            "SMS notification %s could not be sent because the customer phone number is invalid.",
            notification.notification_id,
        )
        notification.status = "FAILED"
        return notification.status

    try:
        response = requests.post(
            MSG91_FLOW_URL,
            headers={
                "authkey": auth_key,
                "accept": "application/json",
                "content-type": "application/json",
            },
            json={
                "template_id": template_id,
                "short_url": "0",
                "recipients": [{
                    "mobiles": mobile,
                    "VAR1": notification.message,
                }],
            },
            timeout=current_app.config.get("SMS_API_TIMEOUT_SECONDS", 8),
        )
    except requests.RequestException:
        current_app.logger.exception(
            "MSG91 request failed for SMS notification %s.",
            notification.notification_id,
        )
        notification.status = "FAILED"
        return notification.status

    if not 200 <= response.status_code < 300:
        current_app.logger.error(
            "MSG91 rejected SMS notification %s with HTTP status %s.",
            notification.notification_id,
            response.status_code,
        )
        notification.status = "FAILED"
        return notification.status

    try:
        result = response.json()
    except ValueError:
        current_app.logger.error(
            "MSG91 returned an unreadable response for SMS notification %s.",
            notification.notification_id,
        )
        notification.status = "FAILED"
        return notification.status

    if not isinstance(result, dict) or str(result.get("type", "")).lower() != "success":
        current_app.logger.error(
            "MSG91 did not accept SMS notification %s.",
            notification.notification_id,
        )
        notification.status = "FAILED"
        return notification.status

    notification.status = "ACCEPTED"
    notification.sent_at = datetime.utcnow()
    return notification.status
