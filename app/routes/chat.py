"""Marketplace chat system — vendor-to-vendor and customer-to-vendor messaging.

Messages are stored in the DB; no login required for customers.
"""
from flask import Blueprint, request, jsonify, redirect, url_for, render_template, flash, abort
from flask_login import current_user, login_required

from ..extensions import csrf, db, limiter
from ..models import ChatMessage, Vendor, User

bp = Blueprint("chat", __name__)


def get_vendor_display(vendor):
    return {
        "id": vendor.id,
        "name": vendor.shop_name,
        "slug": vendor.slug,
        "logo": vendor.logo,
    }


@bp.route("/chat/<int:vendor_id>", methods=["GET"])
def chat_thread(vendor_id):
    """Customer chat page with a vendor (no login needed)."""
    vendor = Vendor.query.get_or_404(vendor_id)
    if not vendor.is_active:
        abort(404)

    # Get thread: all messages between this visitor and this vendor
    visitor_key = request.args.get("visitor", "")
    if not visitor_key:
        # Generate a visitor session key
        visitor_key = f"guest-{request.remote_addr}-{request.cookies.get('session', '')[:8]}"

    messages = (
        ChatMessage.query.filter_by(vendor_id=vendor.id, visitor_key=visitor_key)
        .order_by(ChatMessage.created_at)
        .all()
    )

    return render_template(
        "chat/thread.html",
        vendor=vendor,
        messages=messages,
        visitor_key=visitor_key,
        get_vendor_display=get_vendor_display,
    )


@bp.route("/chat/<int:vendor_id>/send", methods=["POST"])
@limiter.limit("30 per minute")
def chat_send(vendor_id):
    """Send a message to a vendor (customer or vendor-to-vendor)."""
    vendor = Vendor.query.get_or_404(vendor_id)
    if not vendor.is_active:
        abort(404)

    visitor_key = request.form.get("visitor_key", "")
    if not visitor_key:
        visitor_key = f"guest-{request.remote_addr}"

    sender_type = "customer"
    sender_name = request.form.get("sender_name", "").strip() or "Customer"
    sender_vendor_id = None

    # If the sender is a logged-in vendor, mark as vendor-to-vendor
    if current_user.is_authenticated and current_user.vendor:
        sender_type = "vendor"
        sender_name = current_user.vendor.shop_name
        sender_vendor_id = current_user.vendor.id

    text = request.form.get("message", "").strip()
    if not text:
        flash("Message cannot be empty.", "error")
        return redirect(request.referrer or url_for("chat.chat_thread", vendor_id=vendor.id))

    msg = ChatMessage(
        vendor_id=vendor.id,
        sender_type=sender_type,
        sender_name=sender_name,
        sender_vendor_id=sender_vendor_id,
        visitor_key=visitor_key,
        message=text[:2000],
    )
    db.session.add(msg)
    db.session.commit()

    return redirect(request.referrer or url_for("chat.chat_thread", vendor_id=vendor.id))


@bp.route("/vendor/chat")
@login_required
def vendor_chat_inbox():
    """Vendor's chat inbox — all messages sent TO this vendor."""
    v = current_user.vendor
    if not v:
        abort(403)

    # Group messages by visitor (customer or vendor)
    threads = {}
    messages = (
        ChatMessage.query.filter_by(vendor_id=v.id)
        .order_by(ChatMessage.created_at.desc())
        .all()
    )
    for msg in messages:
        key = msg.visitor_key or f"vendor-{msg.sender_vendor_id}"
        if key not in threads:
            threads[key] = {
                "key": key,
                "sender_name": msg.sender_name,
                "sender_type": msg.sender_type,
                "sender_vendor_id": msg.sender_vendor_id,
                "latest_message": msg.message,
                "latest_at": msg.created_at,
                "unread": 0,
            }
        if msg.sender_type == "customer" and not msg.is_read:
            threads[key]["unread"] += 1

    # Mark as read
    ChatMessage.query.filter_by(vendor_id=v.id, is_read=False).update({"is_read": True})
    db.session.commit()

    return render_template(
        "vendor/chat_inbox.html",
        v=v,
        threads=threads.values(),
        get_vendor_display=get_vendor_display,
    )


@bp.route("/vendor/chat/<thread_key>")
@login_required
def vendor_chat_thread(thread_key):
    """Vendor views a specific chat thread."""
    v = current_user.vendor
    if not v:
        abort(403)

    messages = (
        ChatMessage.query.filter_by(vendor_id=v.id, visitor_key=thread_key)
        .order_by(ChatMessage.created_at)
        .all()
    )
    if not messages:
        abort(404)

    return render_template(
        "vendor/chat_thread.html",
        v=v,
        messages=messages,
        thread_key=thread_key,
        get_vendor_display=get_vendor_display,
    )


@bp.route("/vendor/chat/<thread_key>/reply", methods=["POST"])
@limiter.limit("30 per minute")
@login_required
def vendor_chat_reply(thread_key):
    """Vendor replies to a thread."""
    v = current_user.vendor
    if not v:
        abort(403)

    text = request.form.get("message", "").strip()
    if not text:
        flash("Reply cannot be empty.", "error")
        return redirect(url_for("chat.vendor_chat_thread", thread_key=thread_key))

    msg = ChatMessage(
        vendor_id=v.id,
        sender_type="vendor",
        sender_name=v.shop_name,
        sender_vendor_id=v.id,
        visitor_key=thread_key,
        message=text[:2000],
        is_read=True,
    )
    db.session.add(msg)
    db.session.commit()
    return redirect(url_for("chat.vendor_chat_thread", thread_key=thread_key))
