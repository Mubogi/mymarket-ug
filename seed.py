"""Seed script: categories, sample market days, demo data.
Usage: python seed.py
"""
from datetime import date, timedelta

from app import create_app
from app.extensions import db
from app.models import MarketDay, Product, Spotlight, User, Vendor
from app.utils import unique_slug

app = create_app()

# Category-appropriate placeholder images so fresh installs look good before
# vendors upload their own photos.
DEMO_IMAGES = {
    "Tecno Spark 20": "https://images.unsplash.com/photo-1598327105666-5b89351aff97?w=600&fit=crop",
    "iPhone 11 (Used)": "https://images.unsplash.com/photo-1592750475338-74b7b21085ab?w=600&fit=crop",
    "Phones": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600&fit=crop",
    "Clothes": "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=600&fit=crop",
    "Shoes": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&fit=crop",
    "Bags": "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?w=600&fit=crop",
    "Electronics": "https://images.unsplash.com/photo-1498049794561-7780e7231661?w=600&fit=crop",
}


def _demo_image(product):
    return (
        DEMO_IMAGES.get(product.name)
        or DEMO_IMAGES.get(product.category)
        or DEMO_IMAGES["Electronics"]
    )


with app.app_context():
    # The 5 core categories are defined in app.models.CATEGORIES and offered
    # in all forms. Seed demo market days below.
    if MarketDay.query.count() == 0:
        days = [
            ("Mbarara", "Mbarara Main Market", date.today() + timedelta(days=2), 2000),
            ("Kampala", "Owino Market", date.today() + timedelta(days=5), 5000),
            ("Gulu", "Gulu Central Market", date.today() + timedelta(days=9), 3000),
            ("Jinja", "Jinja Market", date.today() + timedelta(days=14), 2000),
        ]
        for city, name, d, fee in days:
            db.session.add(MarketDay(city=city, market_name=name, date=d, fee_amount=fee))
        print("Seeded 4 market days")

    # Demo vendor (active & verified) with products for first-time preview.
    if not User.query.filter_by(email="demo@mymarket.ug").first():
        u = User(name="Demo Vendor", phone="0772123456", email="demo@mymarket.ug")
        u.set_password("demo123")
        db.session.add(u)
        db.session.flush()
        v = Vendor(
            user_id=u.id,
            shop_name="Kampala Phones Hub",
            slug=unique_slug("Kampala Phones Hub"),
            description="Best phones & accessories in Kampala.",
            location_city="Kampala",
            location_detail="Nakasero Market, Stall 23",
            is_verified=True,
            is_active=True,
        )
        db.session.add(v)
        db.session.flush()
        demo_products = [
            ("Tecno Spark 20", "8GB RAM, 128GB storage", 420000, "Phones"),
            ("iPhone 11 (Used)", "Good condition, 64GB", 950000, "Phones"),
            ("Ankara Dress", "Beautiful print, all sizes", 65000, "Clothes"),
            ("Sneakers", "Comfortable running shoes", 80000, "Shoes"),
            ("Leather Handbag", "Genuine leather", 120000, "Bags"),
            ("Bluetooth Speaker", "Loud and clear, 12h battery", 90000, "Electronics"),
        ]
        for name, desc, price, cat in demo_products:
            db.session.add(
                Product(
                    vendor_id=v.id,
                    name=name,
                    description=desc,
                    price=price,
                    category=cat,
                    image_url=DEMO_IMAGES.get(name) or DEMO_IMAGES.get(cat),
                )
            )
        db.session.commit()
        print("Seeded demo vendor with 6 products")

    # Give the demo products images if missing (idempotent), so the homepage
    # and Spotlight rail look alive on a fresh deploy.
    for p in Product.query.all():
        if not p.image_url:
            p.image_url = _demo_image(p)
    db.session.commit()

    # Activate a product + shop spotlight for today and the next two days so the
    # homepage "Star Spotlight Picks" rail has content immediately.
    today = date.today()
    demo_vendor = Vendor.query.filter_by(shop_name="Kampala Phones Hub").first()
    if demo_vendor and not Spotlight.query.filter(
        Spotlight.day == today, Spotlight.status == "active"
    ).first():
        products = Product.query.filter_by(vendor_id=demo_vendor.id).all()
        if products:
            slot_days = [today, today + timedelta(days=1), today + timedelta(days=2)]
            for i, day in enumerate(slot_days):
                pid = products[i % len(products)].id
                db.session.add(
                    Spotlight(
                        vendor_id=demo_vendor.id,
                        kind="product",
                        product_id=pid,
                        day=day,
                        status="active",
                    )
                )
            db.session.add(
                Spotlight(
                    vendor_id=demo_vendor.id, kind="shop", day=today, status="active"
                )
            )
            db.session.commit()
            print("Seeded Spotlight picks for today + 2 days")
    print("Seed complete.")
