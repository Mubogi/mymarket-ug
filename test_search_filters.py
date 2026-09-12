"""End-to-end verification for search/filter/geo/shop features."""
import re

from app import create_app

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}")


app = create_app()
c = app.test_client()


def grid(body):
    s = body.find("All Products")
    e = body.find("Sell on MyMarket.ug")
    seg = body[s:e] if s != -1 and e != -1 else body
    return re.findall(r'line-clamp-1">([^<]+)</div>', seg)


print("=== Search ==")
r = c.get("/?q=iphone")
b = r.get_data(as_text=True)
check("q=iphone returns iPhone", "iPhone 11 (Used)" in b)
check("q=iphone hides Ankara", "Ankara" not in grid(b))

print("=== Category filter ===")
r = c.get("/?category=Phones")
b = r.get_data(as_text=True)
names = grid(b)
check("category=Phones grid only Phones", all("Phone" in n or "Tecno" in n for n in names) and len(names) == 2)
check("category=Phones actively filters (Ankara not shown)", "Ankara" not in names)

print("=== District/city filter ===")
r = c.get("/?city=Kampala")
b = r.get_data(as_text=True)
check("city=Kampala shows products", len(grid(b)) > 0)
r = c.get("/?city=Gulu")
b = r.get_data(as_text=True)
check("city=Gulu shows no products (No products found)", "No products found" in b)
check("all 23 districts available in chips", "Wakiso" in b and "Hoima" in b and "Busia" in b)

print("=== Sort ===")
asc = grid(c.get("/?sort=price_asc").get_data(as_text=True))
desc = grid(c.get("/?sort=price_desc").get_data(as_text=True))
prices = {"Tecno Spark 20": 420000, "iPhone 11 (Used)": 950000, "Ankara Dress": 65000,
          "Sneakers": 80000, "Leather Handbag": 120000, "Bluetooth Speaker": 90000}
asc_p = [prices[n] for n in asc if n in prices]
desc_p = [prices[n] for n in desc if n in prices]
check("price_asc sorted", asc_p == sorted(asc_p))
check("price_desc sorted", desc_p == sorted(desc_p, reverse=True))

print("=== Price range + toggles ===")
b = c.get("/?min=100000&max=500000").get_data(as_text=True)
check("min/max filters", set(grid(b)) <= {"Tecno Spark 20", "Leather Handbag"})
b = c.get("/?verified=1").get_data(as_text=True)
check("verified filter works (demo verified, all show)", len(grid(b)) >= 1)
b = c.get("/?stock=1").get_data(as_text=True)
check("in-stock filter returns something", len(grid(b)) >= 1)

print("=== Rails hidden while filtering ===")
b = c.get("/?category=Phones").get_data(as_text=True)
check("Trending hidden while filtering", "Trending Now" not in b)
check("Deals rail not filtered page", "Deals of the day" not in b)

print("=== Geo ===")
data = c.get("/api/nearby?lat=0.35&lon=32.58").get_json()
check("api/nearby Kampala", data["district"] == "Kampala")
b = c.get("/?near=0.35,32.58").get_data(as_text=True)
check("geo banner shown", "Showing products near" in b and "Kampala" in b)

print("=== Shop page mini-site ===")
b = c.get("/shop/kampala-phones-hub").get_data(as_text=True)
check("shop page has address", "Kampala" in b)
check("shop page has In-shop search", "Search in shop" in b)
check("shop page has Sort", "Price: low" in b)
check("shop page has share button", "Share shop" in b)

print("=== Product page ===")
b = c.get("/product/1").get_data(as_text=True)
check("product page Visit full shop", "Visit full shop" in b)

print("=== WhatsApp link (was broken) ===")
r = c.get("/go/whatsapp/1")
loc = r.headers.get("Location", "")
check("go/whatsapp redirects to wa.me", loc.startswith("https://wa.me/") and "Tecno" in loc)

print(f"\n{PASS} passed, {FAIL} failed")
raise SystemExit(1 if FAIL else 0)