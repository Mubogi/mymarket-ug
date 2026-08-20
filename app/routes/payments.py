import time
from datetime import datetime
import hmac

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    request,
    url_for,
)
from flask_login import current_user, login_required

from .. import payments as flw
from ..extensions import db, limiter
from ..models import Payment

bp = Blueprint("payments", __name__)


def settle_payment(payment):
    """Mark a payment paid and apply its side effects (shared logic)."""
    from .admin import apply_payment_effect
    from ..sms import send_sms

    payment.status = "paid"
    payment.paid_at = datetime.utcnow()
    apply_payment_effect(payment)
    db.session.commit()
    send_sms(
        payment.vendor.user.phone,
        f"MyMarket.ug: payment of UGX {payment.amount:,} ({payment.type.replace('_', ' ')}) confirmed. Thank you!",
    )


@bp.route("/vendor/checkout/<int:payment_id>", methods=["POST"])
@limiter.limit("20 per hour")
@login_required
def checkout(payment_id):
    """Start a Flutterwave checkout for a pending payment."""
    payment = Payment.query.get_or_404(payment_id)
    if not current_user.vendor or payment.vendor_id != current_user.vendor.id:
        abort(403)
    if payment.status == "paid":
        flash("This payment is already completed.", "success")
        return redirect(url_for("vendor.dashboard", tab="payments"))

    if not flw.flutterwave_enabled(current_app):
        flash("Online checkout is not enabled yet. Please pay manually; admin will confirm.", "error")
        return redirect(url_for("vendor.dashboard", tab="payments"))

    payment.tx_ref = f"mymarket-{payment.id}-{int(time.time())}"
    db.session.commit()
    link = flw.create_checkout(
        current_app,
        payment,
        payment.vendor,
        redirect_url=url_for("payments.callback", _external=True),
    )
    if not link:
        flash("Could not start checkout. Please try again.", "error")
        return redirect(url_for("vendor.dashboard", tab="payments"))
    return redirect(link)


@bp.route("/payments/callback")
def callback():
    """Flutterwave redirects the customer here after payment."""
    status = request.args.get("status")
    tx_ref = request.args.get("tx_ref")
    transaction_id = request.args.get("transaction_id")
    payment = Payment.query.filter_by(tx_ref=tx_ref).first() if tx_ref else None

    if status in ("successful", "completed") and transaction_id:
        ok, verified_ref = flw.verify_transaction(current_app, transaction_id)
        if ok and payment and verified_ref == payment.tx_ref and payment.status != "paid":
            settle_payment(payment)
            flash("Payment received! Thank you 🎉", "success")
            return redirect(url_for("vendor.dashboard", tab="payments"))
    flash("Payment not confirmed. If money was deducted, contact support.", "error")
    return redirect(url_for("vendor.dashboard", tab="payments"))


@bp.route("/payments/webhook", methods=["POST"])
def webhook():
    """Flutterwave server-to-server confirmation (source of truth)."""
    secret_hash = current_app.config.get("FLW_WEBHOOK_HASH", "")
    if secret_hash and not hmac.compare_digest(
        request.headers.get("verif-hash", ""), secret_hash
    ):
        return jsonify({"ok": False}), 401
    data = request.get_json(silent=True) or {}
    event_data = data.get("data", {})
    tx_ref = event_data.get("tx_ref")
    if data.get("event") == "charge.completed" and event_data.get("status") == "successful":
        payment = Payment.query.filter_by(tx_ref=tx_ref).first()
        if payment and payment.status != "paid":
            settle_payment(payment)
    return jsonify({"ok": True})
