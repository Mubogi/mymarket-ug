"""Seed script: categories, sample market days, demo data.
Usage: python seed.py
"""
from datetime import date, timedelta

from app import create_app
from app.extensions import db
from app.models import MarketDay, User, Vendor, Product
from app.utils import unique_slug

app = create_app()

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
                Product(vendor_id=v.id, name=name, description=desc, price=price, category=cat)
            )
        db.session.commit()
        print("Seeded demo vendor with 6 products")
    print("Seed complete.")
