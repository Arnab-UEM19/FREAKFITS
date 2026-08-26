import logging

from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import Coupon, Product

logger = logging.getLogger("uvicorn")

INITIAL_PRODUCTS = [
    {
        "id": 1,
        "name": "Argentina Home 3-Star Kit 25/26",
        "club": "Argentina FA",
        "price": 1499.0,
        "was_price": 1999.0,
        "category": "home",
        "color": "#8CFF3B",
        "rating": 4.9,
        "reviews": 312,
        "badge": "BESTSELLER",
        "badge_bg": "#8CFF3B",
        "material": "100% Recycled Poly-Mesh Dri-FIT with golden embroidered 3-star crest",
        "fit": "Athletic Tailored Match Cut — True to size",
        "care": "Machine wash cold inside-out, tumble dry low or hang dry. Do not iron directly on prints.",
        "images": ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300483/freakfits/Argentina_Home.jpg"]
    },
    {
        "id": 2,
        "name": "Argentina Away Midnight Edition",
        "club": "Argentina FA",
        "price": 1399.0,
        "was_price": 1799.0,
        "category": "away",
        "color": "#29C5F6",
        "rating": 4.8,
        "reviews": 184,
        "badge": "FAN FAV",
        "badge_bg": "#29C5F6",
        "material": "100% Performance Breathable Polyester with AeroMesh cooling zones",
        "fit": "Standard Athletic Fit",
        "care": "Machine wash cold, line dry recommended.",
        "images": ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300481/freakfits/Argentina_Away.jpg"]
    },
    {
        "id": 3,
        "name": "Barcelona Home Blaugrana Edition",
        "club": "FC Barcelona",
        "price": 1599.0,
        "was_price": 2099.0,
        "category": "home",
        "color": "#FF3E7A",
        "rating": 4.9,
        "reviews": 245,
        "badge": "ICONIC",
        "badge_bg": "#FF3E7A",
        "material": "Official match-grade jacquard knit with embroidered crest",
        "fit": "Slim Matchday Cut",
        "care": "Machine wash cold, gentle cycle.",
        "images": ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300487/freakfits/Barcelona_Home.jpg"]
    },
    {
        "id": 4,
        "name": "Real Madrid Home Pure White 25/26",
        "club": "Real Madrid CF",
        "price": 1599.0,
        "was_price": 2099.0,
        "category": "home",
        "color": "#D4A054",
        "rating": 5.0,
        "reviews": 420,
        "badge": "CHAMPIONS",
        "badge_bg": "#D4A054",
        "material": "Moisture-wicking AEROREADY fabric with golden shoulder accents",
        "fit": "Tailored Pro Fit",
        "care": "Machine wash cold inside-out.",
        "images": ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300499/freakfits/Real_Madrid_Home.jpg"]
    },
    {
        "id": 5,
        "name": "Real Madrid Fan Edition Special",
        "club": "Real Madrid CF",
        "price": 1799.0,
        "was_price": 2299.0,
        "category": "fan",
        "color": "#D4A054",
        "rating": 4.9,
        "reviews": 198,
        "badge": "SPECIAL DROP",
        "badge_bg": "#D4A054",
        "material": "Premium Engineered Poly-Jacquard Hybrid with special commemorative embroidery",
        "fit": "Relaxed Fit for terraces and streetwear",
        "care": "Hand wash or gentle machine wash cold.",
        "images": ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300497/freakfits/Real_Madrid_Fan_Edition.jpg"]
    },
    {
        "id": 6,
        "name": "Arsenal 24/25 Away Edition",
        "club": "Arsenal FC",
        "price": 1449.0,
        "was_price": 1899.0,
        "category": "away",
        "color": "#8CFF3B",
        "rating": 4.7,
        "reviews": 165,
        "badge": "NEW DROP",
        "badge_bg": "#8CFF3B",
        "material": "Dri-FIT Stadium fabric with embroidered Cannon emblem",
        "fit": "Regular Athletic Fit",
        "care": "Machine wash cold, tumble dry low.",
        "images": ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300485/freakfits/Arsenal_24_25_Away.jpg"]
    },
    {
        "id": 7,
        "name": "FC Bayern Munich Away Kit",
        "club": "FC Bayern München",
        "price": 1499.0,
        "was_price": 1949.0,
        "category": "away",
        "color": "#29C5F6",
        "rating": 4.8,
        "reviews": 135,
        "badge": "RESTOCK",
        "badge_bg": "#29C5F6",
        "material": "High-grade breathable polyester with silicone crest",
        "fit": "Athletic Cut",
        "care": "Machine wash cold, hang dry.",
        "images": ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300488/freakfits/FC_Bayern_Away.jpg"]
    },
    {
        "id": 8,
        "name": "Germany Home DFB Classic Kit",
        "club": "Germany DFB",
        "price": 1499.0,
        "was_price": 1999.0,
        "category": "home",
        "color": "#D4A054",
        "rating": 4.8,
        "reviews": 210,
        "badge": "CLASSIC",
        "badge_bg": "#D4A054",
        "material": "AEROREADY performance moisture-wicking weave",
        "fit": "Standard Athletic Fit",
        "care": "Machine wash cold inside-out.",
        "images": ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300491/freakfits/Germany_Home.jpg"]
    },
    {
        "id": 9,
        "name": "Manchester United Home Red Devils",
        "club": "Manchester United",
        "price": 1549.0,
        "was_price": 2049.0,
        "category": "home",
        "color": "#FF3E7A",
        "rating": 4.9,
        "reviews": 320,
        "badge": "HOT",
        "badge_bg": "#FF3E7A",
        "material": "100% Recycled Polyester Match Knit with woven Red Devils crest",
        "fit": "Regular Matchday Cut",
        "care": "Machine wash cold, do not iron badge.",
        "images": ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300496/freakfits/Manchester_United_Home.jpg"]
    },
    {
        "id": 10,
        "name": "Spain Away Euro Champions Kit",
        "club": "RFEF Spain",
        "price": 1399.0,
        "was_price": 1799.0,
        "category": "away",
        "color": "#8CFF3B",
        "rating": 4.7,
        "reviews": 115,
        "badge": "CHAMPIONS",
        "badge_bg": "#8CFF3B",
        "material": "Featherlight breathable mesh fabric",
        "fit": "Athletic Fit",
        "care": "Machine wash cold, hang dry.",
        "images": ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300501/freakfits/Spain_Away.jpg"]
    }
]

