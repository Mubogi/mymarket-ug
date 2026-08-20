from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="vendor")  # vendor|admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vendor = db.relationship("Vendor", back_populates="user", uselist=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"


class Vendor(db.Model):
    __tablename__ = "vendors"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    shop_name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    logo = db.Column(db.String(255))
    description = db.Column(db.Text)
    location_city = db.Column(db.String(60), default="Kampala")  # district
    location_area = db.Column(db.String(120))  # division/ward/town area
    location_detail = db.Column(db.String(200))  # building / landmark
    shop_no = db.Column(db.String(40))  # stall / shop number
    is_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=False)
    subscription_expires_at = db.Column(db.DateTime)
    products_uploaded_this_month = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="vendor")
    products = db.relationship(
        "Product", back_populates="vendor", cascade="all, delete-orphan"
    )

    @property
    def subscription_active(self):
        return (
            self.subscription_expires_at is not None
            and self.subscription_expires_at > datetime.utcnow()
        )


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Integer, nullable=False)  # UGX
    image_url = db.Column(db.String(255))
    category = db.Column(db.String(60), default="Electronics")
    views_count = db.Column(db.Integer, default=0)
    is_boosted = db.Column(db.Boolean, default=False)
    boost_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vendor = db.relationship("Vendor", back_populates="products")

    @property
    def boosted_now(self):
        return (
            self.is_boosted
            and self.boost_expires_at is not None
            and self.boost_expires_at > datetime.utcnow()
        )

    @property
    def avg_rating(self):
        rs = self.reviews
        if not rs:
            return None
        return round(sum(r.rating for r in rs) / len(rs), 1)


class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    # setup|pro_upload|subscription|boost|market_day|ad_campaign
    type = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending|paid
    reference = db.Column(db.String(120))
    tx_ref = db.Column(db.String(120), unique=True)  # Flutterwave transaction ref
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)

    vendor = db.relationship("Vendor", backref="payments")


class MarketDay(db.Model):
    __tablename__ = "market_days"
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(60), nullable=False)
    market_name = db.Column(db.String(120), nullable=False)
    date = db.Column(db.Date, nullable=False)
    fee_amount = db.Column(db.Integer, default=2000)

    bookings = db.relationship(
        "MarketDayBooking", back_populates="market_day", cascade="all, delete-orphan"
    )


class MarketDayBooking(db.Model):
    __tablename__ = "market_day_bookings"
    id = db.Column(db.Integer, primary_key=True)
    market_day_id = db.Column(db.Integer, db.ForeignKey("market_days.id"), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    payment_id = db.Column(db.Integer, db.ForeignKey("payments.id"))
    status = db.Column(db.String(20), default="pending")  # pending|confirmed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    market_day = db.relationship("MarketDay", back_populates="bookings")
    vendor = db.relationship("Vendor", backref="market_day_bookings")


class Analytics(db.Model):
    __tablename__ = "analytics"
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    # shop_view|product_view|whatsapp_click|call_click
    type = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class AdCampaign(db.Model):
    __tablename__ = "ad_campaigns"
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    budget = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="requested")  # requested|active|completed
    ad_copy = db.Column(db.Text)
    platform = db.Column(db.String(40), default="Facebook")  # Facebook|TikTok
    clicks = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vendor = db.relationship("Vendor", backref="ad_campaigns")
    product = db.relationship("Product", backref="ad_campaigns")


class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    reviewer_name = db.Column(db.String(120), default="Customer")
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product", backref="reviews")
    vendor = db.relationship("Vendor", backref="reviews")


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    # 'customer' or 'vendor'
    sender_type = db.Column(db.String(10), default="customer")
    sender_name = db.Column(db.String(120), default="Customer")
    sender_vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"))
    # Identifies a guest customer (or a vendor-to-vendor thread)
    visitor_key = db.Column(db.String(255), index=True)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vendor = db.relationship("Vendor", foreign_keys=[vendor_id], backref="chat_messages")
    sender_vendor = db.relationship("Vendor", foreign_keys=[sender_vendor_id])


class PushSubscription(db.Model):
    __tablename__ = "push_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    endpoint = db.Column(db.Text, unique=True, nullable=False)
    auth = db.Column(db.String(255))
    p256dh = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


CATEGORIES = ["Phones", "Clothes", "Shoes", "Bags", "Electronics"]
CITIES = ["Kampala", "Gulu", "Mbarara", "Mbale", "Arua", "Jinja"]
