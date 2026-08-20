"""Seed the Jordan Design Hub vendor with real products from the JD Hub repo.

Run: python seed_jdhub.py
"""
import os

os.environ.setdefault("FLASK_DEBUG", "1")

from app import create_app
from app.extensions import db
from app.models import Payment, Product, User, Vendor
from app.utils import unique_slug
from datetime import datetime, timedelta

app = create_app()

JD_PRODUCTS = [
    {
        "name": "SACCO Portfolio Quality & Microfinance System",
        "price": 1500000,
        "category": "Electronics",
        "description": (
            "A microfinance management system for Savings and Credit Cooperatives (SACCOs). "
            "Manages member savings, share capital, loan origination, repayment schedules, "
            "and portfolio-quality analytics — with a double-entry ledger and full audit trail. "
            "Perfect for Ugandan SACCOs looking to digitise. Includes: member onboarding, "
            "savings products (ordinary, fixed, deposits), loan application & approval workflow, "
            "repayment collection with arrears/penalty automation, Portfolio-at-Risk (PAR) "
            "reporting, and immutable audit logs."
        ),
        "image_url": "/static/uploads/jdhub/jdhub-sacco.png",
    },
    {
        "name": "Basic Digital Literacy Course",
        "price": 50000,
        "category": "Electronics",
        "description": (
            "Learn the fundamentals of computing in a friendly, hands-on environment. "
            "Covers: Windows/macOS basics, Microsoft Word, Excel, PowerPoint, email, "
            "internet safety, and file management. Ideal for absolute beginners — "
            "no prior experience needed. Delivered online via Google Meet with a "
            "certificate of completion from Jordan Design Hub Academy."
        ),
        "image_url": "/static/uploads/jdhub/jdhub-digital-literacy.png",
    },
    {
        "name": "Custom Website Design & Development",
        "price": 800000,
        "category": "Electronics",
        "description": (
            "Professional website design and development for businesses, NGOs, and individuals. "
            "We build fast, mobile-first, SEO-ready websites using modern technologies "
            "(Django, Flask, PWA). Packages include: custom design, hosting setup, "
            "domain configuration, SSL, Google Maps integration, WhatsApp chat button, "
            "and 30 days of free support. Your business deserves a professional online presence."
        ),
        "image_url": "/static/uploads/jdhub/jdhub-web-design.png",
    },
    {
        "name": "Offline-First School Management System",
        "price": 2000000,
        "category": "Electronics",
        "description": (
            "Desktop + web platform for schools — runs even without the internet. "
            "A complete school digitisation solution covering enrolment, attendance, grading, "
            "fee collection, and parent communication. Its offline-first architecture ensures "
            "teachers in low-connectivity areas keep working, with automatic synchronisation "
            "when the network returns. Features: role-based dashboards, fee billing & receipts, "
            "termly report cards, QR parent kiosk, hybrid backup (local/USB/cloud), "
            "and hardware-bound licensing."
        ),
        "image_url": "/static/uploads/jdhub/jdhub-school-system.png",
    },
    {
        "name": "Attendance Hub — Event & Church Kiosk",
        "price": 500000,
        "category": "Electronics",
        "description": (
            "Standalone attendance system for churches, conferences, and events. "
            "Available as a Windows desktop app, a web kiosk, and a fully native Android app. "
            "No server, no computer, no internet required — everything runs on the device. "
            "Android edition adds Wi-Fi device linking so multiple phones share one dataset "
            "in real time. Features: one-tap check-in, searchable member database, "
            "session-based tracking, Excel/CSV/PDF exports, and offline SQLite database."
        ),
        "image_url": "/static/uploads/jdhub/jdhub-attendance.png",
    },
    {
        "name": "AI Optimization & Prompt Engineering Training",
        "price": 150000,
        "category": "Electronics",
        "description": (
            "Learn how to use AI tools like ChatGPT, Claude, and Google Gemini effectively. "
            "Covers: prompt engineering basics, AI for content creation, AI for business "
            "automation, and responsible AI use. Practical, hands-on sessions — leave with "
            "real skills you can apply immediately in your work. Certificate provided."
        ),
        "image_url": "/static/uploads/jdhub/jdhub-logo.png",
    },
]

with app.app_context():
    # Check if vendor already exists
    existing = Vendor.query.filter_by(slug="jordan-design-hub").first()
    if existing:
        print("Jordan Design Hub vendor already exists — updating products only.")
        vendor = existing
    else:
        # Create user
        user = User.query.filter_by(email="jordandesignhub@gmail.com").first()
        if not user:
            user = User(
                name="Mubogi Gastavas Jordan",
                phone="256754687597",
                email="jordandesignhub@gmail.com",
                role="vendor",
            )
            user.set_password("jdhub2026")
            db.session.add(user)
            db.session.flush()

        vendor = Vendor(
            user_id=user.id,
            shop_name="Jordan Design Hub",
            slug=unique_slug("Jordan Design Hub"),
            description=(
                "Uganda's all-in-one tech ecosystem — build, learn, and grow. "
                "We build custom web & mobile apps (Android & iOS), run an online academy "
                "with paid courses, offer ICT infrastructure & networking services, "
                "provide media & livestreaming training (OBS, OpenLP), and deliver "
                "AI optimization training. Proudly Ugandan."
            ),
            location_city="Kampala",
            location_area="Kampala Central",
            location_detail="Kampala City",
            shop_no="Suite 4",
            is_verified=True,
            is_active=True,
            logo="/static/uploads/jdhub/jdhub-logo.png",
        )
        vendor.subscription_expires_at = datetime.utcnow() + timedelta(days=365)
        db.session.add(vendor)
        db.session.commit()

        # Create setup payment (marked paid since this is the owner)
        setup_payment = Payment(
            vendor_id=vendor.id,
            amount=10000,
            type="setup",
            status="paid",
            note="Vendor setup fee — Jordan Design Hub",
            paid_at=datetime.utcnow(),
        )
        db.session.add(setup_payment)
        db.session.commit()
        print(f"Created vendor: {vendor.shop_name} (slug: {vendor.slug})")

    # Add products
    for p_data in JD_PRODUCTS:
        exists = Product.query.filter_by(
            vendor_id=vendor.id, name=p_data["name"]
        ).first()
        if exists:
            print(f"  Product exists: {p_data['name']}")
            continue
        p = Product(
            vendor_id=vendor.id,
            name=p_data["name"],
            description=p_data["description"],
            price=p_data["price"],
            image_url=p_data["image_url"],
            category=p_data["category"],
            views_count=0,
        )
        db.session.add(p)
        print(f"  + {p_data['name']}")

    db.session.commit()
    print(f"\nDone! Jordan Design Hub now has {Product.query.filter_by(vendor_id=vendor.id).count()} products.")
    print(f"Vendor login: jordandesignhub@gmail.com / jdhub2026")
    print(f"Shop: /shop/{vendor.slug}")
