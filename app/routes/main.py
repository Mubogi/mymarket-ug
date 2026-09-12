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

from ..extensions import db, limiter
from ..models import (
    AdCampaign,
    Analytics,
    CATEGORIES,
    CITIES,
    DISTRICT_COORDS,
    MarketDay,
    Order,
    Product,
    Review,
    Spotlight,
    Vendor,
)
from ..utils import boosted_first, escape_like, track

DISTANCE_KM_PER_DEG = 111.0


def _nearest_district(lat, lon):
    """Return the district nearest to lat/lon plus distance in km."""
    best_city, best_d = None, 1e9
    for city, (clat, clon) in DISTRICT_COORDS.items():
        d = ((clat - lat) ** 2 + (clon - lon) ** 2) ** 0.5 * DISTANCE_KM_PER_DEG
        if d < best_d:
            best_city, best_d = city, d
    return best_city, best_d


def _geo_city_from_request():
    """Best-effort city hint from ?near=(lat,lon) (set by the browser's geolocation API).

    We deliberately keep this on the client: the browser Geo API knows the user's
    location without shipping any external IP-geolocation dependency. Cloudflare can
    still narrow to country (adds no false-positive districts for non-Ugandans).
    """
    near = request.args.get("near", "").strip()
    if near:
        try:
            lat, lon = map(float, near.split(","))
            return _nearest_district(lat, lon)
        except (ValueError, TypeError):
            pass
    return None, None


def _has_active_filters(q, city, category, sort_by, deal, min_price, max_price, stock, verified, near):
    return any(
        [
            q,
            city,
            category,
            sort_by,
            deal,
            min_price is not None,
            max_price is not None,
            stock,
            verified,
            near,
        ]
    )

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

    # Price / availability / verified toggles
    try:
        min_price = float(request.args.get("min", "")) if request.args.get("min") else None
    except ValueError:
        min_price = None
    try:
        max_price = float(request.args.get("max", "")) if request.args.get("max") else None
    except ValueError:
        max_price = None
    stock = request.args.get("stock", "") == "1"
    verified = request.args.get("verified", "") == "1"

    # Browser-geolocated district, e.g. ?near=0.3476,32.5825
    near_city, _ = _geo_city_from_request()
    geo_detected = bool(near_city)
    if near_city and not city:
        city = near_city

    qry = _visible_products()
    if q:
        like = f"%{escape_like(q)}%"
        qry = qry.filter(
            db.or_(
                Product.name.ilike(like),
                Product.description.ilike(like),
                Vendor.shop_name.ilike(like),
            )
        )
    if city and city in CITIES:
        qry = qry.filter(Vendor.location_city == city)
    if category:
        qry = qry.filter(Product.category == category)
    if min_price is not None:
        qry = qry.filter(Product.price >= min_price)
    if max_price is not None:
        qry = qry.filter(Product.price <= max_price)
    if stock:
        qry = qry.filter(db.or_(Product.stock.is_(None), Product.stock > 0))
    if verified:
        qry = qry.filter(Vendor.is_verified.is_(True))
    if deal:
        qry = qry.filter(Product.discount > 0)

    explicit_sort = sort_by
    if sort_by == "price_asc":
        qry = qry.order_by(Product.price.asc())
    elif sort_by == "price_desc":
        qry = qry.order_by(Product.price.desc())
    elif sort_by == "newest":
        qry = qry.order_by(Product.created_at.desc())
    elif sort_by == "popular":
        qry = qry.order_by(Product.views_count.desc())
    else:
        # Default: boosted first, then newest
        qry = qry.order_by(
            db.desc(Product.is_boosted), db.desc(Product.created_at)
        )
        explicit_sort = ""

    filtered_count = qry.count()
    products = qry.limit(200).all()
    # Only re-sort by boosted/verified when there's no explicit sort — otherwise
    # an explicit price/newest sort must be honored exactly.
    if not explicit_sort:
        products = boosted_first(products)

    # When the user is actively filtering, hide sideline rails (Trending/Deals) —
    # they confused "shows all products" and made filters look broken.
    has_filters = _has_active_filters(
        q, city, category, explicit_sort, deal,
        min_price, max_price, stock, verified, near_city,
    )

    trending = deals = featured_shops = []
    if not has_filters:
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
    product_count = filtered_count or _visible_products().count() or 0

    # Spotlight rail: respect city/category filters so it isn't a mix that
    # contradicts the filtered grid (which made "shows all" feel true).
    spotlight_q = Spotlight.query.filter(Spotlight.status == "active")
    if city and city in CITIES:
        spotlight_q = spotlight_q.join(Vendor, Vendor.id == Spotlight.vendor_id).filter(
            Vendor.location_city == city
        )
    if category:
        spotlight_q = spotlight_q.filter(
            db.or_(Spotlight.kind == "shop", Spotlight.product_id.in_(
                db.session.query(Product.id).filter(Product.category == category)
            ))
        )
    # Today's features first, then upcoming ones. Cap at 6 to keep the grid tight.
    today = date.today()
    spotlights = spotlight_q.order_by(
        db.case((Spotlight.day == today, 0), else_=1),
        Spotlight.day.asc(),
        Spotlight.id.desc(),
    ).limit(6).all()

    geo_city = near_city if near_city else (city if city in CITIES else "")
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
            min_price=min_price,
            max_price=max_price,
            stock=stock,
            verified=verified,
            has_filters=has_filters,
            geo_city=geo_city,
            geo_detected=geo_detected,
            near=request.args.get("near", ""),
            spotlights=spotlights,
        )
    )
    # Let Cloudflare/other CDNs cache the homepage for anonymous visitors
    if not current_user.is_authenticated and not has_filters:
        response.headers["Cache-Control"] = "public, max-age=60, s-maxage=120"
    return response


