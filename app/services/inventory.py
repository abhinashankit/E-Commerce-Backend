"""
Inventory management - prevents overselling under concurrent order placement.

Strategy (defence in depth):
  1. Pessimistic row locks: SELECT ... FOR UPDATE on the product rows, so two
     concurrent orders for the same product are serialized at the DB.
  2. Locks are always taken in ascending product_id order -> no deadlocks between
     orders that contain the same products in different orders.
  3. A CHECK (stock >= 0) constraint on the table is the last line of defence.
"""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.errors import InsufficientStock, NotFound
from app.models import Product


def reserve_stock(db: Session, items: dict[int, int]) -> dict[int, Product]:
    """Lock the products, verify availability and decrement stock.

    `items` is {product_id: quantity}. Does NOT commit - the caller owns the
    transaction, so stock and order rows are committed atomically.
    """
    ids = sorted(items)
    stmt = (
        select(Product)
        .where(Product.id.in_(ids))
        .order_by(Product.id)
        .with_for_update()
    )
    products = {p.id: p for p in db.execute(stmt).scalars()}

    for pid in ids:
        product = products.get(pid)
        if product is None or not product.is_active:
            raise NotFound(f"Product {pid} not found")
        if product.stock < items[pid]:
            raise InsufficientStock(
                f"Only {product.stock} unit(s) of '{product.name}' left (requested {items[pid]})"
            )

    for pid in ids:
        products[pid].stock -= items[pid]
    db.flush()
    return products


def restock(db: Session, items: dict[int, int]) -> None:
    """Return reserved stock (order expired / cancelled). Atomic increments, sorted to avoid deadlocks."""
    for pid in sorted(items):
        db.execute(
            update(Product).where(Product.id == pid).values(stock=Product.stock + items[pid])
        )
