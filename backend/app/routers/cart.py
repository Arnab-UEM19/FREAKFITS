
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import require_current_user

router = APIRouter(
    prefix="/cart",
    tags=["cart"]
)

@router.get("/", response_model=list[schemas.CartItemResponse])
def get_cart_items(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_current_user)
):
    cart_items = db.query(models.CartItem).filter(models.CartItem.user_id == current_user.id).all()
    return cart_items

@router.post("/", response_model=schemas.CartItemResponse)
def add_to_cart(
    item: schemas.CartItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_current_user)
):
    # Check if product exists
    product = db.query(models.Product).filter(models.Product.id == item.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Check if same product & size already exists in cart for this user
    existing_item = db.query(models.CartItem).filter(
        models.CartItem.user_id == current_user.id,
        models.CartItem.product_id == item.product_id,
        models.CartItem.size == item.size
    ).first()

    if existing_item:
        existing_item.quantity += item.quantity
        if item.custom_name is not None:
            existing_item.custom_name = item.custom_name
        if item.custom_number is not None:
            existing_item.custom_number = item.custom_number
        db.commit()
        db.refresh(existing_item)
        return existing_item

    # Create new cart item
    new_item = models.CartItem(
        user_id=current_user.id,
        product_id=item.product_id,
        size=item.size,
        quantity=item.quantity,
        custom_name=item.custom_name,
        custom_number=item.custom_number
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item

@router.put("/{item_id}", response_model=schemas.CartItemResponse)
def update_cart_item(
    item_id: int,
    item: schemas.CartItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_current_user)
):
    existing_item = db.query(models.CartItem).filter(
        models.CartItem.id == item_id,
        models.CartItem.user_id == current_user.id
    ).first()

    if not existing_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    if item.quantity is not None:
        existing_item.quantity = item.quantity
    if item.custom_name is not None:
        existing_item.custom_name = item.custom_name
    if item.custom_number is not None:
        existing_item.custom_number = item.custom_number

    db.commit()
    db.refresh(existing_item)
    return existing_item

@router.delete("/{item_id}")
def delete_cart_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_current_user)
):
    existing_item = db.query(models.CartItem).filter(
        models.CartItem.id == item_id,
        models.CartItem.user_id == current_user.id
    ).first()

    if not existing_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    db.delete(existing_item)
    db.commit()
    return {"message": "Cart item removed"}

@router.delete("/")
def clear_cart(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_current_user)
):
    db.query(models.CartItem).filter(models.CartItem.user_id == current_user.id).delete()
    db.commit()
    return {"message": "Cart cleared"}