@bp.route("/api/nearby")
def api_nearby():
    """Return the closest district + km for a browser geolocation coordinate."""
    lat, lon = request.args.get("lat", ""), request.args.get("lon", "")
    try:
        la, lo = float(lat), float(lon)
    except (TypeError, ValueError):
        return jsonify({"error": "bad coordinates", "district": None, "km": None}), 400
    if not (-90 <= la <= 90) or not (-180 <= lo <= 180):
        return jsonify({"error": "bad coordinates", "district": None, "km": None}), 400
    district, km = _nearest_district(la, lo)
    return jsonify({"district": district, "km": round(km, 1)})


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
    sort_by = request.args.get("sort", "")
    qry = Product.query.filter(
        Product.vendor_id == vendor.id,
        Product.is_hidden.is_(False),
    )
    if q:
        like = f"%{escape_like(q)}%"
        qry = qry.filter(
            db.or_(Product.name.ilike(like), Product.description.ilike(like))
        )
    if sort_by == "price_asc":
        qry = qry.order_by(Product.price.asc())
    elif sort_by == "price_desc":
        qry = qry.order_by(Product.price.desc())
    elif sort_by == "newest":
        qry = qry.order_by(Product.created_at.desc())
    elif sort_by == "popular":
        qry = qry.order_by(Product.views_count.desc())
    else:
        qry = qry.order_by(db.desc(Product.is_boosted), db.desc(Product.created_at))
    products = qry.limit(200).all()
    if not sort_by:
        products = boosted_first(products)
    product_count = qry.count()
    avg_rating = None
    rating_count = 0
    reviews = [r for r in vendor.reviews if r.product and not r.product.is_hidden]
    if reviews:
        avg_rating = round(sum(r.rating for r in reviews) / len(reviews), 1)
        rating_count = len(reviews)

    # Coordinates for "Open in Maps" (from the district table, gracefully degrades)
    coords = DISTRICT_COORDS.get(vendor.location_city or "")
    lat = coords[0] if coords else ""
    lon = coords[1] if coords else ""

    return render_template(
        "shop.html",
        vendor=vendor,
        products=products,
        product_count=product_count,
        avg_rating=avg_rating,
        rating_count=rating_count,
        q=q,
        sort_by=sort_by,
        lat=lat,
        lon=lon,
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
            "discounted_price": f"{p.discounted_price:,}",
            "discount": p.discount or 0,
            "stock": p.stock,
            "shop_url": f"/shop/{p.vendor.slug}",
            "shop_name": p.vendor.shop_name,
            "verified": bool(p.vendor and p.vendor.is_verified),
        }
        for p in by_id.values()
    ]
    return jsonify(data)


@bp.route("/order/<int:order_id>")
def order_confirmation(order_id):
    """Confirmation + tracking page shown after placing an order."""
    order = Order.query.get_or_404(order_id)
    return render_template("order_tracking.html", order=order)


@bp.route("/orders/lookup", methods=["GET", "POST"])
def order_lookup():
    """Find all orders for a given phone number (buyer "My Orders")."""
    if request.method == "POST":
        phone = (request.form.get("phone") or "").strip()
        if not phone:
            flash("Enter the phone you used to order.", "error")
            return redirect(url_for("main.order_lookup"))
        orders = (
            Order.query.filter_by(customer_phone=phone)
            .order_by(Order.created_at.desc())
            .all()
        )
        return render_template(
            "order_lookup.html", orders=orders, phone=phone, categories=CATEGORIES
        )
    return render_template("order_lookup.html", orders=None, categories=CATEGORIES, cities=CITIES)


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
    if p.vendor and p.vendor.is_verified:
        text += "\n(Verified shop on MyMarket.ug)"
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
    phone = "".join(
        c for c in (p.vendor.whatsapp or p.vendor.phone or (p.vendor.user.phone if p.vendor.user else "")) if c.isdigit()
    )
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


@bp.route("/sitemap.xml")
def sitemap():
    from xml.sax.saxutils import escape

    base = f"https://{current_app.config.get('BASE_DOMAIN', 'mymarket.ug')}"
    pages = ["/", "/favorites", "/market-days", "/orders/lookup"]
    products = _visible_products().all()
    shops = Vendor.query.filter_by(is_active=True).all()
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path in pages:
        out.append(f"  <url><loc>{base}{path}</loc><priority>0.8</priority></url>")
    for p in products:
        out.append(f"  <url><loc>{base}/product/{p.id}</loc><priority>0.9</priority></url>")
    for s in shops:
        out.append(f"  <url><loc>{base}/shop/{escape(s.slug)}</loc><priority>0.7</priority></url>")
    out.append("</urlset>")
    return "\n".join(out), 200, {"Content-Type": "application/xml"}


@bp.route("/robots.txt")
def robots():
    base = f"https://{current_app.config.get('BASE_DOMAIN', 'mymarket.ug')}"
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return body, 200, {"Content-Type": "text/plain"}
