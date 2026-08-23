from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Product, User
from ..schemas import ProductResponse
from ..security import require_current_user

router = APIRouter(prefix="/products", tags=["Products"])

@router.get("", response_model=List[ProductResponse])
def list_products(
    category: Optional[str] = Query(None, description="Filter by category (home, away, kit)"),
    sort: Optional[str] = Query("featured", description="Sort order: featured, price_asc, price_desc, rating"),
    q: Optional[str] = Query(None, description="Search query"),
    db: Session = Depends(get_db)
):
    query = db.query(Product).filter(Product.is_active == True)

    if category:
        query = query.filter(Product.category == category.lower().strip())

    if q:
        search = f"%{q.strip()}%"
        query = query.filter(Product.name.ilike(search) | Product.club.ilike(search))

    new_drop_order = (Product.badge == 'NEW DROP').desc()

    if sort == "price_asc":
        query = query.order_by(new_drop_order, Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(new_drop_order, Product.price.desc())
    elif sort == "rating":
        query = query.order_by(new_drop_order, Product.rating.desc())
    else:
        query = query.order_by(new_drop_order, Product.id.desc())

    return query.all()

@router.get("/category/{category}", response_model=List[ProductResponse])
def get_products_by_category(category: str, db: Session = Depends(get_db)):
    products = db.query(Product).filter(
        Product.category == category.lower().strip(),
        Product.is_active == True
    ).order_by((Product.badge == 'NEW DROP').desc(), Product.id.desc()).all()
    return products

@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with ID {product_id} not found."
        )
    return product


import uuid
import os
from fastapi import File, UploadFile, Form
import cloudinary
import cloudinary.uploader
from ..models import Review
from ..config import settings

# Initialize Cloudinary config
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True
)

def extract_cloudinary_public_id(url: str) -> Optional[str]:
    if not url or "res.cloudinary.com" not in url:
        return None
    try:
        parts = url.split("/upload/")
        if len(parts) < 2:
            return None
        path_part = parts[1]
        subparts = path_part.split("/")
        if subparts[0].startswith("v") and subparts[0][1:].isdigit():
            subparts = subparts[1:]
        public_id_with_ext = "/".join(subparts)
        public_id, _ = os.path.splitext(public_id_with_ext)
        return public_id
    except Exception:
        return None

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

@router.post("/reviews")
def create_product_review(
    product_id: int = Form(...),
    user_name: str = Form(None),
    rating: int = Form(...),
    comment: str = Form(None),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_current_user)
):
    # Use authenticated user's name (ignore user-supplied name to prevent impersonation)
    verified_user_name = current_user.full_name or user_name or "Anonymous"

    if rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

    # Validate uploaded image file type
    if photo and photo.filename:
        ext = os.path.splitext(photo.filename)[1].lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Only image files are allowed ({', '.join(ALLOWED_IMAGE_EXTENSIONS)}).")
        
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    image_url = None
    if photo and photo.filename:
        try:
            # Read file bytes to ensure compatibility with Cloudinary upload
            photo.file.seek(0)
            file_bytes = photo.file.read()
            # Upload file directly to Cloudinary
            upload_result = cloudinary.uploader.upload(
                file_bytes,
                folder=settings.CLOUDINARY_FOLDER
            )
            image_url = upload_result.get("secure_url")
        except Exception as e:
            # Fallback to local files if Cloudinary fails
            print(f"Cloudinary upload error: {e}")
            os.makedirs("static/uploads/reviews", exist_ok=True)
            ext = os.path.splitext(photo.filename)[1]
            unique_filename = f"{uuid.uuid4()}{ext}"
            file_path = os.path.join("static", "uploads", "reviews", unique_filename)
            photo.file.seek(0)
            with open(file_path, "wb") as buffer:
                buffer.write(photo.file.read())
            image_url = f"/static/uploads/reviews/{unique_filename}"
        
    review = Review(
        product_id=product_id,
        user_name=verified_user_name,
        rating=rating,
        comment=comment,
        image_url=image_url
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    
    # Recalculate aggregates
    all_reviews = db.query(Review).filter(Review.product_id == product_id).all()
    total_reviews = len(all_reviews)
    avg_rating = sum(r.rating for r in all_reviews) / total_reviews if total_reviews > 0 else 4.8
    
    product.rating = round(avg_rating, 1)
    product.reviews = total_reviews
    db.commit()
    
    return {
        "status": "success",
        "message": "Review submitted successfully!",
        "review": {
            "id": review.id,
            "rating": review.rating,
            "comment": review.comment,
            "image_url": review.image_url,
            "user_name": review.user_name,
            "created_at": review.created_at.isoformat()
        }
    }

@router.delete("/reviews/{review_id}", status_code=status.HTTP_200_OK)
def delete_product_review(
    review_id: int,
    db: Session = Depends(get_db)
):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
        
    product_id = review.product_id

    # Delete image from Cloudinary
    if review.image_url:
        public_id = extract_cloudinary_public_id(review.image_url)
        if public_id:
            try:
                cloudinary.uploader.destroy(public_id)
            except Exception as e:
                print(f"Cloudinary file deletion error: {e}")
        elif review.image_url.startswith("/static/uploads/reviews/"):
            # Local fallback deletion
            local_path = review.image_url.lstrip("/")
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except Exception as e:
                    print(f"Error removing local review image: {e}")

    db.delete(review)
    db.commit()

    # Recalculate aggregates
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        all_reviews = db.query(Review).filter(Review.product_id == product_id).all()
        total_reviews = len(all_reviews)
        avg_rating = sum(r.rating for r in all_reviews) / total_reviews if total_reviews > 0 else 4.8
        
        product.rating = round(avg_rating, 1)
        product.reviews = total_reviews
        db.commit()

    return {
        "success": True,
        "message": f"Review #{review_id} and its associated images deleted successfully."
    }

@router.get("/{product_id}/reviews")
def get_product_reviews(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    reviews = db.query(Review).filter(Review.product_id == product_id).order_by(Review.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "user_name": r.user_name,
            "rating": r.rating,
            "comment": r.comment,
            "image_url": r.image_url,
            "created_at": r.created_at.strftime("%d %b %Y, %I:%M %p")
        }
        for r in reviews
    ]
