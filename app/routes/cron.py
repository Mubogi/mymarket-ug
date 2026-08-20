import hmac
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from ..extensions import db
from ..models import Product, Vendor

bp = Blueprint("cron", __name__, url_prefix="/cron")


def authorized():
    secret = current_app.config["CRON_SECRET"]
    provided = request.args.get("secret") or request.headers.get("X-Cron-Secret") or ""
    return hmac.compare_digest(provided, secret)


@bp.route("/daily", methods=["POST", "GET"])
def daily():
    """Run once per day (e.g. Render Cron Job or cron-job.org)."""
    if not authorized():
        return jsonify({"ok": False, "error": "unauthorized"}), 403
    now = datetime.utcnow()
    results = {}

    # 1. Deactivate vendors with expired subscriptions
    expired = Vendor.query.filter(
        Vendor.subscription_expires_at.isnot(None),
        Vendor.subscription_expires_at < now,
        Vendor.is_active.is_(True),
    ).all()
    for v in expired:
        v.is_active = False
    results["deactivated_vendors"] = len(expired)

    # 2. Reset monthly upload counters on the 1st
    if now.day == 1:
        Vendor.query.update({Vendor.products_uploaded_this_month: 0})
        results["monthly_counters_reset"] = True

    # 3. Expire boosts
    stale = Product.query.filter(
        Product.is_boosted.is_(True),
        Product.boost_expires_at.isnot(None),
        Product.boost_expires_at < now,
    ).all()
    for p in stale:
        p.is_boosted = False
    results["boosts_expired"] = len(stale)

    db.session.commit()

    # 4. Daily digest push: "You have N new shop views today"
    from ..models import Analytics
    from ..push import notify_user

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    digests_sent = 0
    for v in Vendor.query.filter(Vendor.is_active.is_(True)).all():
        views = Analytics.query.filter(
            Analytics.vendor_id == v.id,
            Analytics.type == "shop_view",
            Analytics.created_at >= today_start,
        ).count()
        if views:
            digests_sent += notify_user(
                v.user_id, "MyMarket.ug daily update 📈",
                f"You have {views} new shop views today!", "/vendor",
            )
    results["digest_pushes_sent"] = digests_sent

    db.session.commit()
    results["ok"] = True
    return jsonify(results)
