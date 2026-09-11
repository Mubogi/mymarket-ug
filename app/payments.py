"""Flutterwave Standard checkout integration (MTN MoMo / Airtel Money).

If FLW_SECRET_KEY is not configured, the app falls back to simulated payments
(admin manually marks payments as paid).
"""
import requests

FLW_BASE = "https://api.flutterwave.com/v3"


def flutterwave_enabled(app):
    return bool(app.config.get("FLW_SECRET_KEY"))


def create_checkout(app, payment, vendor, redirect_url):
    """Returns a hosted checkout URL, or None on failure."""
    body = {
        "tx_ref": payment.tx_ref,
        "amount": payment.amount,
        "currency": "UGX",
        "redirect_url": redirect_url,
        "customer": {
            "email": vendor.user.email,
            "phonenumber": vendor.user.phone,
            "name": vendor.user.name,
        },
        "customizations": {
            "title": "MyMarket.ug",
            "description": f"{payment.type.replace('_', ' ').title()} — {vendor.shop_name}",
        },
        "meta": {"payment_id": payment.id},
    }
    try:
        r = requests.post(
            f"{FLW_BASE}/payments",
            json=body,
            headers={"Authorization": f"Bearer {app.config['FLW_SECRET_KEY']}"},
            timeout=20,
        )
        data = r.json()
        if data.get("status") == "success":
            return data["data"]["link"]
        app.logger.error("Flutterwave checkout failed: %s", data)
    except requests.RequestException as exc:
        app.logger.error("Flutterwave request error: %s", exc)
    return None


def create_merchant_checkout(app, amount, tx_ref, customer, vendor, description, redirect_url):
    """Hosted Flutterwave checkout paid to the platform, optionally split
    to the vendor's subaccount (merchant model with marketplace split).

    customer: {email, phonenumber, name}
    Returns checkout link or None on failure."""
    body = {
        "tx_ref": tx_ref,
        "amount": amount,
        "currency": "UGX",
        "redirect_url": redirect_url,
        "customer": {
            "email": customer.get("email"),
            "phonenumber": customer.get("phonenumber"),
            "name": customer.get("name"),
        },
        "customizations": {
            "title": "MyMarket.ug",
            "description": description,
        },
        "meta": {
            "order_tx_ref": tx_ref,
            "vendor_id": vendor.id if vendor else None,
        },
    }
    if vendor and vendor.flw_subaccount_id:
        body["subaccounts"] = [
            {
                "id": vendor.flw_subaccount_id,
                "transaction_split_type": "percentage",
                "transaction_split_value": "95",
            }
        ]
    try:
        r = requests.post(
            f"{FLW_BASE}/payments",
            json=body,
            headers={"Authorization": f"Bearer {app.config['FLW_SECRET_KEY']}"},
            timeout=20,
        )
        data = r.json()
        if data.get("status") == "success":
            return data["data"]["link"]
        app.logger.error("Flutterwave merchant checkout failed: %s", data)
    except requests.RequestException as exc:
        app.logger.error("Flutterwave merchant checkout error: %s", exc)
    return None


def verify_transaction(app, transaction_id):
    """Returns (ok, tx_ref) for a completed transaction."""
    try:
        r = requests.get(
            f"{FLW_BASE}/transactions/{transaction_id}/verify",
            headers={"Authorization": f"Bearer {app.config['FLW_SECRET_KEY']}"},
            timeout=20,
        )
        data = r.json()
        if data.get("status") == "success" and data["data"]["status"] == "successful":
            return True, data["data"].get("tx_ref")
    except requests.RequestException as exc:
        app.logger.error("Flutterwave verify error: %s", exc)
    return False, None
