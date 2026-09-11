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
    url_for,
)
from flask_login import current_user

from ..extensions import db
from ..models import (
    AdCampaign,
    Analytics,
    CATEGORIES,
    CITIES,
    MarketDay,
    Product,
    Review,
    Vendor,
)
from ..extensions import limiter
from ..utils import boosted_first, escape_like, track

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


def _visible_products():
    """Base query: only active vendors' visible products."""
    return Product.query.join(Vendor).filter(
        Vendor.is_active.is_(True),
        Product.is_hidden.is_(False),
    )


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
    sort_by = request.args.get("sort", "")
    deal = request.args.get("deal", "")

    qry = _visible_products().order_by(
        db.desc(Product.is_boosted), db.desc(Product.created_at)
    )
    if q:
        like = f"%{escape_like(q)}%"
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
    if sort_by == "price_asc":
        qry = qry.order_by(Product.price.asc())
    elif sort_by == "price_desc":
        qry = qry.order_by(Product.price.desc())
    elif sort_by == "newest":
        qry = qry.order_by(Product.created_at.desc())
    elif sort_by == "popular":
        qry = qry.order_by(Product.views_count.desc())
    if deal:
        qry = qry.filter(Product.discount > 0)

    products = boosted_first(qry.limit(200).all())

    # Trending products (most viewed, from active vendors)
    trending = (
        _visible_products()
        .order_by(Product.views_count.desc())
        .limit(8)
        .all()
    )

    # Deals of the day (discounted products)
    deals = (
        _visible_products()
        .filter(Product.discount > 0, Product.discount.isnot(None))
        .order_by(db.desc(Product.discount))
        .limit(10)
        .all()
    )

    # Featured shops: active+verified, with at least 3 products, most shop views
    shop_views_subq = (
        db.session.query(
            Analytics.vendor_id,
            db.func.count(Analytics.id).label("sv"),
        )
        .filter(Analytics.type == "shop_view", Analytics.vendor_id.isnot(None))
        .group_by(Analytics.vendor_id)
        .subquery()
    )
    featured_shops = (
        Vendor.query.filter(
            Vendor.is_active.is_(True),
            Vendor.is_verified.is_(True),
        )
        .outerjoin(shop_views_subq, shop_views_subq.c.vendor_id == Vendor.id)
        .order_by(db.desc(shop_views_subq.c.sv), Vendor.created_at.desc())
        .limit(6)
        .all()
    )
    featured_shops = [v for v in featured_shops if len(v.products or []) >= 3][:6]

    # Shop count for hero stat
    vendor_count = Vendor.query.filter_by(is_active=True).count()
    product_count = _visible_products().count() or 0

    response = make_response(
        render_template(
            "index.html",
            products=products,
            trending=trending,
            deals=deals,
            featured_shops=featured_shops,
            vendor_count=vendor_count,
            product_count=product_count,
            categories=CATEGORIES,
            cities=CITIES,
            banner_days=upcoming_market_banner(),
            q=q,
            city=city,
            category=category,
            sort_by=sort_by,
            deal=deal,
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
    # Only visible products; optional in-shop search
    q = request.args.get("q", "").strip()
    qry = Product.query.filter(
        Product.vendor_id == vendor.id,
        Product.is_hidden.is_(False),
    )
    if q:
        like = f"%{escape_like(q)}%"
        qry = qry.filter(
            db.or_(Product.name.ilike(like), Product.description.ilike(like))
        )
    products = boosted_first(qry.limit(200).all())
    product_count = qry.count()
    avg_rating = None
    rating_count = 0
    reviews = [r for r in vendor.reviews if r.product and not r.product.is_hidden]
    if reviews:
        avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1)
        rating_count = len(reviews)
    return render_template(
        "shop.html",
        vendor=vendor,
        products=products,
        product_count=product_count,
        avg_rating=avg_rating,
        rating_count=rating_count,
        q=q,
        basedomain=True,
    )


@bp.route("/product/<int:product_id>")
def product_view(product_id):
    p = Product.query.get_or_404(product_id)
    if p.is_hidden or not p.vendor.is_active:
        abort(404)
    p.views_count = (p.views_count or 0) + 1
    db.session.commit()
    track(p.vendor_id, "product_view", p.id)
    related = (
        _visible_products()
        .filter(Product.category == p.category, Product.id != p.id)
        .order_by(db.desc(Product.created_at))
        .limit(6)
        .all()
    )
    return render_template("product.html", product=p, related=related)


@bp.route("/favorites")
def favorites():
    """Favorites are stored client-side; this renders the page (empty list arrives via JS)."""
    return render_template("favorites.html", categories=CATEGORIES, cities=CITIES)


@bp.route("/api/favorites")
def favorites_api():
    """Return saved products data for the favorites page."""
    ids = request.args.get("ids", "")
    try:
        id_list = [int(i) for i in ids.split(",") if i.strip()]
    except (ValueError, TypeError):
        return jsonify([])
    if not id_list:
        return jsonify([])
    q = _visible_products()
    items = q.filter(Product.id.in_(id_list)).all()
    by_id = {}
    for p in items:
        by_id[p.id] = p
    data = [
        {
            "id": p.id,
            "name": p.name,
            "image_url": p.image_url,
            "price_formatted": f"{p.price:,}",
        }
        for p in by_id.values()
    ]
    return jsonify(data)


@bp.route("/go/order/<int:product_id>")
def go_order(product_id):
    """One-tap order intent: opens WhatsApp with a pre-filled order message."""
    p = Product.query.get_or_404(product_id)
    if p.is_hidden or not p.vendor.is_active:
        abort(404)
    track(p.vendor_id, "order_click", p.id)
    name = request.args.get("name", "").strip()
    qty = request.args.get("qty", "1").strip() or "1"
    notes = request.args.get("notes", "").strip()
    phone = "".join(c for c in (p.vendor.whatsapp or p.vendor.user.phone) if c.isdigit())
    if phone.startswith("0"):
        phone = "256" + phone[1:]
    text = f"Hi {p.vendor.shop_name}, I'd like to order: {p.name} (UGX {p.price:,})\nQty: {qty}"
    if notes:
        text += f"\nNotes: {notes}"
    text += f"\nFrom MyMarket.ug product: https://{current_app.config['BASE_DOMAIN']}/product/{p.id}"
    return redirect(f"https://wa.me/{phone}?text={text.replace(' ', '%20').replace('\n', '%0A')}")


@bp.route("/refer/<slug>")
def refer(slug):
    """Redirect a referral link to signup, carrying the referrer slug."""
    v = Vendor.query.filter_by(slug=slug).first()
    if not v:
        abort(404)
    return redirect(url_for("vendor.signup", ref=v.slug))


@bp.route("/product/<int:product_id>/review", methods=["POST"])
@limiter.limit("10 per hour")
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
    raw = p.vendor.whatsapp or p.vendor.phone or (p.vendor.user.phone if p.vendor.user else "")
    if phone.startswith("0"):
        phone = "256" + phone[1:]
    text = f"Hi {p.vendor.shop_name}, I saw '{p.name}' on MyMarket.ug"
    return redirect(f"https://wa.me/{phone}?text={text.replace(' ', '%20')}")


@bp.route("/go/call/<int:product_id>")
def go_call(product_id):
    p = Product.query.get_or_404(product_id)
    track(p.vendor_id, "call_click", p.id)
    raw = p.vendor.phone or p.vendor.whatsapp or (p.vendor.user.phone if p.vendor.user else "")
    return redirect(f"tel:{raw}")


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
