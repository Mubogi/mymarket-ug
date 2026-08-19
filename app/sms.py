"""Africa's Talking SMS integration. No-ops when credentials are not set.
Get sandbox credentials at https://account.africastalking.com
"""
import requests

from flask import current_app


def _normalize(phone):
    digits = "".join(c for c in phone if c.isdigit())
    if digits.startswith("0"):
        digits = "256" + digits[1:]
    return "+" + digits


def send_sms(phone, message):
    username = current_app.config.get("AT_USERNAME")
    api_key = current_app.config.get("AT_API_KEY")
    if not (username and api_key and phone):
        return False
    base = (
        "https://api.sandbox.africastalking.com/version1/messaging"
        if username == "sandbox"
        else "https://api.africastalking.com/version1/messaging"
    )
    try:
        r = requests.post(
            base,
            data={"username": username, "to": _normalize(phone), "message": message},
            headers={"apiKey": api_key, "Accept": "application/json"},
            timeout=15,
        )
        ok = r.status_code == 201
        if not ok:
            current_app.logger.warning("SMS failed: %s", r.text[:200])
        return ok
    except requests.RequestException as exc:
        current_app.logger.warning("SMS error: %s", exc)
        return False
