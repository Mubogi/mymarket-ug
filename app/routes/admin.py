from datetime import date, datetime, timedelta

from flask import abort, Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from ..extensions import db
from ..models import (
    AdCampaign,
    MarketDay,
    MarketDayBooking,
    Payment,
    Product,
    Vendor,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@bp.before_request
def guard():
    admin_required()


@bp.route("/")
@login_required
def dashboard():
    now = datetime.utcnow()
    return render_template(
        "admin/dashboard.html",
        vendors=Vendor.query.order_by(Vendor.created_at.desc()).all(),
        payments=Payment.query.order_by(Payment.created_at.desc()).limit(100).all(),
        market_days=MarketDay.query.order_by(MarketDay.date).all(),
        campaigns=AdCampaign.query.order_by(AdCampaign.created_at.desc()).all(),
        bookings=MarketDayBooking.query.order_by(MarketDayBooking.created_at.desc()).all(),
        expiring=[
            v
            for v in Vendor.query.all()
            if v.subscription_expires_at
            and now <= v.subscription_expires_at <= now + timedelta(days=5)
        ],
    )


@bp.route("/vendors/<int:vid>/approve", methods=["POST"])
def approve_vendor(vid):
    v = Vendor.query.get_or_404(vid)
    v.is_active = True
    v.is_verified = True
    if not v.subscription_expires_at or v.subscription_expires_at < datetime.utcnow():
        v.subscription_expires_at = datetime.utcnow() + timedelta(days=30)
            # mark setup payment paid automatically upon approval
    for p in v.payments:
        if p.type == "setup" and p.status == "pending":
            p.status = "paid"
            p.paid_at = datetime.utcnow()
    db.session.commit()
    flash(f"Vendor '{v.shop_name}' approved & verified.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/vendors/<int:vid>/toggle", methods=["POST"])
def toggle_vendor(vid):
    v = Vendor.query.get_or_404(vid)
    v.is_active = not v.is_active
    db.session.commit()
    flash(f"{v.shop_name} is now {'active' if v.is_active else 'inactive'}.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/payments/<int:pid>/mark-paid", methods=["POST"])
def mark_paid(pid):
    p = Payment.query.get_or_404(pid)
    p.status = "paid"
    p.paid_at = datetime.utcnow()
    apply_payment_effect(p)
    db.session.commit()
    flash("Payment marked as paid.", "success")
    return redirect(url_for("admin.dashboard"))


def apply_payment_effect(payment):
    """Side effects once a payment is confirmed."""
    v = payment.vendor
    now = datetime.utcnow()
    if payment.type == "setup":
        v.is_active = True
        v.is_verified = True
        if not v.subscription_expires_at or v.subscription_expires_at < now:
            v.subscription_expires_at = now + timedelta(days=30)
    elif payment.type == "subscription":
        base = v.subscription_expires_at if v.subscription_expires_at and v.subscription_expires_at > now else now
        v.subscription_expires_at = base + timedelta(days=30)
        v.is_active = True
    elif payment.type == "boost" and payment.note:
        product = (
            Product.query.filter_by(vendor_id=v.id, name=payment.note.replace("Boost: ", ""))
            .order_by(Product.created_at.desc())
            .first()
        )
        if product:
            product.is_boosted = True
            product.boost_expires_at = now + timedelta(days=1)
    elif payment.type == "market_day":
        booking = MarketDayBooking.query.filter_by(payment_id=payment.id).first()
        if booking:
            booking.status = "confirmed"
    elif payment.type == "ad_campaign":
        c = AdCampaign.query.filter_by(vendor_id=v.id).order_by(AdCampaign.created_at.desc()).first()
        if c and c.status == "requested":
            c.status = "active"


@bp.route("/market-days/create", methods=["POST"])
def create_market_day():
    d = MarketDay(
        city=request.form["city"],
        market_name=request.form["market_name"],
        date=datetime.strptime(request.form["date"], "%Y-%m-%d").date(),
        fee_amount=int(float(request.form.get("fee_amount", 2000))),
    )
    db.session.add(d)
    db.session.commit()
    flash("Market day created.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/ads/<int:cid>/launch", methods=["POST"])
def launch_ad(cid):
    c = AdCampaign.query.get_or_404(cid)
    c.ad_copy = request.form.get("ad_copy", "").strip() or c.ad_copy
    c.status = "active"
    db.session.commit()
    flash("Campaign launched.", "success")
    return redirect(url_for("admin.dashboard"))


@bp.route("/ads/<int:cid>/complete", methods=["POST"])
def complete_ad(cid):
    c = AdCampaign.query.get_or_404(cid)
    c.status = "completed"
    db.session.commit()
    flash("Campaign completed.", "success")
    return redirect(url_for("admin.dashboard"))
