import os
from datetime import datetime
from ..database import SessionLocal
from ..models import Product

FRONTEND_URL = "https://freakfits.com"
SITEMAP_PATH = os.path.join(os.path.dirname(__file__), "../../../storefront/sitemap.xml")

def regenerate_sitemap():
    static_routes = ["/", "/category.html", "/cart.html", "/track.html", "/returns.html", "/contact.html"]
    today = datetime.now().strftime("%Y-%m-%d")
    urls = []
    
    for route in static_routes:
        urls.append(f"  <url>\n    <loc>{FRONTEND_URL}{route}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>{1.0 if route == '/' else 0.8}</priority>\n  </url>")

    db = SessionLocal()
    try:
        products = db.query(Product).filter(Product.is_active == True).all()
        for p in products:
            urls.append(f"  <url>\n    <loc>{FRONTEND_URL}/product.html?id={p.id}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.9</priority>\n  </url>")
    except Exception as e:
        print(f"Error regenerating sitemap: {e}")
    finally:
        db.close()

    content = f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{chr(10).join(urls)}\n</urlset>'
    
    try:
        with open(SITEMAP_PATH, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        print(f"Failed to write sitemap to {SITEMAP_PATH}: {e}")
