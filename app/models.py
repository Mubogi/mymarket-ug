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
    phone = db.Column(db.String(30))  # public contact phone (WhatsApp)
    whatsapp = db.Column(db.String(30))  # separate WhatsApp number if different
    email = db.Column(db.String(120))  # public contact email
    opening_hours = db.Column(db.String(160))  # e.g. "Mon–Sat 9am–6pm"
    facebook = db.Column(db.String(255))  # social links shown on the shop mini-site
    instagram = db.Column(db.String(255))
    tiktok = db.Column(db.String(255))
    twitter = db.Column(db.String(255))
    website = db.Column(db.String(255))
    referred_by = db.Column(db.Integer, db.ForeignKey("vendors.id"))
    credit = db.Column(db.Integer, default=0, nullable=False)  # UGX referral/other credit
    flw_subaccount_id = db.Column(db.String(80))  # Flutterwave subaccount for merchant splits
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", back_populates="vendor")
    referrer = db.relationship("Vendor", remote_side=[id], foreign_keys=[referred_by], backref="referrals")
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
    stock = db.Column(db.Integer, default=None)  # None = unlimited; 0 = out of stock
    discount = db.Column(db.Integer, default=0)  # percent 0-90
    is_hidden = db.Column(db.Boolean, default=False)  # admin moderation hide
    is_boosted = db.Column(db.Boolean, default=False)
    boost_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vendor = db.relationship("Vendor", back_populates="products")

    @property
    def out_of_stock(self):
        return self.stock == 0

    @property
    def discounted_price(self):
        if not self.discount:
            return self.price
        return round(self.price * (100 - self.discount)) / 100

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
    merchant_notify = db.Column(db.Boolean, default=False)  # merchant confirmed via SMS/push

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


class Order(db.Model):
    """A customer purchase, paid via Flutterwave checkout or cash-on-delivery."""
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    qty = db.Column(db.Integer, default=1, nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # product subtotal (incl. discount)
    delivery_fee = db.Column(db.Integer, default=0)
    payment_method = db.Column(db.String(20), default="flutterwave")  # flutterwave|cod
    customer_name = db.Column(db.String(120))
    customer_phone = db.Column(db.String(30), index=True)
    customer_email = db.Column(db.String(120))
    customer_address = db.Column(db.String(255))
    status = db.Column(db.String(20), default="pending")  # pending|confirmed|delivered|paid|cancelled
    tx_ref = db.Column(db.String(120), unique=True)
    merchant_notify = db.Column(db.Boolean, default=False)  # vendor notified of new sale
    buyer_notify = db.Column(db.Boolean, default=False)  # buyer notified of status change
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime)

    product = db.relationship("Product", backref="orders")
    vendor = db.relationship("Vendor", backref="orders")


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




class Spotlight(db.Model):
    __tablename__ = "spotlights"
    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    kind = db.Column(db.String(10), default="product")  # product|shop
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"))
    day = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), default="requested")  # requested|active|expired|rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    vendor = db.relationship("Vendor", backref="spotlights")
    product = db.relationship("Product", backref="spotlights")


class Review(db.Model):
    __tablename__ = "reviews"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendors.id"), nullable=False)
    reviewer_name = db.Column(db.String(120), default="Customer")
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.Text)
    reply = db.Column(db.Text)  # vendor reply
    replied_at = db.Column(db.DateTime)
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
# The full list of districts/areas used by the location picker — keep in sync with
# app/static/js/uganda-locations.js. Used for the city/district filter + geolocation.
CITIES = [
    "Kampala", "Wakiso", "Jinja", "Mbarara", "Gulu", "Mbale", "Arua", "Masaka",
    "Lira", "Fort Portal", "Kabale", "Tororo", "Soroti", "Hoima", "Kasese",
    "Mityana", "Mukono", "Iganga", "Luwero", "Moroto", "Kitgum", "Busia", "Other",
]

# Approximate lat/lng (decimal degrees) for geolocation resolution.
DISTRICT_COORDS = {
    "Kampala": (0.3476, 32.5825),
    "Wakiso": (0.4041, 32.4597),
    "Jinja": (0.4244, 33.2036),
    "Mbarara": (-0.6072, 30.6545),
    "Gulu": (2.7720, 32.2985),
    "Mbale": (1.0784, 34.1750),
    "Arua": (3.0301, 30.9072),
    "Masaka": (-0.3410, 31.7340),
    "Lira": (2.2490, 32.8999),
    "Fort Portal": (0.6714, 30.2752),
    "Kabale": (-1.2490, 29.9897),
    "Tororo": (0.7000, 34.2000),
    "Soroti": (1.7146, 33.6110),
    "Hoima": (1.4356, 31.3435),
    "Kasese": (0.1850, 30.0881),
    "Mityana": (0.4175, 32.0250),
    "Mukono": (0.3533, 32.7553),
    "Iganga": (0.6092, 33.4838),
    "Luwero": (0.8500, 32.4800),
    "Moroto": (2.5333, 34.6667),
    "Kitgum": (3.2833, 32.8833),
    "Busia": (0.4630, 34.0833),
    "Other": (1.0000, 32.5000),
}
