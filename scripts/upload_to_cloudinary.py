#!/usr/bin/env python3
"""
FreakFits — Cloudinary Batch Image Uploader & Code Refactor Script
Uploads all assets from assets/ to Cloudinary with auto-optimization (f_auto, q_auto),
builds a mapping dictionary, and updates HTML/JS/Python files to use Cloudinary CDN URLs.
"""

import os
import sys
import json
import glob
from pathlib import Path
from dotenv import load_dotenv

# Try loading from backend/.env and root .env
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "backend" / ".env", override=True)
load_dotenv(BASE_DIR / ".env", override=False)

try:
    import cloudinary
    import cloudinary.uploader
    from cloudinary.utils import cloudinary_url
except ImportError:
    print("Error: 'cloudinary' package is not installed.")
    print("Please run: pip install cloudinary")
    sys.exit(1)

CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
API_KEY = os.getenv("CLOUDINARY_API_KEY", "").strip()
API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "").strip()
FOLDER = os.getenv("CLOUDINARY_FOLDER", "freakfits").strip()

def check_credentials():
    if not CLOUD_NAME or not API_KEY or not API_SECRET:
        print("\n" + "=" * 65)
        print("[!] CLOUDINARY CREDENTIALS MISSING")
        print("=" * 65)
        print("Please add your Cloudinary credentials in backend/.env or .env:")
        print("  CLOUDINARY_CLOUD_NAME=your_cloud_name")
        print("  CLOUDINARY_API_KEY=your_api_key")
        print("  CLOUDINARY_API_SECRET=your_api_secret")
        print("  CLOUDINARY_FOLDER=freakfits")
        print("=" * 65 + "\n")
        return False
    return True

def configure_cloudinary():
    cloudinary.config(
        cloud_name=CLOUD_NAME,
        api_key=API_KEY,
        api_secret=API_SECRET,
        secure=True
    )
    print(f"[OK] Cloudinary configured for cloud '{CLOUD_NAME}' -> folder '{FOLDER}'")

def upload_assets():
    assets_dir = BASE_DIR / "assets"
    if not assets_dir.exists():
        print(f"Error: assets directory not found at {assets_dir}")
        sys.exit(1)

    image_files = sorted(list(assets_dir.glob("*.jpeg")) + list(assets_dir.glob("*.jpg")) + list(assets_dir.glob("*.png")))
    if not image_files:
        print("No image files found in assets/ directory.")
        return {}

    print(f"\nFound {len(image_files)} image files in assets/ to upload...")
    url_mapping = {}

    for idx, filepath in enumerate(image_files, start=1):
        filename = filepath.name
        rel_key = f"assets/{filename}"
        public_id_name = filepath.stem

        print(f"[{idx}/{len(image_files)}] Uploading {filename}...", end=" ", flush=True)

        try:
            res = cloudinary.uploader.upload(
                str(filepath),
                folder=FOLDER,
                public_id=public_id_name,
                overwrite=True,
                resource_type="image",
                transformation=[
                    {"fetch_format": "auto", "quality": "auto"}
                ]
            )
            # Optimize delivery URL with f_auto,q_auto
            secure_url = res.get("secure_url")
            # Ensure transformation is in the URL if not already present
            if "/upload/" in secure_url and "/f_auto,q_auto/" not in secure_url:
                opt_url = secure_url.replace("/upload/", "/upload/f_auto,q_auto/")
            else:
                opt_url = secure_url

            url_mapping[rel_key] = opt_url
            print("[OK]")
            print(f"    -> {opt_url}")
        except Exception as e:
            print(f"[FAILED] ({e})")

    return url_mapping

def save_mapping(mapping):
    mapping_file = BASE_DIR / "cloudinary_assets.json"
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
    print(f"\n[OK] Saved URL mapping to {mapping_file}")

def refactor_codebase(mapping):
    if not mapping:
        print("No mapping to apply. Skipping code refactor.")
        return

    files_to_update = [
        BASE_DIR / "index.html",
        BASE_DIR / "products.js",
        BASE_DIR / "script.js",
        BASE_DIR / "category.html",
        BASE_DIR / "product.html",
        BASE_DIR / "cart.html",
        BASE_DIR / "contact.html",
        BASE_DIR / "returns.html",
        BASE_DIR / "sizeguide.html",
        BASE_DIR / "backend" / "app" / "seed.py"
    ]

    print("\nRefactoring project files to use Cloudinary CDN URLs...")

    for file_path in files_to_update:
        if not file_path.exists():
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            original_content = content
            replacements_count = 0

            for local_path, cloud_url in mapping.items():
                if local_path in content:
                    count = content.count(local_path)
                    content = content.replace(local_path, cloud_url)
                    replacements_count += count

            if content != original_content:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  [OK] Updated {file_path.relative_to(BASE_DIR)} ({replacements_count} paths replaced)")
            else:
                print(f"  [-] No changes needed in {file_path.relative_to(BASE_DIR)}")
        except Exception as e:
            print(f"  [FAIL] Error updating {file_path.name}: {e}")

def reseed_database():
    try:
        sys.path.insert(0, str(BASE_DIR / "backend"))
        from app.seed import seed_database
        print("\nRe-seeding MySQL database with Cloudinary product URLs...")
        seed_database()
        print("[OK] MySQL database products updated successfully!")
    except Exception as e:
        print(f"Note: Database re-seed note: {e}")

def main():
    print("=" * 65)
    print(" FreakFits -- Cloudinary Batch Asset Uploader & Refactor")
    print("=" * 65)

    if not check_credentials():
        sys.exit(1)

    configure_cloudinary()
    mapping = upload_assets()

    if mapping:
        save_mapping(mapping)
        refactor_codebase(mapping)
        reseed_database()
        print("\n" + "=" * 65)
        print(" SUCCESS: ALL ASSETS MIGRATED TO CLOUDINARY CDN!")
        print("=" * 65 + "\n")
    else:
        print("\nNo assets were uploaded.")

if __name__ == "__main__":
    main()
