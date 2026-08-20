"""Seed demo vendors with real products.

- Jordan Design Hub (6 tech products with real JD Hub content)
- Prosy Styles (fashion items)
- Updates existing vendors; does not duplicate.

Run: python seed_jdhub.py
"""
import os

os.environ.setdefault("FLASK_DEBUG", "1")

from app import create_app
from app.extensions import db
from app.models import Payment, Product, User, Vendor
from app.utils import unique_slug
from datetime import datetime, timedelta

def run_seed_demo():
    """Seed all demo vendors + products. Safe to re-run — never duplicates."""

    from datetime import datetime, timedelta

    app = create_app()
    with app.app_context():
        jdhub_products, prosy_products = _get_product_data()

        # Jordan Design Hub
        vendor = _seed_vendor(
            "Jordan Design Hub",
            "jordandesignhub@gmail.com",
            "jdhub2026",
            "Mubogi Gastavas Jordan",
            "256754687597",
            "Kampala",
            "Kampala Central",
            "Kampala City",
            "Suite 4",
            "Uganda's all-in-one tech ecosystem — build, learn, and grow. "
            "We build custom web & mobile apps (Android & iOS), run an online academy, "
            "offer ICT services, media training, and AI optimization training.",
            "/static/img-jdhub/jdhub-logo.png",
        )
        _seed_products(vendor, jdhub_products)

        # Kampala Phones Hub (demo vendor)
        demo = _seed_vendor(
            "Kampala Phones Hub",
            "demo@mymarket.ug",
            "demo123",
            "Demo Vendor",
            "0772123456",
            "Kampala",
            "Nakasero",
            "Nakasero Market",
            "Stall 23",
            "Best phones & accessories in Kampala.",
            None,
        )
        demo_products = [
            {"name": "Tecno Spark 20", "price": 420000, "category": "Phones", "image_url": None, "description": "8GB RAM, 128GB storage"},
            {"name": "iPhone 11 (Used)", "price": 950000, "category": "Phones", "image_url": None, "description": "Good condition, 64GB"},
            {"name": "Bluetooth Speaker", "price": 90000, "category": "Electronics", "image_url": None, "description": "Loud and clear, 12h battery"},
        ]
        _seed_products(demo, demo_products)

        # Prosy Styles (fashion)
        prosy = Vendor.query.filter_by(slug="prosy-styles").first()
        if prosy:
            _seed_products(prosy, prosy_products)

        print("Seeded Jordan Design Hub + Prosy Styles")


def _get_product_data():
    """Returns (jdhub_products, prosy_products, demo_products) as lists of dicts."""
    return (
        [
            {
                "name": "SACCO Portfolio Quality & Microfinance System",
                "price": 1500000,
                "category": "Electronics",
                "image_url": "/static/img-jdhub/jdhub-sacco.png",
                "description": "Microfinance management for SACCOs — member savings, share capital, loans, repayment schedules, double-entry ledger, and portfolio-quality analytics.",
            },
            {
                "name": "Basic Digital Literacy Course",
                "price": 50000,
                "category": "Electronics",
                "image_url": "/static/img-jdhub/jdhub-digital-literacy.png",
                "description": "Learn computing fundamentals — Windows, Word, Excel, email, internet safety. Perfect for beginners. Online on Google Meet with certificate.",
            },
            {
                "name": "Custom Website Design & Development",
                "price": 800000,
                "category": "Electronics",
                "image_url": "/static/img-jdhub/jdhub-web-design.png",
                "description": "Professional mobile-first websites for businesses and NGOs. Django/Flask/PWA with free support for 30 days.",
            },
            {
                "name": "Offline-First School Management System",
                "price": 2000000,
                "category": "Electronics",
                "image_url": "/static/img-jdhub/jdhub-logo.png",
                "description": "School digitisation: enrolment, attendance, grading, fees, parent communication. Works without internet!",
            },
            {
                "name": "Attendance Hub — Event & Church Kiosk",
                "price": 500000,
                "category": "Electronics",
                "image_url": "/static/img-jdhub/jdhub-logo.png",
                "description": "Church and event attendance kiosk. Desktop + web + Android. No internet needed.",
            },
            {
                "name": "AI Optimization & Prompt Engineering",
                "price": 150000,
                "category": "Electronics",
                "image_url": "/static/img-jdhub/jdhub-logo.png",
                "description": "Learn to use AI tools like ChatGPT effectively. Prompt engineering, content creation, business automation.",
            },
        ],
        [
            {
                "name": "Kitenge Dress",
                "price": 55000,
                "category": "Clothes",
                "image_url": None,
                "description": "Beautiful African print dress, all sizes.",
            },
            {
                "name": "High Heels",
                "price": 85000,
                "category": "Shoes",
                "image_url": None,
                "description": "Stylish heels, size 36-41.",
            },
            {
                "name": "Clutch Bag",
                "price": 40000,
                "category": "Bags",
                "image_url": None,
                "description": "Evening clutch bag with gold chain.",
            },
            {
                "name": "Denim Jacket",
                "price": 70000,
                "category": "Clothes",
                "image_url": None,
                "description": "Classic blue denim jacket.",
            },
        ],
    )


def _seed_vendor(name, email, password, owner_name, phone, city, area, detail, shop_no, description, logo):
    vendor = Vendor.query.filter_by(user_id=User.query.filter_by(email=email).first().id if User.query.filter_by(email=email).first() else None).first()  # complex check
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(name=owner_name, phone=phone, email=email, role="vendor")
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

    vendor = Vendor.query.filter_by(user_id=user.id).first()
    if not vendor:
        vendor = Vendor(
            user_id=user.id,
            shop_name=name,
            slug=unique_slug(name),
            description=description,
            location_city=city,
            location_area=area,
            location_detail=detail,
            shop_no=shop_no,
            is_verified=True,
            is_active=True,
            logo=logo,
        )
        vendor.subscription_expires_at = datetime.utcnow() + timedelta(days=365)
        db.session.add(vendor)
        db.session.commit()
    return vendor


def _seed_products(vendor, products):
    for p_data in products:
        exists = Product.query.filter_by(vendor_id=vendor.id, name=p_data["name"]).first()
        if not exists:
            db.session.add(
                Product(
                    vendor_id=vendor.id,
                    name=p_data["name"],
                    description=p_data["description"],
                    price=p_data["price"],
                    category=p_data["category"],
                    image_url=p_data["image_url"],
                    views_count=0,
                )
            )
    db.session.commit()


if __name__ == "__main__":
    run_seed_demo()

