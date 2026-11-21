from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cache
from app.database import get_db
from app.errors import NotFound
from app.models import Product
from app.rate_limit import rate_limit
from app.schemas import ProductCreate, ProductOut, ProductUpdate
from app.security import require_admin

router = APIRouter(prefix="/products", tags=["catalog"], dependencies=[Depends(rate_limit())])


@router.get("", response_model=list[ProductOut])
def list_products(
    q: str | None = Query(None, max_length=100),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    key = f"products:list:v{cache.products_version()}:{q or ''}:{skip}:{limit}"
    if (hit := cache.get_json(key)) is not None:
        return hit

    stmt = select(Product).where(Product.is_active.is_(True))
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    rows = db.execute(stmt.order_by(Product.id).offset(skip).limit(limit)).scalars().all()
    data = [ProductOut.model_validate(p).model_dump(mode="json") for p in rows]
    cache.set_json(key, data)
    return data


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    key = f"products:detail:v{cache.products_version()}:{product_id}"
    if (hit := cache.get_json(key)) is not None:
        return hit
    product = db.get(Product, product_id)
    if not product or not product.is_active:
        raise NotFound("Product not found")
    data = ProductOut.model_validate(product).model_dump(mode="json")
    cache.set_json(key, data)
    return data


@router.post("", response_model=ProductOut, status_code=201, dependencies=[Depends(require_admin)])
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    cache.bump_products_version()
    return product


@router.patch("/{product_id}", response_model=ProductOut, dependencies=[Depends(require_admin)])
def update_product(product_id: int, payload: ProductUpdate, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise NotFound("Product not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    cache.bump_products_version()
    return product
