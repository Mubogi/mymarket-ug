from datetime import datetime, timedelta

from flask import (
    abort,
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import func

from ..extensions import db, limiter
from ..models import (
    AdCampaign,
    Analytics,
    CATEGORIES,
    CITIES,
    MarketDay,
    MarketDayBooking,
    Payment,
    Product,
    PushSubscription,
    User,
    Vendor,
)
from ..utils import allowed_uploads, save_upload, unique_slug

bp = Blueprint("vendor", __name__, url_prefix="/vendor")

PAY_LABELS = {
    "setup": "Setup Fee",
    "pro_upload": "Pro Upload",
    "subscription": "Subscription",
    "boost": "Boost",
    "market_day": "Market Day",
    "ad_campaign": "Ad Campaign",
}


def current_vendor():
    if not current_user.is_authenticated or not current_user.vendor:
        return None
    return current_user.vendor


def create_payment(vendor, amount, type_, note=None):
    p = Payment(vendor_id=vendor.id, amount=amount, type=type_, note=note)
    db.session.add(p)
    db.session.commit()
    return p


# ---------- Auth ----------
@bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("8 per hour")
def signup():
    if request.method == "POST":
        f = request.form
        if len(f.get("password", "")) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("vendor.signup"))
        if User.query.filter_by(email=f["email"].lower()).first():
            flash("Email already registered. Please log in.", "error")
            return redirect(url_for("vendor.login"))
        user = User(
            name=f["name"].strip(),
            phone=f["phone"].strip(),
            email=f["email"].lower().strip(),
            role="vendor",
        )
        user.set_password(f["password"])
        db.session.add(user)
        db.session.flush()
        vendor = Vendor(
            user_id=user.id,
            shop_name=f["shop_name"].strip(),
            slug=unique_slug(f["shop_name"]),
            description=f.get("description", ""),
            location_city=f.get("location_city", "Kampala"),
            location_area=f.get("location_area", ""),
            location_detail=f.get("location_detail", ""),
            shop_no=f.get("shop_no", ""),
        )
        logo = save_upload(request.files.get("logo"))
        if logo:
            vendor.logo = logo
        db.session.add(vendor)
        db.session.commit()
        create_payment(
            vendor, current_app.config["SETUP_FEE"], "setup", "Vendor signup fee"
        )
        from ..sms import send_sms

        send_sms(
            user.phone,
            f"Hi {user.name}! Your MyMarket.ug application for '{vendor.shop_name}' was received. "
            "Pay UGX 10,000 setup fee to go live.",
        )
        login_user(user)
        flash(
            "Application received! Pay UGX 10,000 setup fee. An admin will activate your shop after payment.",
            "success",
        )
        return redirect(url_for("vendor.dashboard", tab="payments"))
    return render_template("vendor/signup.html", cities=CITIES)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"].lower()).first()
        if user and user.check_password(request.form["password"]):
            session.clear()  # anti session-fixation: fresh session on privilege change
            login_user(user)
            if user.is_admin:
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("vendor.dashboard"))
        flash("Wrong email or password.", "error")
    return render_template("vendor/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))


# ---------- Dashboard ----------
@bp.route("/", methods=["GET"])
@login_required
def dashboard():
    v = current_vendor()
    if not v:
        return redirect(url_for("vendor.signup"))
    tab = request.args.get("tab", "products")

    monthly = (
        db.session.query(Analytics.type, func.count(Analytics.id))
        .filter(
            Analytics.vendor_id == v.id,
            Analytics.created_at
            >= datetime.utcnow().replace(day=1, hour=0, minute=0, second=0),
        )
        .group_by(Analytics.type)
        .all()
    )
    stats = {"shop_view": 0, "product_view": 0, "whatsapp_click": 0, "call_click": 0}
    for t, c in monthly:
        stats[t] = c

    daily = (
        db.session.query(func.date(Analytics.created_at), func.count(Analytics.id))
        .filter(
            Analytics.vendor_id == v.id,
            Analytics.created_at >= datetime.utcnow() - timedelta(days=13),
        )
        .group_by(func.date(Analytics.created_at))
        .order_by(func.date(Analytics.created_at))
        .all()
    )

    return render_template(
        "vendor/dashboard.html",
        v=v,
        tab=tab,
        stats=stats,
        chart_labels=[str(d[0]) for d in daily],
        chart_values=[d[1] for d in daily],
        categories=CATEGORIES,
        upload_limit=allowed_uploads(v),
        payments=Payment.query.filter_by(vendor_id=v.id)
        .order_by(Payment.created_at.desc())
        .all(),
        market_days=MarketDay.query.filter(MarketDay.date >= datetime.utcnow().date())
        .order_by(MarketDay.date)
        .all(),
        my_bookings={b.market_day_id: b for b in v.market_day_bookings},
        campaigns=AdCampaign.query.filter_by(vendor_id=v.id)
        .order_by(AdCampaign.created_at.desc())
        .all(),
        fees=current_app.config,
    )


# ---------- Products ----------
@bp.route("/products/add", methods=["POST"])
@login_required
def add_product():
    v = current_vendor()
    if not v:
        abort(403)
    if v.products_uploaded_this_month >= allowed_uploads(v):
        flash(
            "Free limit reached. Pay UGX 5,000 Pro Upload to add 10 more products.",
            "error",
        )
        return redirect(url_for("vendor.dashboard", tab="payments"))
    image = save_upload(request.files.get("image"))
    p = Product(
        vendor_id=v.id,
        name=request.form["name"].strip(),
        description=request.form.get("description", ""),
        price=int(float(request.form["price"] or 0)),
        category=request.form.get("category", "Electronics"),
        image_url=image or request.form.get("image_url"),
    )
    v.products_uploaded_this_month = (v.products_uploaded_this_month or 0) + 1
    db.session.add(p)
    db.session.commit()
    flash("Product added!", "success")
    return redirect(url_for("vendor.dashboard", tab="products"))


@bp.route("/products/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def edit_product(pid):
    v = current_vendor()
    p = Product.query.get_or_404(pid)
    if p.vendor_id != v.id:
        abort(403)
    if request.method == "POST":
        p.name = request.form["name"].strip()
        p.description = request.form.get("description", "")
        p.price = int(float(request.form["price"] or 0))
        p.category = request.form.get("category", p.category)
        image = save_upload(request.files.get("image"))
        if image:
            p.image_url = image
        elif request.form.get("image_url"):
            p.image_url = request.form["image_url"]
        db.session.commit()
        flash("Product updated!", "success")
        return redirect(url_for("vendor.dashboard", tab="products"))
    return render_template("vendor/edit_product.html", v=v, p=p, categories=CATEGORIES)


@bp.route("/products/<int:pid>/delete", methods=["POST"])
@login_required
def delete_product(pid):
    v = current_vendor()
    p = Product.query.get_or_404(pid)
    if p.vendor_id != v.id:
        abort(403)
    db.session.delete(p)
    db.session.commit()
    flash("Product deleted.", "success")
    return redirect(url_for("vendor.dashboard", tab="products"))


@bp.route("/products/<int:pid>/boost", methods=["POST"])
@login_required
def boost_product(pid):
    v = current_vendor()
    p = Product.query.get_or_404(pid)
    if p.vendor_id != v.id:
        abort(403)
    create_payment(v, current_app.config["BOOST_FEE"], "boost", f"Boost: {p.name}")
    flash("Boost payment created (UGX 5,000). Your product goes to #1 once paid.", "success")
    return redirect(url_for("vendor.dashboard", tab="payments"))


# ---------- Payments (simulated checkout) ----------
@bp.route("/pay/<type_>", methods=["POST"])
@login_required
def pay(type_):
    v = current_vendor()
    fees = {
        "subscription": (current_app.config["SUBSCRIPTION_FEE"], "Monthly subscription"),
        "pro_upload": (current_app.config["PRO_UPLOAD_FEE"], "10 extra uploads"),
    }
    if type_ not in fees:
        abort(404)
    amount, note = fees[type_]
    create_payment(v, amount, type_, note)
    flash(f"Payment request created: UGX {amount:,} ({note}).", "success")
    return redirect(url_for("vendor.dashboard", tab="payments"))


# ---------- Market day booking ----------
@bp.route("/market-days/<int:day_id>/book", methods=["POST"])
@login_required
def book_market_day(day_id):
    v = current_vendor()
    day = MarketDay.query.get_or_404(day_id)
    if any(b.market_day_id == day_id for b in v.market_day_bookings):
        flash("You already booked this market day.", "error")
    else:
        payment = create_payment(v, day.fee_amount, "market_day", day.market_name)
        b = MarketDayBooking(market_day_id=day.id, vendor_id=v.id, payment_id=payment.id)
        db.session.add(b)
        db.session.commit()
        flash(f"Slot requested for {day.market_name} (UGX {day.fee_amount:,}).", "success")
    return redirect(url_for("vendor.dashboard", tab="market"))


# ---------- Ads ----------
@bp.route("/ads/request", methods=["POST"])
@login_required
def request_ad():
    v = current_vendor()
    budget = int(float(request.form.get("budget") or 0))
    if budget < 10_000:
        flash("Minimum ad budget is UGX 10,000.", "error")
        return redirect(url_for("vendor.dashboard", tab="ads"))
    c = AdCampaign(
        vendor_id=v.id,
        product_id=request.form.get("product_id") or None,
        budget=budget,
        platform=request.form.get("platform", "Facebook"),
    )
    db.session.add(c)
    db.session.commit()
    create_payment(v, budget, "ad_campaign", "Ad campaign budget")
    flash("Ad request submitted! We will create your ad and run it.", "success")
    return redirect(url_for("vendor.dashboard", tab="ads"))


# ---------- Shop settings ----------
@bp.route("/settings", methods=["POST"])
@login_required
def settings():
    v = current_vendor()
    if not v:
        abort(403)
    v.description = request.form.get("description", v.description)
    v.location_city = request.form.get("location_city", v.location_city)
    v.location_area = request.form.get("location_area", v.location_area)
    v.location_detail = request.form.get("location_detail", v.location_detail)
    v.shop_no = request.form.get("shop_no", v.shop_no)
    logo = save_upload(request.files.get("logo"))
    if logo:
        v.logo = logo
    db.session.commit()
    flash("Shop settings saved!", "success")
    return redirect(url_for("vendor.dashboard", tab="settings"))


# ---------- Push subscriptions ----------
@bp.route("/push/subscribe", methods=["POST"])
@login_required
def push_subscribe():
    data = request.get_json(force=True)
    sub = data.get("subscription", {})
    endpoint = sub.get("endpoint")
    if not endpoint:
        return jsonify({"ok": False}), 400
    keys = sub.get("keys", {})
    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not existing:
        db.session.add(
            PushSubscription(
                user_id=current_user.id,
                endpoint=endpoint,
                auth=keys.get("auth", ""),
                p256dh=keys.get("p256dh", ""),
            )
        )
        db.session.commit()
    return jsonify({"ok": True})
