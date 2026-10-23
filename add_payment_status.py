from app import app, db
from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)

    columns = [
        column["name"]
        for column in inspector.get_columns("supplier_payment")
    ]

    if "payment_status" not in columns:
        db.session.execute(
            db.text(
                "ALTER TABLE supplier_payment "
                "ADD COLUMN payment_status "
                "VARCHAR(20) NOT NULL DEFAULT 'Paid'"
            )
        )
        db.session.commit()
        print("Payment status column added successfully.")
    else:
        print("Payment status column already exists.")