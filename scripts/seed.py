"""Create an admin user and a few sample products:  python -m scripts.seed"""
from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Product, User
from app.security import hash_password

Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    if not db.execute(select(User).where(User.email == "admin@example.com")).first():
        db.add(User(email="admin@example.com", hashed_password=hash_password("admin12345"),
                    full_name="Admin", phone="+919999999999", is_admin=True))
    if not db.execute(select(Product.id)).first():
        db.add_all([
            Product(name="Wireless Mouse", description="2.4GHz ergonomic mouse", price=799, stock=50),
            Product(name="Mechanical Keyboard", description="Blue switches, RGB", price=2499, stock=25),
            Product(name="USB-C Hub", description="7-in-1 hub", price=1599, stock=10),
        ])
    db.commit()
print("Seeded. Admin: admin@example.com / admin12345")
