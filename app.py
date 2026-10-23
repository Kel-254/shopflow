from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
import os
from werkzeug.utils import secure_filename
from sqlalchemy import func
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect

load_dotenv()

app = Flask(__name__)

# -------------------------
# Application Configuration
# -------------------------
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY is missing. Configure it in your environment.")

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.config["SESSION_COOKIE_SECURE"] = False  # Local HTTP development
app.config["WTF_CSRF_ENABLED"] = True
app.config["WTF_CSRF_TIME_LIMIT"] = 3600

csrf = CSRFProtect(app)

# Create database folder
os.makedirs("instance", exist_ok=True)

# Database configuration

database_url = os.environ.get("DATABASE_URL", "").strip()

if database_url:
    # Render provides PostgreSQL; use the psycopg 3 driver.
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    # Keep using the existing local SQLite database.
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///shop.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Invoice upload configuration
UPLOAD_FOLDER = os.path.join(
    "static",
    "uploads",
    "invoices"
)

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_INVOICE_EXTENSIONS = {
    "pdf",
    "jpg",
    "jpeg",
    "png"
}


# Initialize database
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# -------------------------
# East Africa Time (EAT)
# -------------------------

def format_eat(datetime_value):
    if datetime_value is None:
        return ""

    # Treat existing SQLite timestamps as UTC
    utc_value = datetime_value.replace(
        tzinfo=timezone.utc
    )

    eat_value = utc_value.astimezone(
        timezone(timedelta(hours=3))
    )

    return eat_value.strftime(
        "%d %b %Y, %I:%M %p"
    )

app.jinja_env.globals["format_eat"] = format_eat

def format_eat_24(datetime_value):
    if datetime_value is None:
        return ""

    utc_value = datetime_value.replace(tzinfo=timezone.utc)
    eat_value = utc_value.astimezone(EAT)

    return eat_value.strftime("%d %b %Y, %H:%M")

app.jinja_env.globals["format_eat_24"] = format_eat_24

EAT = timezone(timedelta(hours=3))

# -------------------------
# Shop Model
# -------------------------

class Shop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(30))
    email = db.Column(db.String(120))
    address = db.Column(db.String(200))

    
    # Payment settings
    bank_name = db.Column(db.String(100))
    bank_account_name = db.Column(db.String(150))
    bank_account_number = db.Column(db.String(100))
    bank_branch = db.Column(db.String(100))
    bank_payment_instructions = db.Column(db.Text)

    accept_bank_transfer = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )

    accept_mpesa = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    default_low_stock_level = db.Column(
        db.Integer,
        nullable=False,
        default=5
    )

    users = db.relationship("User", backref="shop", lazy=True)

    products = db.relationship(
        "Product",
        backref="shop",
        lazy=True
    )

    def __repr__(self):
        return f"<Shop {self.name}>"


# -------------------------
# User Model
# -------------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_name = db.Column(db.String(150), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(30), default="owner")
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False)

    def __repr__(self):
        return f"<User {self.username}>"

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(150), nullable=False)

    category = db.Column(db.String(100))

    buying_price = db.Column(db.Float, nullable=False)

    selling_price = db.Column(db.Float, nullable=False)

    quantity = db.Column(db.Integer, default=0)

    low_stock_level = db.Column(db.Integer, default=5)

    supplier = db.Column(db.String(150))

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now()
    )

    def __repr__(self):
        return f"<Product {self.name}>"


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    total_amount = db.Column(db.Float, nullable=False)

    
    payment_method = db.Column(
        db.String(20),
        nullable=False,
        default="Cash"
    )

    
    payment_status = db.Column(
        db.String(20),
        nullable=False,
        default="Paid"
    )

    amount_paid = db.Column(
        db.Float,
        nullable=False,
        default=0.0
    )

    payment_reference = db.Column(
        db.String(100),
        nullable=True
    )


    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now()
    )

    items = db.relationship(
        "SaleItem",
        backref="sale",
        lazy=True,
        cascade="all, delete-orphan"
    )


class SaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    quantity = db.Column(db.Integer, nullable=False)

    selling_price = db.Column(db.Float, nullable=False)

    total_price = db.Column(db.Float, nullable=False)

    sale_id = db.Column(
        db.Integer,
        db.ForeignKey("sale.id"),
        nullable=False
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.id"),
        nullable=False
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    product = db.relationship(
         "Product",
          backref="sale_items"
    )


# =========================================
# SUPPLIER
# =========================================

class Supplier(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(150),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default="Active",
        nullable=False
    )

    phone = db.Column(
        db.String(30)
    )

    email = db.Column(
        db.String(120)
    )

    address = db.Column(
        db.String(200)
    )

    kra_pin = db.Column(
        db.String(30)
    )

    notes = db.Column(
        db.Text
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now()
    )

    purchase_orders = db.relationship(
        "PurchaseOrder",
        backref="supplier",
        lazy=True
    )

    def __repr__(self):
        return f"<Supplier {self.name}>"


# =========================================
# PURCHASE ORDER
# =========================================

class PurchaseOrder(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    order_number = db.Column(
        db.String(50),
        nullable=False
    )

    order_date = db.Column(
        db.DateTime,
        default=db.func.now()
    )

    status = db.Column(
        db.String(30),
        default="Pending"
    )

    expected_total = db.Column(
        db.Float,
        default=0
    )

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("supplier.id"),
        nullable=False
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    notes = db.Column(
        db.Text
    )

    items = db.relationship(
        "PurchaseOrderItem",
        backref="purchase_order",
        lazy=True,
        cascade="all, delete-orphan"
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now()
    )

    def __repr__(self):
        return f"<PurchaseOrder {self.order_number}>"


# =========================================
# PURCHASE ORDER ITEM
# =========================================

class PurchaseOrderItem(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    quantity_ordered = db.Column(
        db.Integer,
        nullable=False
    )

    quantity_received = db.Column(
        db.Integer,
        default=0
    )

    buying_price = db.Column(
        db.Float,
        nullable=False
    )

    total_price = db.Column(
        db.Float,
        nullable=False
    )

    purchase_order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_order.id"),
        nullable=False
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.id"),
        nullable=False
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    product = db.relationship(
        "Product",
        backref="purchase_order_items"
    )

    def __repr__(self):
        return f"<PurchaseOrderItem {self.id}>"


# =========================================
# DELIVERY / STOCK RECEIVING
# =========================================

class StockDelivery(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    delivery_number = db.Column(
        db.String(50),
        nullable=False
    )

    delivery_date = db.Column(
        db.DateTime,
        default=db.func.now()
    )

    invoice_number = db.Column(
        db.String(100)
    )

    invoice_date = db.Column(
        db.DateTime
    )

    invoice_file = db.Column(
        db.String(255)
    )

    total_amount = db.Column(
        db.Float,
        default=0
    )

    notes = db.Column(
        db.Text
    )

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("supplier.id"),
        nullable=False
    )

    purchase_order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_order.id")
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    supplier = db.relationship("Supplier")

    purchase_order = db.relationship("PurchaseOrder")

    items = db.relationship(
        "StockDeliveryItem",
        backref="delivery",
        lazy=True,
        cascade="all, delete-orphan"
    )

    # Supplier payments linked to this delivery
    supplier_payments = db.relationship(
        "SupplierPayment",
        back_populates="delivery",
        cascade="all, delete-orphan"
    )


    created_at = db.Column(
        db.DateTime,
        default=db.func.now()
    )

    def __repr__(self):
        return f"<StockDelivery {self.delivery_number}>"


# =========================================
# DELIVERY ITEM
# =========================================

class StockDeliveryItem(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    quantity_received = db.Column(
        db.Integer,
        nullable=False
    )

    buying_price = db.Column(
        db.Float,
        nullable=False
    )

    total_price = db.Column(
        db.Float,
        nullable=False
    )

    delivery_id = db.Column(
        db.Integer,
        db.ForeignKey("stock_delivery.id"),
        nullable=False
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.id"),
        nullable=False
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    product = db.relationship(
        "Product",
        backref="delivery_items"
    )

    def __repr__(self):
        return f"<StockDeliveryItem {self.id}>"



# =========================================
# SUPPLIER PAYMENTS
# =========================================

class SupplierPayment(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    amount = db.Column(
        db.Float,
        nullable=False
    )

    payment_date = db.Column(
        db.DateTime,
        default=db.func.now(),
        nullable=False
    )

    payment_method = db.Column(
        db.String(50),
        default="Cash"
    )

    reference_number = db.Column(
        db.String(100)
    )

    payment_status = db.Column(
        db.String(20),
        nullable=False,
        default="Paid"
    )

    notes = db.Column(
        db.Text
    )

    supplier_id = db.Column(
        db.Integer,
        db.ForeignKey("supplier.id"),
        nullable=False
    )

    delivery_id = db.Column(
        db.Integer,
        db.ForeignKey("stock_delivery.id"),
        nullable=False
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    supplier = db.relationship("Supplier")

    delivery = db.relationship(
         "StockDelivery",
         back_populates="supplier_payments")

    def __repr__(self):
        return f"<SupplierPayment {self.amount}>"



# =========================================
# STOCK MOVEMENT
# =========================================

class StockMovement(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    movement_type = db.Column(
        db.String(50),
        nullable=False
    )

    quantity = db.Column(
        db.Integer,
        nullable=False
    )

    previous_quantity = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    new_quantity = db.Column(
        db.Integer,
        nullable=False,
        default=0
    )

    reference_type = db.Column(
        db.String(50)
    )

    reference_id = db.Column(
        db.Integer
    )

    notes = db.Column(
        db.Text
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("product.id"),
        nullable=False
    )

    shop_id = db.Column(
        db.Integer,
        db.ForeignKey("shop.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=db.func.now()
    )

    product = db.relationship(
        "Product",
        backref="stock_movements"
    )

    def __repr__(self):
        return f"<StockMovement {self.movement_type}>"

    

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# -------------------------
# Home Page
# -------------------------

@app.route("/")
def home():
    return "Lena MiniMart System is running!"

# Registration #

@app.route("/register-shop", methods=["GET", "POST"])
def register_shop():
    if request.method == "POST":
        # Read and clean form values
        shop_name = request.form.get("shop_name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        address = request.form.get("address", "").strip()

        owner_name = request.form.get("owner_name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # Validate required fields
        if not all([shop_name, email, owner_name, username, password]):
            flash("Please fill in all required fields.", "error")
            return render_template("register_shop.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return render_template("register_shop.html")

        # Check for an existing owner email before creating a shop
        existing_user = User.query.filter(
            db.func.lower(User.email) == email
        ).first()

        if existing_user:
            flash(
                "This email is already registered. Please use another email.",
                "error"
            )
            return render_template("register_shop.html")

        try:
            # Create the shop and owner in one transaction
            new_shop = Shop(
                name=shop_name,
                phone=phone or None,
                email=email,
                address=address or None
            )

            db.session.add(new_shop)
            db.session.flush()

            new_user = User(
                owner_name=owner_name,
                username=username,
                email=email,
                password=generate_password_hash(password),
                role="owner",
                shop_id=new_shop.id
            )

            db.session.add(new_user)
            db.session.commit()

        except Exception as error:
            db.session.rollback()

            # Handle a duplicate email, including a concurrent registration
            from sqlalchemy.exc import IntegrityError

            if isinstance(error, IntegrityError):
                app.logger.warning(
                    "Shop registration rejected by a database constraint."
                )
                flash(
                    "That email is already registered, or some registration "
                    "details conflict with the database. Please check and try again.",
                    "error"
                )
                return render_template("register_shop.html")

            app.logger.exception("Shop registration failed.")
            flash(
                "Registration could not be completed. Please try again.",
                "error"
            )
            return render_template("register_shop.html")

        flash("Your shop has been registered successfully. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register_shop.html")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):

            login_user(user)

            return redirect(url_for("dashboard"))

        return "Invalid username or password."

    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():

    # Get products for the current shop
    products = Product.query.filter_by(
        shop_id=current_user.shop_id
    ).all()

    # Get all sales for the current shop
    sales = Sale.query.filter_by(
        shop_id=current_user.shop_id
    ).all()

    # Total number of products
    total_products = len(products)

    # Total quantity currently in stock
    total_stock = sum(
        product.quantity
        for product in products
    )

    # Count low-stock products
    low_stock = sum(
        1
        for product in products
        if product.quantity <= product.low_stock_level
    )

    # Today's sales
    today = db.func.date(db.func.now())

    todays_sales = Sale.query.filter(
        Sale.shop_id == current_user.shop_id,
        db.func.date(Sale.created_at) == today
    ).all()

    # Today's revenue
    todays_revenue = sum(
        sale.total_amount
        for sale in todays_sales
    )

    # Number of sales made today
    sales_today = len(todays_sales)
    recent_sales = Sale.query.filter_by(
        shop_id=current_user.shop_id
        ).order_by(
           Sale.created_at.desc()
        ).limit(5).all()

    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_stock=total_stock,
        low_stock=low_stock,
        todays_revenue=todays_revenue,
        sales_today=sales_today,
        recent_sales=recent_sales,
        products=products
    )



@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    shop = Shop.query.filter_by(
        id=current_user.shop_id
    ).first_or_404()

    if request.method == "POST":
        form_type = request.form.get("form_type", "")

        # Save Shop Profile
        if form_type == "shop_profile":
            name = request.form.get("name", "").strip()
            phone = request.form.get("phone", "").strip()
            email = request.form.get("email", "").strip()
            address = request.form.get("address", "").strip()

            low_stock_level = request.form.get(
                "default_low_stock_level", "5"
            ).strip()

            if not name:
                flash("Shop name is required.", "error")
                return render_template(
                    "settings.html", shop=shop
                )

            try:
                low_stock_level = int(low_stock_level)

                if low_stock_level < 0:
                    raise ValueError

            except ValueError:
                flash(
                    "Default low-stock level must be zero or greater.",
                    "error"
                )
                return render_template(
                    "settings.html", shop=shop
                )

            shop.name = name
            shop.phone = phone or None
            shop.email = email or None
            shop.address = address or None
            shop.default_low_stock_level = low_stock_level

            db.session.commit()

            flash(
                "Shop profile updated successfully!",
                "success"
            )

        # Save Payment Settings
        elif form_type == "payment_settings":
            accept_bank_transfer = (
                request.form.get("accept_bank_transfer") == "on"
            )

            accept_mpesa = (
                request.form.get("accept_mpesa") == "on"
            )

            bank_name = request.form.get(
                "bank_name", ""
            ).strip()

            bank_account_name = request.form.get(
                "bank_account_name", ""
            ).strip()

            bank_account_number = request.form.get(
                "bank_account_number", ""
            ).strip()

            bank_branch = request.form.get(
                "bank_branch", ""
            ).strip()

            bank_payment_instructions = request.form.get(
                "bank_payment_instructions", ""
            ).strip()

            # Require bank details when bank transfers are enabled
            if accept_bank_transfer and not all([
                bank_name,
                bank_account_name,
                bank_account_number
            ]):
                flash(
                    "Enter the bank name, account name, and "
                    "account number to enable bank transfers.",
                    "error"
                )
                return render_template(
                    "settings.html", shop=shop
                )

            shop.accept_bank_transfer = accept_bank_transfer
            shop.accept_mpesa = accept_mpesa

            shop.bank_name = bank_name or None
            shop.bank_account_name = bank_account_name or None
            shop.bank_account_number = bank_account_number or None
            shop.bank_branch = bank_branch or None
            shop.bank_payment_instructions = (
                bank_payment_instructions or None
            )

            db.session.commit()

            flash(
                "Payment settings updated successfully!",
                "success"
            )

        else:
            flash(
                "Invalid settings form. Please try again.",
                "error"
            )

        return redirect(url_for("settings"))

    return render_template("settings.html", shop=shop)



@app.route("/settings/change-password", methods=["POST"])
@login_required
def change_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    user = User.query.get_or_404(current_user.id)

    if not check_password_hash(user.password, current_password):
        flash("Your current password is incorrect.", "error")
        return redirect(url_for("settings"))

    if len(new_password) < 8:
        flash("Your new password must contain at least 8 characters.", "error")
        return redirect(url_for("settings"))

    if new_password != confirm_password:
        flash("The new passwords do not match.", "error")
        return redirect(url_for("settings"))

    user.password = generate_password_hash(new_password)
    db.session.commit()

    flash("Your password has been changed successfully.", "success")
    return redirect(url_for("settings"))


@app.route("/reports")
@login_required
def reports():
    today = datetime.now().date()

    start_date_str = request.args.get(
        "start_date",
        today.replace(day=1).isoformat()
    )

    end_date_str = request.args.get(
        "end_date",
        today.isoformat()
    )

    try:
        start_date = datetime.strptime(
            start_date_str, "%Y-%m-%d"
        ).date()

        end_date = datetime.strptime(
            end_date_str, "%Y-%m-%d"
        ).date()

        if start_date > end_date:
            flash("Start date cannot be after end date.", "error")
            return redirect(url_for("reports"))

    except ValueError:
        flash("Please select valid report dates.", "error")
        return redirect(url_for("reports"))

    start_datetime = datetime.combine(
        start_date, datetime.min.time()
    )

    end_datetime = datetime.combine(
        end_date + timedelta(days=1),
        datetime.min.time()
    )

    sales_query = Sale.query.filter(
        Sale.shop_id == current_user.shop_id,
        Sale.created_at >= start_datetime,
        Sale.created_at < end_datetime
    )

    total_sales = sales_query.with_entities(
        func.coalesce(func.sum(Sale.total_amount), 0)
    ).scalar()

    total_transactions = sales_query.count()

    total_items_sold = db.session.query(
        func.coalesce(func.sum(SaleItem.quantity), 0)
    ).join(
        Sale, SaleItem.sale_id == Sale.id
    ).filter(
        SaleItem.shop_id == current_user.shop_id,
        Sale.created_at >= start_datetime,
        Sale.created_at < end_datetime
    ).scalar()

    average_sale = (
        total_sales / total_transactions
        if total_transactions else 0
    )

    recent_sales = sales_query.order_by(
        Sale.created_at.desc()
    ).all()

    # Daily sales revenue for the selected period
    daily_sales = db.session.query(
        func.date(Sale.created_at).label("sale_date"),
        func.sum(Sale.total_amount).label("daily_revenue")
    ).filter(
        Sale.shop_id == current_user.shop_id,
        Sale.created_at >= start_datetime,
        Sale.created_at < end_datetime
    ).group_by(
        func.date(Sale.created_at)
    ).order_by(
        func.date(Sale.created_at)
    ).all()

    # Top products
    top_products = db.session.query(
        Product.name.label("product_name"),
        func.sum(SaleItem.quantity).label("quantity_sold"),
        func.sum(SaleItem.total_price).label("revenue")
    ).join(
        SaleItem, SaleItem.product_id == Product.id
    ).join(
        Sale, SaleItem.sale_id == Sale.id
    ).filter(
        Sale.shop_id == current_user.shop_id,
        SaleItem.shop_id == current_user.shop_id,
        Sale.created_at >= start_datetime,
        Sale.created_at < end_datetime
    ).group_by(
        Product.id,
        Product.name
    ).order_by(
        func.sum(SaleItem.quantity).desc()
    ).limit(5).all()

    return render_template(
        "reports.html",
        start_date=start_date_str,
        end_date=end_date_str,
        total_sales=total_sales,
        total_transactions=total_transactions,
        total_items_sold=total_items_sold,
        average_sale=average_sale,
        recent_sales=recent_sales,
        top_products=top_products,
        daily_sales=daily_sales
    )


@app.route("/products")
@login_required
def products():

    products = Product.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(Product.name.asc()).all()

    total_products = len(products)

    total_items = sum(
        product.quantity for product in products
    )

    low_stock = sum(
        1 for product in products
        if product.quantity <= product.low_stock_level
    )

    stock_value = sum(
        product.buying_price * product.quantity
        for product in products
    )

    return render_template(
        "products.html",
        products=products,
        total_products=total_products,
        total_items=total_items,
        low_stock=low_stock,
        stock_value=stock_value
    )


@app.route("/products/add", methods=["GET", "POST"])
@login_required
def add_product():
    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            category = request.form["category"].strip()
            buying_price = float(request.form["buying_price"])
            selling_price = float(request.form["selling_price"])
            quantity = int(request.form["quantity"])

            low_stock_level = int(
                request.form.get(
                    "low_stock_level",
                    str(current_user.shop.default_low_stock_level)
                )
            )

            supplier = request.form.get("supplier", "").strip()

            if not name or not category:
                flash("Product name and category are required.", "error")
                return render_template("add_product.html")

            if buying_price < 0 or selling_price < 0:
                flash("Prices cannot be negative.", "error")
                return render_template("add_product.html")

            if quantity < 0 or low_stock_level < 0:
                flash(
                    "Quantity and low-stock level cannot be negative.",
                    "error"
                )
                return render_template("add_product.html")

        except (ValueError, TypeError):
            flash(
                "Please enter valid numbers for prices and quantities.",
                "error"
            )
            return render_template("add_product.html")

        new_product = Product(
            name=name,
            category=category,
            buying_price=buying_price,
            selling_price=selling_price,
            quantity=quantity,
            low_stock_level=low_stock_level,
            supplier=supplier,
            shop_id=current_user.shop_id
        )

        db.session.add(new_product)
        db.session.commit()

        flash("Product added successfully!", "success")
        return redirect(url_for("products"))

    return render_template("add_product.html")


@app.route("/products/edit/<int:product_id>", methods=["GET", "POST"])
@login_required
def edit_product(product_id):

    product = Product.query.filter_by(
        id=product_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    if request.method == "POST":

        product.name = request.form["name"]
        product.category = request.form["category"]
        product.buying_price = float(request.form["buying_price"])
        product.selling_price = float(request.form["selling_price"])
        product.quantity = int(request.form["quantity"])
        product.low_stock_level = int(request.form["low_stock_level"])
        product.supplier = request.form["supplier"]

        db.session.commit()

        return redirect(url_for("products"))

    return render_template(
        "edit_product.html",
        product=product
    )


@app.route("/stock-history")
@login_required
def stock_history():

    # Get filter values from the URL
    search = request.args.get("search", "").strip()
    movement_type = request.args.get("movement_type", "").strip()
    selected_date = request.args.get("date", "").strip()
    delivery_id = request.args.get("delivery_id", type=int)

    # Start with this shop's stock movements only
    query = StockMovement.query.filter_by(
        shop_id=current_user.shop_id
    )

    # FILTER BY A SPECIFIC DELIVERY
    delivery = None

    if delivery_id:
        delivery = StockDelivery.query.filter_by(
            id=delivery_id,
            shop_id=current_user.shop_id
        ).first_or_404()

        query = query.filter(
            StockMovement.reference_type == "Delivery",
            StockMovement.reference_id == delivery.id
        )

    # PRODUCT SEARCH
    if search:
        query = query.join(
            Product,
            StockMovement.product_id == Product.id
        ).filter(
            Product.name.ilike(f"%{search}%"),
            Product.shop_id == current_user.shop_id
        )

    # MOVEMENT TYPE FILTER
    if movement_type:
        query = query.filter(
            StockMovement.movement_type == movement_type
        )

    # DATE FILTER
    if selected_date:
        try:
            selected_date_obj = datetime.strptime(
                selected_date,
                "%Y-%m-%d"
            )

            next_date = selected_date_obj.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )

            following_date = next_date + timedelta(days=1)

            query = query.filter(
                StockMovement.created_at >= next_date,
                StockMovement.created_at < following_date
            )

        except ValueError:
            selected_date = ""

    
     # GET MOVEMENTS AFTER APPLYING ALL FILTERS
    movements = query.order_by(
        StockMovement.created_at.desc()
    ).all()
    
    # Get delivery details using one query
    delivery_references = {}

    delivery_ids = {
        movement.reference_id
        for movement in movements
        if (
            movement.reference_type == "Delivery"
            and movement.reference_id
        )
    }

    if delivery_ids:
        deliveries = StockDelivery.query.filter(
            StockDelivery.id.in_(delivery_ids),
            StockDelivery.shop_id == current_user.shop_id
        ).all()

        deliveries_by_id = {
            item.id: item
            for item in deliveries
        }

        for movement in movements:
            if movement.reference_type == "Delivery":
                referenced_delivery = deliveries_by_id.get(
                    movement.reference_id
                )

                if referenced_delivery:
                    delivery_references[movement.id] = (
                        referenced_delivery
                    )


    # SUMMARY CARDS
    total_movements = len(movements)

    total_stock_in = sum(
        movement.quantity
        for movement in movements
        if movement.movement_type == "Stock In"
    )

    total_stock_out = sum(
        movement.quantity
        for movement in movements
        if movement.movement_type == "Stock Out"
    )

    # Current stock remains the shop's actual inventory,
    # regardless of the filters applied above.
    total_current_stock = db.session.query(
        db.func.coalesce(
            db.func.sum(Product.quantity),
            0
        )
    ).filter(
        Product.shop_id == current_user.shop_id
    ).scalar()

    # WAS A FILTER USED?
    filters_applied = bool(
        search or
        movement_type or
        selected_date or
        delivery_id
    )

    return render_template(
        "stock_history.html",
        movements=movements,
        total_movements=total_movements,
        total_stock_in=total_stock_in,
        total_stock_out=total_stock_out,
        total_current_stock=total_current_stock,
        search=search,
        movement_type=movement_type,
        selected_date=selected_date,
        filters_applied=filters_applied,
        delivery_references=delivery_references,
        delivery_id=delivery_id,
        delivery=delivery
    )

@app.route("/sales")
@login_required
def sales():

    products = Product.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(Product.name.asc()).all()

    return render_template(
        "sales.html",
        products=products
    )


@app.route("/sales/complete", methods=["POST"])
@login_required
def complete_sale():
    from flask import jsonify

    try:
        product_id = request.form.get("product_id", type=int)
        quantity = request.form.get("quantity", type=int)

        if not product_id or not quantity:
            message = "Please select a product and enter a quantity."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message=message), 400
            return message, 400

        if quantity <= 0:
            message = "Quantity must be greater than zero."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message=message), 400
            return message, 400

        product = Product.query.filter_by(
            id=product_id,
            shop_id=current_user.shop_id
        ).first()

        if product is None:
            message = "Product not found in your shop."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message=message), 404
            return message, 404

        if quantity > product.quantity:
            message = "Not enough stock available."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message=message), 400
            return message, 400

        shop = Shop.query.filter_by(
            id=current_user.shop_id
        ).first()

        if shop is None:
            message = "Shop not found."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message=message), 404
            return message, 404

        payment_method = request.form.get(
            "payment_method", "Cash"
        ).strip()

        if payment_method not in ["Cash", "M-Pesa", "Bank"]:
            message = "Invalid payment method."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message=message), 400
            return message, 400

        if payment_method == "Bank" and not shop.accept_bank_transfer:
            message = "Bank transfers are not enabled for this shop."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message=message), 400
            return message, 400

        if payment_method == "M-Pesa" and not shop.accept_mpesa:
            message = "M-Pesa payments are not enabled for this shop."
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify(success=False, message=message), 400
            return message, 400

        total_amount = product.selling_price * quantity

        if payment_method == "Cash":
            payment_status = "Paid"
            amount_paid = total_amount
        else:
            payment_status = "Pending"
            amount_paid = 0.0

        new_sale = Sale(
            total_amount=total_amount,
            payment_method=payment_method,
            payment_status=payment_status,
            amount_paid=amount_paid,
            payment_reference=None,
            shop_id=current_user.shop_id
        )

        db.session.add(new_sale)
        db.session.flush()

        sale_item = SaleItem(
            quantity=quantity,
            selling_price=product.selling_price,
            total_price=total_amount,
            sale_id=new_sale.id,
            product_id=product.id,
            shop_id=current_user.shop_id
        )

        db.session.add(sale_item)

        if payment_status == "Paid":
            previous_quantity = product.quantity
            product.quantity -= quantity

            db.session.add(StockMovement(
                movement_type="Stock Out",
                quantity=quantity,
                previous_quantity=previous_quantity,
                new_quantity=product.quantity,
                reference_type="Sale",
                reference_id=new_sale.id,
                notes=f"Sale #{new_sale.id}",
                product_id=product.id,
                shop_id=current_user.shop_id
            ))

        db.session.commit()

        sale_url = url_for(
            "sale_details",
            sale_id=new_sale.id
        )

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(
                success=True,
                sale_id=new_sale.id,
                sale_url=sale_url,
                payment_method=payment_method,
                payment_status=payment_status,
                total_amount=total_amount
            )

        return redirect(sale_url)

    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to complete sale")

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(
                success=False,
                message="The sale could not be saved. Please try again."
            ), 500

        return "The sale could not be saved. Please try again.", 500


@app.route("/sales/history")
@login_required
def sales_history():

    # Get all sales belonging to the current shop
    sales = Sale.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(
        Sale.created_at.desc()
    ).all()

    # Only confirmed paid sales count toward sales totals
    paid_sales = [
        sale for sale in sales
        if sale.payment_status == "Paid"
    ]

    # Total number of paid sales
    total_sales = len(paid_sales)

    # Total confirmed revenue
    total_revenue = sum(
        sale.amount_paid or 0.0
        for sale in paid_sales
    )

    # Total items in paid sales
    total_items_sold = sum(
        item.quantity
        for sale in paid_sales
        for item in sale.items
    )

    # Today's paid sales
    today = db.func.date(db.func.now())

    todays_sales = Sale.query.filter(
        Sale.shop_id == current_user.shop_id,
        Sale.payment_status == "Paid",
        db.func.date(Sale.created_at) == today
    ).all()

    todays_revenue = sum(
        sale.amount_paid or 0.0
        for sale in todays_sales
    )

    return render_template(
        "sales_history.html",
        sales=sales,
        total_sales=total_sales,
        total_revenue=total_revenue,
        total_items_sold=total_items_sold,
        todays_revenue=todays_revenue
    )


@app.route("/sales/<int:sale_id>")
@login_required
def sale_details(sale_id):

    sale = Sale.query.filter_by(
        id=sale_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    return render_template(
        "sale_details.html",
        sale=sale
    )



@app.route(
    "/sales/<int:sale_id>/confirm-bank-payment",
    methods=["POST"]
)
@login_required
def confirm_bank_payment(sale_id):

    sale = Sale.query.filter_by(
        id=sale_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    if sale.payment_method != "Bank":
        flash("Only bank transfer sales can be confirmed here.", "error")
        return redirect(url_for("sale_details", sale_id=sale.id))

    if sale.payment_status != "Pending":
        flash("This sale is not awaiting payment confirmation.", "error")
        return redirect(url_for("sale_details", sale_id=sale.id))

    reference = request.form.get("payment_reference", "").strip()

    if not reference:
        flash("Enter the bank transaction reference.", "error")
        return redirect(url_for("sale_details", sale_id=sale.id))

    # IMPORTANT: verify the transfer in the actual bank account first.
    # A reference entered by a user is not proof of payment.

    # Reject a reference already used for another paid sale in this shop.
    duplicate_reference = Sale.query.filter(
        Sale.shop_id == current_user.shop_id,
        Sale.payment_status == "Paid",
        Sale.payment_reference.isnot(None),
        db.func.lower(Sale.payment_reference) == reference.lower(),
        Sale.id != sale.id
    ).first()

    if duplicate_reference:
        flash(
            "This transaction reference has already been used.",
            "error"
        )
        return redirect(url_for("sale_details", sale_id=sale.id))

    sale_items = SaleItem.query.filter_by(
        sale_id=sale.id,
        shop_id=current_user.shop_id
    ).all()

    if not sale_items:
        flash("No items were found for this sale.", "error")
        return redirect(url_for("sale_details", sale_id=sale.id))

    # Validate every product before making any changes.
    products_to_update = []

    for item in sale_items:
        product = Product.query.filter_by(
            id=item.product_id,
            shop_id=current_user.shop_id
        ).first()

        if product is None:
            flash("A product in this sale could not be found.", "error")
            return redirect(url_for("sale_details", sale_id=sale.id))

        if item.quantity <= 0 or item.quantity > product.quantity:
            flash(
                f"Not enough stock for {product.name}. "
                "Review inventory before confirming.",
                "error"
            )
            return redirect(url_for("sale_details", sale_id=sale.id))

        products_to_update.append((item, product))

    try:
        # Atomically claim the pending sale. Only one request should
        # be able to change this sale from Pending to Paid.
        updated_rows = Sale.query.filter_by(
            id=sale.id,
            shop_id=current_user.shop_id,
            payment_method="Bank",
            payment_status="Pending"
        ).update(
            {
                "payment_status": "Paid",
                "amount_paid": sale.total_amount,
                "payment_reference": reference
            },
            synchronize_session=False
        )

        if updated_rows != 1:
            db.session.rollback()
            flash(
                "This sale was already processed. Refresh and check its status.",
                "error"
            )
            return redirect(url_for("sale_details", sale_id=sale.id))

        # Deduct stock and record each movement in the same transaction.
        for item, product in products_to_update:
            previous_quantity = product.quantity
            product.quantity -= item.quantity

            db.session.add(StockMovement(
                movement_type="Stock Out",
                quantity=item.quantity,
                previous_quantity=previous_quantity,
                new_quantity=product.quantity,
                reference_type="Sale",
                reference_id=sale.id,
                notes=f"Bank transfer confirmed for Sale #{sale.id}",
                product_id=product.id,
                shop_id=current_user.shop_id
            ))

        db.session.commit()

    except Exception:
        db.session.rollback()
        app.logger.exception(
            "Bank confirmation failed for sale %s", sale_id
        )
        flash(
            "Confirmation failed. Check the sale status before trying again.",
            "error"
        )
        return redirect(url_for("sale_details", sale_id=sale_id))

    flash(
        "Bank payment confirmed and stock updated successfully.",
        "success"
    )
    return redirect(url_for("sale_details", sale_id=sale_id))


# =========================================
# SUPPLIERS
# =========================================

@app.route("/suppliers")
@login_required
def suppliers():

    suppliers = Supplier.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(
        Supplier.name.asc()
    ).all()

    return render_template(
        "suppliers.html",
        suppliers=suppliers
    )


@app.route("/suppliers/add", methods=["GET", "POST"])
@login_required
def add_supplier():

    if request.method == "POST":

        name = request.form["name"].strip()
        phone = request.form["phone"].strip()
        email = request.form["email"].strip()
        address = request.form["address"].strip()
        kra_pin = request.form["kra_pin"].strip()
        notes = request.form["notes"].strip()

        if not name:
            return "Supplier name is required."

        new_supplier = Supplier(
            name=name,
            phone=phone,
            email=email,
            address=address,
            kra_pin=kra_pin,
            notes=notes,
            shop_id=current_user.shop_id
        )

        db.session.add(new_supplier)
        db.session.commit()

        return redirect(url_for("suppliers"))

    return render_template("add_supplier.html")


@app.route("/suppliers/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
def edit_supplier(supplier_id):

    supplier = Supplier.query.filter_by(
        id=supplier_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    if request.method == "POST":

        name = request.form["name"].strip()
        phone = request.form["phone"].strip()
        email = request.form["email"].strip()
        address = request.form["address"].strip()
        kra_pin = request.form["kra_pin"].strip()
        notes = request.form["notes"].strip()

        status = request.form.get(
            "status",
            "Active"
        )

        if not name:
            return "Supplier name is required."

        supplier.name = name
        supplier.phone = phone
        supplier.email = email
        supplier.address = address
        supplier.kra_pin = kra_pin
        supplier.notes = notes
        supplier.status= status

        db.session.commit()

        return redirect(
            url_for(
                "supplier_details",
                supplier_id=supplier.id
            )
        )

    return render_template(
        "edit_supplier.html",
        supplier=supplier
    )


# =========================================
# SUPPLIER DETAILS
# =========================================


@app.route("/suppliers/<int:supplier_id>")
@login_required
def supplier_details(supplier_id):

    supplier = Supplier.query.filter_by(
        id=supplier_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    purchase_orders = PurchaseOrder.query.filter_by(
        supplier_id=supplier.id,
        shop_id=current_user.shop_id
    ).order_by(
        PurchaseOrder.order_date.desc()
    ).all()

    deliveries = StockDelivery.query.filter_by(
        supplier_id=supplier.id,
        shop_id=current_user.shop_id
    ).order_by(
        StockDelivery.delivery_date.desc()
    ).all()

     # Load payment history for this supplier
    payments = SupplierPayment.query.filter_by(
        supplier_id=supplier.id,
        shop_id=current_user.shop_id
    ).order_by(
        SupplierPayment.payment_date.desc()
    ).all()

    # Calculate supplier totals
    total_purchase_value = sum(
        order.expected_total or 0
        for order in purchase_orders
    )


    total_purchase_value = sum(
        order.expected_total or 0
        for order in purchase_orders
    )

    total_deliveries_value = sum(
        delivery.total_amount or 0
        for delivery in deliveries
    )

    total_payments_value = (
        db.session.query(func.sum(SupplierPayment.amount))
        .filter_by(
            supplier_id=supplier.id,
            shop_id=current_user.shop_id
        )
        .scalar()
        or 0
    )

    outstanding_value = max(
        total_deliveries_value - total_payments_value,
        0
    )

    return render_template(
        "supplier_details.html",
        supplier=supplier,
        purchase_orders=purchase_orders,
        deliveries=deliveries,
        payments=payments,
        total_purchase_value=total_purchase_value,
        total_deliveries_value=total_deliveries_value,
        total_payments_value=total_payments_value,
        outstanding_value=outstanding_value
    )


@app.route("/suppliers/<int:supplier_id>/deliveries/<int:delivery_id>/pay", methods=["POST"])
@login_required
def record_supplier_payment(supplier_id, delivery_id):

    supplier = Supplier.query.filter_by(
        id=supplier_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    delivery = StockDelivery.query.filter_by(
        id=delivery_id,
        supplier_id=supplier.id,
        shop_id=current_user.shop_id
    ).first_or_404()

    try:
        amount = float(request.form.get("amount", 0))
    except (ValueError, TypeError):
        flash("Please enter a valid payment amount.", "error")
        return redirect(
            url_for("supplier_details", supplier_id=supplier.id)
        )

    if amount <= 0:
        flash("Payment amount must be greater than zero.", "error")
        return redirect(
            url_for("supplier_details", supplier_id=supplier.id)
        )

    paid_so_far = (
        db.session.query(func.sum(SupplierPayment.amount))
        .filter_by(
            supplier_id=supplier.id,
            delivery_id=delivery.id,
            shop_id=current_user.shop_id
        )
        .scalar()
        or 0
    )

    balance = max((delivery.total_amount or 0) - paid_so_far, 0)

    if amount > balance:
        flash(
            f"Payment exceeds the outstanding balance of KSh {balance:,.2f}.",
            "error"
        )
        return redirect(
            url_for("supplier_details", supplier_id=supplier.id)
        )

    payment = SupplierPayment(
        amount=amount,
        payment_date=datetime.now(),
        payment_method=request.form.get("payment_method", "Cash"),
        reference_number=request.form.get("reference_number", "").strip(),
        notes=request.form.get("notes", "").strip(),
        supplier_id=supplier.id,
        delivery_id=delivery.id,
        shop_id=current_user.shop_id
    )

    try:
        db.session.add(payment)
        db.session.commit()
        flash("Supplier payment recorded successfully!", "success")
    except Exception:
        db.session.rollback()
        flash("Could not record the payment. Please try again.", "error")

    return redirect(
        url_for("supplier_details", supplier_id=supplier.id)
    )


@app.route("/supplier-debts")
@login_required
def supplier_debts():
    suppliers = Supplier.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(Supplier.name.asc()).all()

    supplier_summaries = []
    grand_total_deliveries = 0
    grand_total_payments = 0

    for supplier in suppliers:
        total_deliveries = (
            db.session.query(func.sum(StockDelivery.total_amount))
            .filter_by(
                supplier_id=supplier.id,
                shop_id=current_user.shop_id
            )
            .scalar() or 0
        )

        total_payments = (
            db.session.query(func.sum(SupplierPayment.amount))
            .filter_by(
                supplier_id=supplier.id,
                shop_id=current_user.shop_id
            )
            .scalar() or 0
        )

        outstanding = max(total_deliveries - total_payments, 0)

        supplier_summaries.append({
            "supplier": supplier,
            "total_deliveries": total_deliveries,
            "total_payments": total_payments,
            "outstanding": outstanding
        })

        grand_total_deliveries += total_deliveries
        grand_total_payments += total_payments

    return render_template(
        "supplier_debts.html",
        supplier_summaries=supplier_summaries,
        grand_total_deliveries=grand_total_deliveries,
        grand_total_payments=grand_total_payments,
        grand_total_outstanding=max(
            grand_total_deliveries - grand_total_payments, 0
        )
    )



# =========================================
# PURCHASE ORDERS
# =========================================

@app.route("/purchases")
@login_required
def purchases():

    purchase_orders = PurchaseOrder.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(
        PurchaseOrder.order_date.desc()
    ).all()

    return render_template(
        "purchases.html",
        purchase_orders=purchase_orders
    )


# =========================================
# VIEW PURCHASE ORDER
# =========================================

@app.route("/purchases/<int:purchase_id>")
@login_required
def purchase_details(purchase_id):

    purchase_order = PurchaseOrder.query.options(
        db.joinedload(PurchaseOrder.supplier),
        db.selectinload(PurchaseOrder.items).joinedload(
            PurchaseOrderItem.product
        )
    ).filter_by(
        id=purchase_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    deliveries = StockDelivery.query.options(
        db.selectinload(StockDelivery.items).joinedload(
            StockDeliveryItem.product
        )
    ).filter_by(
        purchase_order_id=purchase_order.id,
        shop_id=current_user.shop_id
    ).order_by(
        StockDelivery.delivery_date.desc()
    ).all()

    return render_template(
        "purchase_details.html",
        purchase_order=purchase_order,
        deliveries=deliveries
    )


@app.route("/deliveries")
@login_required
def deliveries():
    from datetime import datetime, timedelta
    from sqlalchemy import func

    shop_id = current_user.shop_id
    seven_days_ago = datetime.now() - timedelta(days=7)

    # Load delivery records for display
    deliveries = StockDelivery.query.filter_by(
        shop_id=shop_id
    ).order_by(
        StockDelivery.delivery_date.desc()
    ).all()

    # Calculate totals inside the database
    total_deliveries = StockDelivery.query.filter_by(
        shop_id=shop_id
    ).count()

    total_delivery_value = db.session.query(
        func.coalesce(func.sum(StockDelivery.total_amount), 0)
    ).filter(
        StockDelivery.shop_id == shop_id
    ).scalar()

    recent_deliveries = StockDelivery.query.filter(
        StockDelivery.shop_id == shop_id,
        StockDelivery.delivery_date >= seven_days_ago
    ).count()

    return render_template(
        "deliveries.html",
        deliveries=deliveries,
        total_deliveries=total_deliveries,
        total_delivery_value=total_delivery_value,
        recent_deliveries=recent_deliveries
    )

@app.route("/deliveries/<int:delivery_id>")
@login_required
def delivery_details(delivery_id):

    delivery = StockDelivery.query.filter_by(
        id=delivery_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    return render_template(
        "delivery_details.html",
        delivery=delivery
    )


# =========================================
# RECEIVE STOCK
# =========================================
@app.route(
    "/purchases/<int:purchase_id>/receive",
    methods=["GET", "POST"]
)
@login_required
def receive_purchase(purchase_id):

    purchase_order = PurchaseOrder.query.filter_by(
        id=purchase_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    # -----------------------------
    # PREVENT RECEIVING COMPLETED PO
    # -----------------------------

    if purchase_order.status == "Received":
        return redirect(
            url_for(
                "purchase_details",
                 purchase_id=purchase_order.id
            )
        )

    if request.method == "POST":

        # -----------------------------
        # GET DELIVERY INFORMATION
        # -----------------------------

        delivery_number = request.form.get(
            "delivery_number",
            ""
        ).strip()

        invoice_number = request.form.get(
            "invoice_number",
            ""
        ).strip()

        delivery_date = request.form.get(
            "delivery_date",
            ""
        )

        invoice_date = request.form.get(
            "invoice_date",
            ""
        )

        notes = request.form.get(
            "notes",
            ""
        ).strip()

        invoice_file = request.files.get("invoice_file")

        # Validate invoice file
        if invoice_file and invoice_file.filename:

            file_extension = (
                invoice_file.filename
                .rsplit(".", 1)[-1]
                .lower()
            )

            if file_extension not in ALLOWED_INVOICE_EXTENSIONS:
               return (
                   "Invalid invoice file. "
                   "Only PDF, JPG, JPEG, and PNG files are allowed.",
                   400
                )

         # Save invoice file
        invoice_filename = None

        if invoice_file and invoice_file.filename:

            safe_filename = secure_filename(
                invoice_file.filename
            )

            file_extension = (
                safe_filename
                .rsplit(".", 1)[-1]
                .lower()
            )

            invoice_filename = (
                f"delivery_{purchase_order.id}_"
                f"{datetime.now(EAT).strftime('%Y%m%d%H%M%S')}"
                f".{file_extension}"
            )

            invoice_file.save(
                os.path.join(
                     app.config["UPLOAD_FOLDER"],
                     invoice_filename
                )
            )

        # validate delivery route
        if delivery_date:
            delivery_date_obj = datetime.strptime(
                delivery_date,
                "%Y-%m-%d"
            )
            if delivery_date_obj.date() > datetime.today(EAT).date():
                return "Delivery date cannot be in the future.", 400
        else:
            delivery_date_obj = datetime.combine(
                datetime.now(EAT).date(),
                datetime.min.time()
            )

        # Validate invoice date
        if invoice_date:
            invoice_date_obj = datetime.strptime(
                invoice_date,
                "%Y-%m-%d"
            )
            if invoice_date_obj.date() > datetime.now(EAT).date():
                return "Invoice date cannot be in the future.", 400
        else:
            invoice_date_obj = None

        # -----------------------------
        # VALIDATION
        # -----------------------------

        if not delivery_number:
            return "Delivery number is required."

        if not delivery_date:
            return "Delivery date is required."

        try:
            parsed_delivery_date = datetime.strptime(
                delivery_date,
                "%Y-%m-%d"
            )
        except ValueError:
            return "Invalid delivery date."

        # -----------------------------
        # CREATE DELIVERY
        # -----------------------------

        delivery = StockDelivery(
            delivery_number=delivery_number,
            delivery_date=delivery_date_obj,
            invoice_number=invoice_number,
            invoice_date=invoice_date_obj,
            invoice_file=invoice_filename,
            total_amount=0,
            notes=notes,
            supplier_id=purchase_order.supplier_id,
            purchase_order_id=purchase_order.id,
            shop_id=current_user.shop_id
        )

        db.session.add(delivery)
        db.session.flush()

        delivery_total = 0

        # -----------------------------
        # PROCESS PRODUCTS
        # -----------------------------

        for item in purchase_order.items:

            received_value = request.form.get(
                f"received_{item.id}",
                "0"
            )

            try:
                quantity_received = int(received_value)
            except (ValueError, TypeError):

                db.session.rollback()

                return (
                    f"Invalid quantity received "
                    f"for {item.product.name}."
                )

            # Nothing received
            if quantity_received <= 0:
                continue

            # -----------------------------
            # CHECK REMAINING QUANTITY
            # -----------------------------

            current_received = (
                item.quantity_received or 0
            )

            remaining = (
                item.quantity_ordered -
                current_received
            )

            if quantity_received > remaining:

                db.session.rollback()

                return (
                    f"Cannot receive more than the remaining "
                    f"quantity for {item.product.name}."
                )

            # -----------------------------
            # GET ACTUAL BUYING PRICE
            # -----------------------------

            actual_price_value = request.form.get(
                f"buying_price_{item.id}",
                str(item.buying_price)
            )

            try:
                actual_buying_price = float(
                    actual_price_value
                )
            except (ValueError, TypeError):

                db.session.rollback()

                return (
                    f"Invalid buying price for "
                    f"{item.product.name}."
                )

            if actual_buying_price < 0:

                db.session.rollback()

                return (
                    f"Buying price cannot be negative "
                    f"for {item.product.name}."
                )

            # -----------------------------
            # CALCULATE DELIVERY TOTAL
            # -----------------------------

            total_price = (
                quantity_received *
                actual_buying_price
            )

            # -----------------------------
            # CREATE DELIVERY ITEM
            # -----------------------------

            delivery_item = StockDeliveryItem(
                quantity_received=quantity_received,
                buying_price=actual_buying_price,
                total_price=total_price,
                delivery_id=delivery.id,
                product_id=item.product_id,
                shop_id=current_user.shop_id
            )

            db.session.add(delivery_item)

            # -----------------------------
            # UPDATE PRODUCT STOCK
            # -----------------------------

            product = item.product

            existing_quantity = (
                product.quantity or 0
            )

            existing_buying_price = (
                product.buying_price or 0
            )

            new_quantity = (
                existing_quantity +
                quantity_received
            )

            if new_quantity > 0:

                total_stock_value = (
                    existing_quantity *
                    existing_buying_price
                ) + (
                    quantity_received *
                    actual_buying_price
                )

                new_average_buying_price = (
                    total_stock_value /
                    new_quantity
                )

            else:

                new_average_buying_price = (
                    actual_buying_price
                )

            product.quantity = new_quantity

            product.buying_price = (
                new_average_buying_price
            )
            # -----------------------------
            # CREATE STOCK MOVEMENT
            # -----------------------------

            stock_movement = StockMovement(
                movement_type="Stock In",
                quantity=quantity_received,
                previous_quantity=existing_quantity,
                new_quantity=new_quantity,
                reference_type="Delivery",
                reference_id=delivery.id,
                notes=(
                    f"Received from "
                    f"{purchase_order.supplier.name} - "
                    f"Delivery {delivery.delivery_number}"
                ),
                product_id=product.id,
                shop_id=current_user.shop_id
            )

            db.session.add(stock_movement)

            # -----------------------------
            # UPDATE PURCHASE ORDER ITEM
            # -----------------------------

            item.quantity_received = (
                current_received +
                quantity_received
            )

            # -----------------------------
            # UPDATE DELIVERY TOTAL
            # -----------------------------

            delivery_total += total_price

        # -----------------------------
        # UPDATE DELIVERY TOTAL
        # -----------------------------

        delivery.total_amount = delivery_total

        # -----------------------------
        # UPDATE PURCHASE ORDER STATUS
        # -----------------------------

        total_ordered = 0
        total_received = 0

        for item in purchase_order.items:

            total_ordered += item.quantity_ordered

            total_received += (
                item.quantity_received or 0
            )

        if total_received == 0:

            purchase_order.status = "Pending"

        elif total_received < total_ordered:

            purchase_order.status = "Partially Received"

        else:

            purchase_order.status = "Received"

        # -----------------------------
        # SAVE EVERYTHING
        # -----------------------------

        db.session.commit()

        # -----------------------------
        # RETURN TO PURCHASE ORDER
        # -----------------------------

        return redirect(
            url_for(
                "purchase_details",
                purchase_id=purchase_order.id
            )
        )

    # -----------------------------
    # RECEIVE STOCK PAGE
    # -----------------------------

    return render_template(
        "receive_purchase.html",
        purchase_order=purchase_order,
        current_date=datetime.now(EAT).strftime("%Y-%m-%d")
    )


# =========================================
# CREATE PURCHASE ORDER
# =========================================

@app.route("/purchases/add", methods=["GET", "POST"])
@login_required
def add_purchase_order():

    suppliers = Supplier.query.filter_by(
        shop_id=current_user.shop_id,
        status="Active"
    ).order_by(
        Supplier.name.asc()
    ).all()

    products = Product.query.filter_by(
        shop_id=current_user.shop_id
    ).order_by(
        Product.name.asc()
    ).all()

    if request.method == "POST":

        supplier_id = request.form.get("supplier_id")
        order_number = request.form.get("order_number").strip()
        order_date = request.form.get("order_date")
        notes = request.form.get("notes").strip()

        if not supplier_id:
            return "Please select a supplier."

        if not order_number:
            return "Order number is required."

        supplier = Supplier.query.filter_by(
            id=int(supplier_id),
            shop_id=current_user.shop_id
        ).first_or_404()

        new_order = PurchaseOrder(
            order_number=order_number,
            order_date=datetime.strptime(
                order_date,
                "%Y-%m-%d"
            ) if order_date else datetime.now(),
            supplier_id=supplier.id,
            shop_id=current_user.shop_id,
            notes=notes,
            expected_total=0
        )

        db.session.add(new_order)
        db.session.flush()

        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        prices = request.form.getlist("buying_price[]")

        expected_total = 0

        for product_id, quantity, buying_price in zip(
            product_ids,
            quantities,
            prices
        ):

            if not product_id or not quantity or not buying_price:
                continue

            product = Product.query.filter_by(
                id=int(product_id),
                shop_id=current_user.shop_id
            ).first()

            if not product:
                continue

            quantity = int(quantity)
            buying_price = float(buying_price)

            if quantity <= 0 or buying_price < 0:
                continue

            total_price = quantity * buying_price

            order_item = PurchaseOrderItem(
                quantity_ordered=quantity,
                quantity_received=0,
                buying_price=buying_price,
                total_price=total_price,
                purchase_order_id=new_order.id,
                product_id=product.id,
                shop_id=current_user.shop_id
            )

            db.session.add(order_item)

            expected_total += total_price

        new_order.expected_total = expected_total

        db.session.commit()

        return redirect(url_for("purchases"))

    return render_template(
        "add_purchase_order.html",
        suppliers=suppliers,
        products=products
    )

@app.route("/products/delete/<int:product_id>", methods=["POST"])
@login_required
def delete_product(product_id):

    product = Product.query.filter_by(
        id=product_id,
        shop_id=current_user.shop_id
    ).first_or_404()

    db.session.delete(product)
    db.session.commit()

    return redirect(url_for("products"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# -------------------------
# Create Database
# -------------------------

with app.app_context():
    db.create_all()

    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    columns = [
        column["name"]
        for column in inspector.get_columns("shop")
    ]

    if "default_low_stock_level" not in columns:
        with db.engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE shop "
                "ADD COLUMN default_low_stock_level "
                "INTEGER NOT NULL DEFAULT 5"
            ))

        print("Added default low-stock setting to the database.")

    
    # Add payment method to existing sales table if missing
    inspector = inspect(db.engine)
    sale_columns = [
        column["name"]
        for column in inspector.get_columns("sale")
    ]

    if "payment_method" not in sale_columns:
        with db.engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE sale "
                "ADD COLUMN payment_method "
                "VARCHAR(20) NOT NULL DEFAULT 'Cash'"
            ))

        print("Added payment method to the sales table.")


    
    # Add payment tracking fields to existing sales table
    inspector = inspect(db.engine)
    sale_columns = [
        column["name"]
        for column in inspector.get_columns("sale")
    ]

    with db.engine.begin() as connection:
        if "payment_status" not in sale_columns:
            connection.execute(text(
                "ALTER TABLE sale "
                "ADD COLUMN payment_status "
                "VARCHAR(20) NOT NULL DEFAULT 'Paid'"
            ))

        if "amount_paid" not in sale_columns:
            connection.execute(text(
                "ALTER TABLE sale "
                "ADD COLUMN amount_paid "
                "FLOAT NOT NULL DEFAULT 0.0"
            ))

        if "payment_reference" not in sale_columns:
            connection.execute(text(
                "ALTER TABLE sale "
                "ADD COLUMN payment_reference VARCHAR(100)"
            ))

        # Preserve old cash sales as paid.
        connection.execute(text(
            "UPDATE sale "
            "SET amount_paid = total_amount "
            "WHERE payment_method = 'Cash' "
            "AND amount_paid = 0"
        ))

        # Don't treat old electronic-payment records as verified
        # merely because a cashier selected a payment method.
        connection.execute(text(
            "UPDATE sale "
            "SET payment_status = 'Pending', amount_paid = 0 "
            "WHERE payment_method IN ('M-Pesa', 'Bank') "
            "AND amount_paid = 0"
        ))


    # Add payment settings to existing shop table
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    shop_columns = {
        column["name"]
        for column in inspector.get_columns("shop")
    }

    payment_columns = {
        "bank_name": "VARCHAR(100)",
        "bank_account_name": "VARCHAR(150)",
        "bank_account_number": "VARCHAR(100)",
        "bank_branch": "VARCHAR(100)",
        "bank_payment_instructions": "TEXT",
        "accept_bank_transfer": "BOOLEAN NOT NULL DEFAULT 0",
        "accept_mpesa": "BOOLEAN NOT NULL DEFAULT 1",
    }

    with db.engine.begin() as connection:
        for column_name, column_type in payment_columns.items():
            if column_name not in shop_columns:
                connection.execute(
                    text(
                        f'ALTER TABLE shop ADD COLUMN "{column_name}" '
                        f"{column_type}"
                    )
                )
                print(f"Added {column_name} to the shop table.")

    
# -------------------------
# Run Application
# -------------------------

if __name__ == "__main__":

    with app.app_context():

        from sqlalchemy import inspect, text

        inspector = inspect(db.engine)

        columns = {
            column["name"]
            for column in inspector.get_columns("stock_movement")
        }

        with db.engine.begin() as connection:

            if "previous_quantity" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE stock_movement "
                        "ADD COLUMN previous_quantity "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )

            if "new_quantity" not in columns:
                connection.execute(
                    text(
                        "ALTER TABLE stock_movement "
                        "ADD COLUMN new_quantity "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                )

    app.run(
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    )