INITIAL_COUPONS = [
    {
        "code": "FREAK5P",
        "discount_percent": 5.0,
        "label": "5% OFF — FREAK5P",
        "is_active": True
    },
    {
        "code": "FREAK10",
        "discount_percent": 10.0,
        "label": "10% OFF — FREAK10",
        "is_active": True
    }
]

from .models import Admin
from .security import get_password_hash

INITIAL_ORDERS = [
    {
        "order_code": "FF-6647650C",
        "customer_name": "Arnab Bindu",
        "customer_email": "arnabbinduc2005@gmail.com",
        "customer_phone": "+91 98765 43210",
        "subtotal": 1898.0,
        "discount": 0.0,
        "shipping_fee": 0.0,
        "total": 1898.0,
        "payment_method": "UPI",
        "payment_status": "COMPLETED",
        "order_status": "Pending",
        "items": [
            {
                "product_id": 1,
                "product_name": "Argentina Home 3-Star Kit 25/26",
                "club": "Argentina FA",
                "size": "M",
                "custom_name": "BINDUS",
                "custom_number": "10",
                "quantity": 1,
                "unit_price": 899.0,
                "line_total": 899.0
            },
            {
                "product_id": 4,
                "product_name": "Real Madrid Home Pure White 25/26",
                "club": "Real Madrid CF",
                "size": "L",
                "custom_name": "MBAPPE",
                "custom_number": "09",
                "quantity": 1,
                "unit_price": 999.0,
                "line_total": 999.0
            }
        ]
    },
    {
        "order_code": "FF-8B12EC4A",
        "customer_name": "Rohit Deshmukh",
        "customer_email": "rohit.d@gmail.com",
        "customer_phone": "+91 98123 45678",
        "subtotal": 699.0,
        "discount": 0.0,
        "shipping_fee": 0.0,
        "total": 699.0,
        "payment_method": "Credit Card",
        "payment_status": "COMPLETED",
        "order_status": "Shipped",
        "items": [
            {
                "product_id": 3,
                "product_name": "Barcelona Home Blaugrana Edition",
                "club": "FC Barcelona",
                "size": "S",
                "custom_name": "YAMAL",
                "custom_number": "19",
                "quantity": 1,
                "unit_price": 699.0,
                "line_total": 699.0
            }
        ]
    },
    {
        "order_code": "FF-7A41DF99",
        "customer_name": "Vikram Malhotra",
        "customer_email": "vikram.m@outlook.com",
        "customer_phone": "+91 99345 67890",
        "subtotal": 2198.0,
        "discount": 0.0,
        "shipping_fee": 0.0,
        "total": 2198.0,
        "payment_method": "Net Banking",
        "payment_status": "COMPLETED",
        "order_status": "Delivered",
        "items": [
            {
                "product_id": 9,
                "product_name": "Manchester United Home Red Devils",
                "club": "Manchester United",
                "size": "XL",
                "custom_name": "GARNACHO",
                "custom_number": "17",
                "quantity": 1,
                "unit_price": 1299.0,
                "line_total": 1299.0
            },
            {
                "product_id": 5,
                "product_name": "Real Madrid Fan Edition Special",
                "club": "Real Madrid CF",
                "size": "M",
                "custom_name": "",
                "custom_number": "",
                "quantity": 1,
                "unit_price": 899.0,
                "line_total": 899.0
            }
        ]
    }
]


