import os
import json
import urllib.request
from datetime import datetime

# URL of the deployed frontend
FRONTEND_URL = "https://freakfits.com" # Replace with actual domain

def generate_sitemap():
    # 1. Static routes
    static_routes = [
        "/",
        "/category.html",
        "/cart.html",
        "/track.html",
        "/returns.html",
        "/contact.html"
    ]

    urls = []
    today = datetime.now().strftime("%Y-%m-%d")

    for route in static_routes:
        urls.append(f"""  <url>
    <loc>{FRONTEND_URL}{route}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>{1.0 if route == "/" else 0.8}</priority>
  </url>""")

    # 2. Dynamic routes (Products)
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/api/products?limit=1000")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            items = data.get("items", [])
            for item in items:
                urls.append(f"""  <url>
    <loc>{FRONTEND_URL}/product.html?id={item['id']}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
  </url>""")
    except Exception as e:
        print(f"Warning: Could not fetch products from local API: {e}")

    sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""

    with open(os.path.join(os.path.dirname(__file__), "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap_content)
    
    print("sitemap.xml generated successfully.")

if __name__ == "__main__":
    generate_sitemap()
