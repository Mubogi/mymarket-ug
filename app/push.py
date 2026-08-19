"""Web Push notifications via VAPID (pywebpush).
No-ops gracefully when VAPID keys are not configured."""
import json

from flask import current_app

from .extensions import db
from .models import PushSubscription


def push_enabled():
    return bool(
        current_app.config.get("VAPID_PUBLIC_KEY")
        and current_app.config.get("VAPID_PRIVATE_KEY")
    )


def _send(sub, title, body, url="/"):
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"auth": sub.auth, "p256dh": sub.p256dh},
            },
            data=json.dumps({"title": title, "body": body, "url": url}),
            vapid_private_key=current_app.config["VAPID_PRIVATE_KEY"],
            vapid_claims={"sub": f"mailto:{current_app.config['VAPID_CLAIMS_EMAIL']}"},
        )
        return True
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in (404, 410):  # subscription expired — clean up
            db.session.delete(sub)
            db.session.commit()
        current_app.logger.warning("Push failed (%s): %s", status, exc)
        return False
    except Exception as exc:  # never break a request because of push
        current_app.logger.warning("Push error: %s", exc)
        return False


def notify_user(user_id, title, body, url="/"):
    if not push_enabled():
        return 0
    sent = 0
    for sub in PushSubscription.query.filter_by(user_id=user_id).all():
        sent += _send(sub, title, body, url)
    return sent


def notify_all(title, body, url="/"):
    if not push_enabled():
        return 0
    sent = 0
    for sub in PushSubscription.query.all():
        sent += _send(sub, title, body, url)
    return sent
