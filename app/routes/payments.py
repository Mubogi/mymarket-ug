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
from ..models import Order, Payment, Product

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


def settle_order(order):
    """Mark an order paid, decrement stock, and notify the vendor."""
    from ..sms import send_sms
    from ..push import notify_user

    order.status = "paid"
    order.paid_at = datetime.utcnow()
    p = order.product
    if p is not None and p.stock is not None:
        p.stock = max(0, p.stock - order.qty)
    order.merchant_notify = True
    db.session.commit()
    phone = order.vendor.user.phone
    if phone:
        send_sms(
            phone,
            f"MyMarket.ug: New order! {order.customer_name or 'Customer'} bought "
            f"{order.qty}x {p.name if p else 'item'} UGX {order.amount:,}. "
            f"Call {order.customer_phone or 'no number'} to arrange delivery.",
        )
    notify_user(order.vendor.user_id, "New order", f"{order.qty}x {p.name if p else 'item'} paid — UGX {order.amount:,}", "/vendor#orders")


@bp.route("/orders/buy/<int:product_id>", methods=["POST"])
@limiter.limit("10 per hour")
def buy_product(product_id):
    """Create a customer order. Pays via Flutterwave checkout, or cash-on-delivery."""
    p = Product.query.get_or_404(product_id)
    if p.is_hidden or not p.vendor.is_active:
        abort(404)
    if p.stock is not None and p.stock <= 0:
        flash("This product is out of stock.", "error")
        return redirect(url_for("main.product_view", product_id=p.id))
    try:
        raw_qty = int(request.form.get("qty", "1"))
    except (TypeError, ValueError):
        raw_qty = 1
    qty = max(1, min(99, raw_qty))
    if p.stock is not None and qty > p.stock:
        flash(f"Only {p.stock} in stock.", "error")
        return redirect(url_for("main.product_view", product_id=p.id))

    unit = p.discounted_price if p.discount else p.price
    amount = unit * qty
    try:
        raw_fee = int(request.form.get("delivery_fee", "0") or "0")
    except (TypeError, ValueError):
        raw_fee = 0
    delivery_fee = max(0, min(20000, raw_fee))
    total = amount + delivery_fee

    payment_method = (request.form.get("payment") or "flutterwave").strip().lower()
    if payment_method not in ("flutterwave", "cod"):
        payment_method = "flutterwave"

    name = (request.form.get("name") or "").strip()[:120]
    phone = (request.form.get("phone") or "").strip()[:30]
    email = (request.form.get("email") or "").strip()[:120]
    address = (request.form.get("address") or "").strip()[:255]
    if not (name and phone):
        flash("Please provide your name and phone number.", "error")
        return redirect(url_for("main.product_view", product_id=p.id))

    order = Order(
        product_id=p.id,
        vendor_id=p.vendor_id,
        qty=qty,
        amount=amount,
        delivery_fee=delivery_fee,
        payment_method=payment_method,
        customer_name=name,
        customer_phone=phone,
        customer_email=email,
        customer_address=address,
        tx_ref=f"mymarket-order-{int(time.time())}-{p.id}",
    )
    # Reserve stock for COD (paid orders reserve in settle_order on payment).
    if payment_method == "cod" and p.stock is not None:
        p.stock = max(0, p.stock - qty)
    db.session.add(order)
    db.session.commit()

    from ..sms import send_sms
    from ..push import notify_user

    if payment_method == "cod":
        # Cash-on-delivery: no gateway needed. Notify the vendor immediately.
        order.status = "pending"
        order.merchant_notify = True
        db.session.commit()
        vend_phone = order.vendor.user.phone
        if vend_phone:
            send_sms(
                vend_phone,
                f"MyMarket.ug: New COD order! {name} wants {qty}x {p.name} "
                f"(UGX {total:,}, delivery {delivery_fee:,}). Call {phone}.",
            )
        notify_user(
            order.vendor.user_id,
            "New COD order",
            f"{qty}x {p.name} — UGX {total:,}. Call {phone} to confirm.",
            "/vendor#orders",
        )
        flash("Order placed! The vendor will call you to confirm delivery. 🎉", "success")
        return redirect(url_for("main.order_confirmation", order_id=order.id))

    if not flw.flutterwave_enabled(current_app):
        flash("Online payments are not enabled yet. Please use WhatsApp or Cash on Delivery.", "error")
        return redirect(url_for("main.product_view", product_id=p.id))

    link = flw.create_merchant_checkout(
        current_app,
        total,
        order.tx_ref,
        {
            "email": email or "buyer@example.com",
            "phonenumber": phone or "",
            "name": name or "Buyer",
        },
        p.vendor,
        f"{p.name} × {qty}",
        url_for("payments.order_callback", _external=True),
    )
    if not link:
        order.status = "cancelled"
        db.session.commit()
        flash("Could not start checkout. Please try again.", "error")
        return redirect(url_for("main.product_view", product_id=p.id))
    return redirect(link)


@bp.route("/payments/order-callback")
def order_callback():
    """Flutterwave redirects the customer here after a product order payment."""
    status = request.args.get("status")
    tx_ref = request.args.get("tx_ref")
    transaction_id = request.args.get("transaction_id")
    order = Order.query.filter_by(tx_ref=tx_ref).first() if tx_ref else None
    if status in ("successful", "completed")and transaction_id:
        ok, verified_ref = flw.verify_transaction(current_app, transaction_id)
        if ok and order and verified_ref == order.tx_ref and order.status != "paid":
            settle_order(order)
            flash("Payment received! The vendor has been notified. Thank you 🎉", "success")
            if order.customer_email:
                from ..mail import send_mail
                send_mail(
                    order.customer_email,
                    "Your MyMarket.ug order confirmation",
                    f"Hi {order.customer_name or 'there'}, your order for {order.qty}x "
                    f"{order.product.name} (UGX {order.amount:,}) is confirmed. "
                    f"Vendor will contact you on {order.customer_phone or 'the number you gave'}.",
                )
            return redirect(url_for("main.product_view", product_id=order.product_id))
    flash("Payment not confirmed. If money was deducted, contact support.", "error")
    return redirect(url_for("main.product_view", product_id=p.id)) if (p := Order.query.filter_by(tx_ref=tx_ref).first()) else redirect("/")


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
        order = Order.query.filter_by(tx_ref=tx_ref).first()
        if order and order.status != "paid":
            settle_order(order)


    return jsonify({"ok": True})
