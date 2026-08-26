# Project Profile — MyMarket.ug

> Multi-vendor SaaS marketplace for Uganda — vendors get their own subdomain shop, customers browse freely, admin approves & tracks payments.

## 1. Business Overview
- **Owner / Brand:** Jordan Design Hub (JD Hub) — Mubogi Gastavas Jordan Tech Ecosystem
- **Contact:** jordandesignhub@gmail.com · WhatsApp +256 754 687 597
- **Category:** Marketplace / E-commerce SaaS
- **Status:** production
- **Links:** Live · <https://github.com/Mubogi/mymarket-ug>

## 2. Problem & Target Market
- **Problem:** Ugandan vendors (market sellers, small shops) have no affordable online storefront; customers can't discover them.
- **Target users:** Vendors (SMEs, market traders) and customers in Ugandan cities.
- **Market context:** Mobile-first; UGX pricing; Flutterwave mobile money (MTN/Airtel); Africa's Talking SMS; 3G-fast image compression.

## 3. Value Proposition & Features
- Customers browse/search/filter by city & category — no login
- Vendor dashboard: products (10 free/month), analytics, payments, market-day booking, ad requests
- Admin panel: vendor approval, payment marking, market days, ad campaigns, expiring subs
- Subdomain shops (slug.mymarket.ug) with /shop/<slug> fallback
- PWA installable with push-notification plumbing
- Real Flutterwave payments (MoMo checkout + webhook) with manual fallback
- Cron endpoint for expiries, monthly resets, boost expiry, daily digests
- Ratings & reviews without login
- Image compression (3 MB → ~6 KB) for 3G speed

## 4. Business / Monetization Model
- **Pricing:** freemium + subscription + boosts
- **Revenue streams:** UGX 10,000 setup · UGX 5,000/month subscription · UGX 5,000 pro-upload · UGX 5,000/day boost · UGX 2,000–5,000 market days · ad budgets
- **Payment methods:** Flutterwave mobile money (MTN MoMo / Airtel Money); manual admin-marked fallback

## 5. Tech Stack
| Layer | Tech |
|-------|------|
| Backend | Python + Flask, Flask-Login |
| Frontend | Jinja2, Tailwind CSS, Alpine.js, Chart.js |
| Database | SQLite dev / Postgres prod (SQLAlchemy) |
| Mobile/Desktop | PWA |
| Deploy | Render-ready; cron endpoint for scheduled jobs |

## 6. Roadmap & Status
- **Current milestone:** Production SaaS with real payments live
- **Next steps:** Vendor growth, push digest hardening, ad campaigns
- **Known gaps:** VAPID/push reliability; manual payment fallback volume

## 7. Metrics (optional)
- Users: n/a
- Last updated: 2026-08-26

---
*Template version: 1.0 — kept identical across all JD Hub projects. Update only the content, not the structure.*
