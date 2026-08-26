from sqlalchemy import text

from app.database import get_engine


def migrate():
    engine = get_engine()
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE coupons ADD COLUMN usage_limit INT NULL;"))
            print("Added usage_limit column.")
        except Exception as e:
            print(f"Column usage_limit may already exist or error: {e}")
            
        try:
            conn.execute(text("ALTER TABLE coupons ADD COLUMN usage_count INT DEFAULT 0;"))
            print("Added usage_count column.")
        except Exception as e:
            print(f"Column usage_count may already exist or error: {e}")
            
        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
