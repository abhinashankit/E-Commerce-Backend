"""Integration test (needs Postgres): proves concurrent buyers can never oversell a product."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from app.database import Base, SessionLocal, engine
from app.errors import InsufficientStock
from app.models import Product
from app.services import inventory


@pytest.fixture(scope="module", autouse=True)
def _db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Postgres not reachable")
    Base.metadata.create_all(bind=engine)


def test_no_overselling_under_concurrency():
    STOCK, BUYERS = 5, 40
    with SessionLocal() as db:
        product = Product(name="Concurrency Test Item", price=100, stock=STOCK)
        db.add(product)
        db.commit()
        pid = product.id

    def buy(_) -> bool:
        with SessionLocal() as db:
            try:
                inventory.reserve_stock(db, {pid: 1})
                db.commit()
                return True
            except InsufficientStock:
                db.rollback()
                return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(buy, range(BUYERS)))

    with SessionLocal() as db:
        final_stock = db.get(Product, pid).stock

    assert sum(results) == STOCK       # exactly 5 buyers succeed
    assert final_stock == 0            # never negative
