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
- **Cron endpoint**: `/cron/daily?secret=...` deactivates expired vendors, resets monthly upload counters on the 1st, expires stale boosts

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
    ├── __init__.py         # app factory, admin bootstrap
    ├── extensions.py       # db, login manager
    ├── models.py           # users, vendors, products, payments, market_days, analytics, ad_campaigns
    ├── utils.py            # slugify, uploads, sorting, upload limits
    ├── routes/
    │   ├── main.py         # homepage, search, shop pages, market days, click tracking, PWA
    │   ├── vendor.py       # auth + dashboard (products/analytics/payments/market days/ads)
    │   ├── admin.py        # approvals, payments, market days, ad campaigns
    │   └── cron.py         # daily maintenance jobs
    ├── templates/          # Jinja2 (Tailwind + Alpine.js)
    └── static/             # manifest.json, sw.js, icons, uploads/
```

## Roadmap ideas

- Real payments via MTN MoMo / Airtel Money APIs (Flutterwave/PesaPal)
- Web Push (VAPID) for live notifications
- Product edit page, image compression, review/ratings
