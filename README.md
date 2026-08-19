# MyMarket.ug 🇺🇬

A mobile-first multi-vendor SaaS marketplace for Uganda. Vendors get their own shop
(`theirname.mymarket.ug`), customers browse freely without login, and the admin
approves vendors and tracks payments.

## Features

- **Customers**: browse/search/filter products by city & category — no login needed
- **Vendors**: dashboard with Products (10 free/month), Analytics (views + WhatsApp clicks, graph), Payments, Market Day booking, Ad requests
- **Admin** (`/admin`): approve/verify vendors, mark payments paid, create market days, launch ad campaigns, see expiring subscriptions
- **Monetization**: UGX 10,000 setup · UGX 5,000/month subscription · UGX 5,000 pro-upload · UGX 5,000/day boost · UGX 2,000–5,000 market days · ad budgets
- **Market Day banner**: scrolling marquee on every page for market days in the next 3 days
- **Subdomain shops**: `slug.mymarket.ug` renders the vendor shop (falls back to `/shop/<slug>`)
- **PWA**: installable on phones, service worker + push notification plumbing
- **Cron endpoint**: `/cron/daily?secret=...` deactivates expired vendors, resets monthly upload counters on the 1st, expires stale boosts, and sends each vendor a daily "N new shop views" push digest
- **Real payments (Flutterwave)**: vendors tap "Pay with Mobile Money" → hosted Flutterwave checkout (MTN MoMo / Airtel Money) → webhook verifies and activates the purchase automatically. Without API keys it falls back to manual "admin marks paid"
- **Web Push**: "New vendor joined" broadcast, "Product boosted" alerts, daily view digests (VAPID + pywebpush)
- **Image compression**: uploads are auto-resized to max 1000px and JPEG-optimized (a 3MB photo becomes ~6KB) — fast on 3G
- **Ratings & reviews**: customers review products without login; stars show on product pages and cards
- **SMS (Africa's Talking)**: signup confirmation, vendor approval, payment confirmation texts
- **Admin analytics** (`/admin/analytics`): revenue by type & month, engagement funnel, top vendors/categories

## Optional integrations (env vars)

| Variable | What it enables |
|---|---|
| `FLW_SECRET_KEY`, `FLW_PUBLIC_KEY`, `FLW_WEBHOOK_HASH` | Flutterwave MoMo checkout. Set the webhook URL in Flutterwave dashboard: `https://YOUR-APP/payments/webhook` |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | Web Push. Generate with `pip install py-vapid && vapid --gen` |
| `AT_USERNAME`, `AT_API_KEY` | Africa's Talking SMS (`AT_USERNAME=sandbox` for free testing) |

## Speed: Cloudflare CDN (free)

The app already sends long cache headers for static files and CDN-friendly headers
(`s-maxage=120`) on the anonymous homepage. To finish the setup:

1. Sign up at cloudflare.com → **Add site** → `mymarket.ug` → Free plan
2. Change your domain's nameservers at your registrar to the two Cloudflare ones
3. Add DNS records: `A @ → Render IP` and `CNAME * → your-app.onrender.com` (both **proxied**, orange cloud)
4. Cloudflare → Caching → **Cache Rule**: cache `/static/*` for 1 month, homepage for 2 minutes

Result: pages are served from Cloudflare's edge (Kampala gets Mombasa/Nairobi edge), and your
Render free dyno handles a fraction of the traffic.

## Tech stack

Python + Flask · SQLAlchemy (SQLite dev / Postgres prod) · Jinja2 · Tailwind CSS · Alpine.js · Flask-Login · Chart.js

## Run locally

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional
python seed.py                # seeds market days + demo vendor
python run.py                 # http://localhost:5000
```

Default admin login: **admin@mymarket.ug / admin123** (set `ADMIN_EMAIL`/`ADMIN_PASSWORD` env vars to change).

## Deploy on Render.com (free tier)

1. Push this repo to GitHub (see repo: `Mubogi/mymarket-ug`).
2. In Render dashboard: **New → Blueprint** → connect the GitHub repo. Render reads `render.yaml` and creates the web service + free Postgres automatically.
3. Set these env vars in the service dashboard (not committed):
   - `ADMIN_PASSWORD` — your real admin password
   - `BASE_DOMAIN` — `mymarket.ug` (or your custom domain)
4. Open the deployed URL → run the seed once via Render Shell:
   ```bash
   python seed.py
   ```
5. **Cron**: add a Render **Cron Job** (or free cron-job.org) hitting:
   ```
   https://YOUR-APP.onrender.com/cron/daily?secret=$CRON_SECRET
   ```
   once per day.

### Custom domain + vendor subdomains

1. In Render: **Settings → Custom Domains** → add `mymarket.ug` and `*.mymarket.ug`.
2. At your DNS provider: add an `A` record (apex) and a **wildcard `CNAME`** `* → your-app.onrender.com`.
3. Set `BASE_DOMAIN=mymarket.ug` in env vars. Shops then work as `slug.mymarket.ug`.

> Note: wildcard subdomains require a custom domain — they don't work on the default `onrender.com` URL. Until then, shops are reachable at `/shop/<slug>`.

## Folder structure

```
├── run.py                  # entry point (gunicorn run:app)
├── config.py               # env-driven config + pricing
├── seed.py                 # seed categories/market days/demo data
├── requirements.txt
├── render.yaml             # Render blueprint (web + Postgres)
├── .env.example
└── app/
    ├── __init__.py         # app factory, admin bootstrap, auto-migrations
    ├── extensions.py       # db, login manager
    ├── models.py           # users, vendors, products, payments, market_days, analytics, ad_campaigns, reviews
    ├── payments.py         # Flutterwave checkout + verification
    ├── push.py             # Web Push (VAPID/pywebpush)
    ├── sms.py              # Africa's Talking SMS
    ├── utils.py            # slugify, image compression, sorting, upload limits
    ├── routes/
    │   ├── main.py         # homepage, search, shop pages, reviews, market days, click tracking, PWA
    │   ├── vendor.py       # auth + dashboard (products/analytics/payments/market days/ads)
    │   ├── payments.py     # Flutterwave checkout, callback, webhook
    │   ├── admin.py        # approvals, payments, market days, ad campaigns, analytics
    │   └── cron.py         # daily maintenance jobs + push digests
    ├── templates/          # Jinja2 (Tailwind + Alpine.js)
    └── static/             # manifest.json, sw.js, icons, uploads/
```

## Roadmap ideas

- Vendor referral program (vendors earn credit for inviting vendors)
- Featured-shop placements on the homepage
- USSD fallback (*code#) for vendors without smartphones
- Multi-photo products + video support
- Delivery/courier integration for Kampala