def seed_database():
    """Create tables and seed initial data if empty."""
    Base.metadata.create_all(bind=engine)
    
    # Auto-migrate using Alembic
    try:
        import os

        from alembic.config import Config

        from alembic import command
        alembic_ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
        alembic_cfg = Config(alembic_ini_path)
        command.upgrade(alembic_cfg, "head")
        logger.info("Successfully ran Alembic migrations.")
    except Exception as e:
        logger.error(f"Alembic migration failed: {e}")

    db: Session = SessionLocal()
    try:
        # Seed Default Administrator
        admin_email = "supportfreakfits@gmail.com"
        existing_admin = db.query(Admin).filter(Admin.email == admin_email).first()
        if not existing_admin:
            default_admin = Admin(
                full_name="Super Admin",
                email=admin_email,
                hashed_password=get_password_hash("admin123"),
                role="super_admin",
                status="approved",
                is_active=True
            )
            db.add(default_admin)
            
            # Remove old legacy admin if exists
            old_admin = db.query(Admin).filter(Admin.email == "admin@freakfits.in").first()
            if old_admin:
                db.delete(old_admin)
                
            db.commit()
            logger.info(f"Seeded default administrator: {admin_email}")

        # Seed Products with Stock and Size Prices
        for prod_data in INITIAL_PRODUCTS:
            existing = db.query(Product).filter(Product.id == prod_data["id"]).first()
            p_price = prod_data["price"]
            p_was = prod_data.get("was_price") or (p_price + 400)
            size_prices_dict = {
                "S": p_price,
                "M": p_price,
                "L": p_price,
                "XL": p_price,
                "XXL": p_price
            }
            size_was_dict = {
                "S": p_was,
                "M": p_was,
                "L": p_was,
                "XL": p_was,
                "XXL": p_was
            }
            if not existing:
                stock_matrix = {"S": 12, "M": 8, "L": 10, "XL": 4, "XXL": 2}
                prod = Product(**prod_data, stock=stock_matrix, size_prices=size_prices_dict, size_was_prices=size_was_dict)
                db.add(prod)
            else:
                # Do not overwrite user-edited data (like price) on every restart
                if not existing.stock:
                    existing.stock = {"S": 12, "M": 8, "L": 10, "XL": 4, "XXL": 2}
                if not existing.size_prices:
                    existing.size_prices = size_prices_dict
                if not existing.size_was_prices:
                    existing.size_was_prices = size_was_dict
        
        # Seed Coupons
        for coupon_data in INITIAL_COUPONS:
            existing_coupon = db.query(Coupon).filter(Coupon.code == coupon_data["code"]).first()
            if not existing_coupon:
                c = Coupon(**coupon_data)
                db.add(c)

        # Seed Sample Orders if empty - commented out to allow testing from a clean slate
        # existing_orders_count = db.query(Order).count()
        # if existing_orders_count == 0:
        #     for ord_data in INITIAL_ORDERS:
        #         items_data = ord_data.pop("items")
        #         order_obj = Order(**ord_data)
        #         db.add(order_obj)
        #         db.flush()
        #         for itm in items_data:
        #             order_item_obj = OrderItem(order_id=order_obj.id, **itm)
        #             db.add(order_item_obj)
        #     logger.info("Seeded initial orders for fulfillment dashboard.")

        db.commit()
        logger.info("Successfully seeded FreakFits database with products, coupons, admin, and orders.")
    except Exception as e:
        logger.error(f"Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
