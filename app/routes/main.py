from datetime import date, datetime, timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
)
from flask_login import current_user

from ..extensions import db
from ..models import (
    AdCampaign,
    CATEGORIES,
    CITIES,
    MarketDay,
    Product,
    Review,
    Vendor,
)
from ..utils import boosted_first, track

bp = Blueprint("main", __name__)


def resolve_shop(slug):
    vendor = Vendor.query.filter_by(slug=slug).first()
    if not vendor:
        return None
    return vendor


@bp.before_app_request
def detect_subdomain():
    """If a vendor subdomain exists, expose it for shop rendering."""
    g.subdomain_vendor = None
    host = request.host.split(":")[0]
    base = current_app.config["BASE_DOMAIN"]
    if host != base and host.endswith("." + base):
        slug = host[: -(len(base) + 1)]
        g.subdomain_vendor = Vendor.query.filter_by(slug=slug).first()


def upcoming_market_banner():
    soon = date.today() + timedelta(days=3)
    return (
        MarketDay.query.filter(MarketDay.date >= date.today(), MarketDay.date <= soon)
        .order_by(MarketDay.date)
        .all()
    )


@bp.route("/")
def index():
    if g.get("subdomain_vendor"):
        return shop_page(g.subdomain_vendor)
    q = request.args.get("q", "").strip()
    city = request.args.get("city", "")
    category = request.args.get("category", "")

    qry = (
        Product.query.join(Vendor)
        .filter(Vendor.is_active.is_(True))
        .order_by(db.desc(Product.is_boosted), db.desc(Product.created_at))
    )
    if q:
        like = f"%{q}%"
        qry = qry.filter(
            db.or_(
                Product.name.ilike(like),
                Product.description.ilike(like),
                Vendor.shop_name.ilike(like),
            )
        )
    if city:
        qry = qry.filter(Vendor.location_city == city)
    if category:
        qry = qry.filter(Product.category == category)

    products = boosted_first(qry.limit(200).all())
    response = make_response(
        render_template(
            "index.html",
            products=products,
            categories=CATEGORIES,
            cities=CITIES,
            banner_days=upcoming_market_banner(),
            q=q,
            city=city,
            category=category,
        )
    )
    # Let Cloudflare/other CDNs cache the homepage for anonymous visitors
    if not current_user.is_authenticated:
        response.headers["Cache-Control"] = "public, max-age=60, s-maxage=120"
    return response


@bp.route("/shop/<slug>")
def shop(slug):
    vendor = resolve_shop(slug)
    if not vendor:
        abort(404)
    return shop_page(vendor)


def shop_page(vendor):
    track(vendor.id, "shop_view")
    products = boosted_first(vendor.products)
    return render_template(
        "shop.html", vendor=vendor, products=products, basedomain=True
    )


@bp.route("/product/<int:product_id>")
def product_view(product_id):
    p = Product.query.get_or_404(product_id)
    p.views_count = (p.views_count or 0) + 1
    db.session.commit()
    track(p.vendor_id, "product_view", p.id)
    return render_template("product.html", product=p)


@bp.route("/product/<int:product_id>/review", methods=["POST"])
def add_review(product_id):
    p = Product.query.get_or_404(product_id)
    rating = int(request.form.get("rating", 5))
    if not 1 <= rating <= 5:
        abort(400)
    db.session.add(
        Review(
            product_id=p.id,
            vendor_id=p.vendor_id,
            reviewer_name=(request.form.get("reviewer_name") or "Customer").strip()[:120],
            rating=rating,
            comment=(request.form.get("comment") or "").strip()[:1000],
        )
    )
    db.session.commit()
    return redirect(f"/product/{p.id}#reviews")


@bp.route("/go/whatsapp/<int:product_id>")
def go_whatsapp(product_id):
    p = Product.query.get_or_404(product_id)
    track(p.vendor_id, "whatsapp_click", p.id)
    phone = "".join(c for c in p.vendor.user.phone if c.isdigit())
    if phone.startswith("0"):
        phone = "256" + phone[1:]
    text = f"Hi {p.vendor.shop_name}, I saw '{p.name}' on MyMarket.ug"
    return redirect(f"https://wa.me/{phone}?text={text.replace(' ', '%20')}")


@bp.route("/go/call/<int:product_id>")
def go_call(product_id):
    p = Product.query.get_or_404(product_id)
    track(p.vendor_id, "call_click", p.id)
    return redirect(f"tel:{p.vendor.user.phone}")


@bp.route("/go/ad/<int:campaign_id>")
def go_ad(campaign_id):
    c = AdCampaign.query.get_or_404(campaign_id)
    c.clicks = (c.clicks or 0) + 1
    db.session.commit()
    if c.product_id:
        return redirect(f"/product/{c.product_id}")
    return redirect(f"/shop/{c.vendor.slug}")


@bp.route("/market-days")
def market_days():
    upcoming = (
        MarketDay.query.filter(MarketDay.date >= date.today())
        .order_by(MarketDay.date)
        .all()
    )
    return render_template("market_days.html", days=upcoming)


@bp.route("/api/push/public-key")
def push_public_key():
    return jsonify({"key": current_app.config.get("VAPID_PUBLIC_KEY", "")})


@bp.route("/sw.js")
def service_worker():
    return (
        current_app.send_static_file("sw.js"),
        200,
        {"Content-Type": "application/javascript", "Service-Worker-Allowed": "/"},
    )
