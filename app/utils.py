import os
import re
import unicodedata
from datetime import datetime

from flask import current_app
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Analytics, Product, Vendor


def slugify(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value) or "shop"


def unique_slug(name):
    base = slugify(name)
    slug, i = base, 2
    while Vendor.query.filter_by(slug=slug).first():
        slug = f"{base}-{i}"
        i += 1
    return slug


def save_upload(file_storage, max_px=1000, quality=82):
    """Save an uploaded image, downscaled + JPEG-compressed for fast mobile loads."""
    if not file_storage or not file_storage.filename:
        return None
    filename = secure_filename(file_storage.filename)
    name, ext = os.path.splitext(filename)
    if ext.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return None
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    final = f"{slugify(name)[:40]}-{ts}.jpg"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    dest = os.path.join(current_app.config["UPLOAD_FOLDER"], final)
    try:
        from PIL import Image

        img = Image.open(file_storage.stream)
        img.verify()  # reject files that are not really images
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream).convert("RGB")
        img.thumbnail((max_px, max_px))
        img.save(dest, "JPEG", quality=quality, optimize=True)
    except Exception:
        # Never save an unverified upload — blocks disguised HTML/JS payloads
        if os.path.exists(dest):
            os.remove(dest)
        return None
    return f"/static/uploads/{final}"


def escape_like(text):
    """Escape SQL LIKE wildcards in user-supplied search text."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def track(vendor_id, type_, product_id=None):
    db.session.add(Analytics(vendor_id=vendor_id, product_id=product_id, type=type_))
    db.session.commit()


def boosted_first(products):
    """Sort: 1) boosted, 2) verified vendor, 3) newest."""

    def key(p: Product):
        return (
            0 if p.boosted_now else 1,
            0 if (p.vendor and p.vendor.is_verified) else 1,
            -p.created_at.timestamp(),
        )

    return sorted(products, key=key)


def allowed_uploads(vendor):
    """Free limit + 10 extra per paid pro_upload this month."""
    now = datetime.utcnow()
    from .models import Payment

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    paid_extras = Payment.query.filter(
        Payment.vendor_id == vendor.id,
        Payment.type == "pro_upload",
        Payment.status == "paid",
        Payment.created_at >= month_start,
    ).count()
    return current_app.config["FREE_PRODUCT_LIMIT"] + 10 * paid_extras


def ugx(amount):
    return f"{int(amount or 0):,}"
