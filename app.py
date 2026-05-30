from flask import Flask, session
from models import db
from flask_login import LoginManager
from routes.auth_routes import auth_bp
from routes.client_routes import client_bp
from routes.vendeur_routes import vendeur_bp
from routes.admin_routes import admin_bp
import os
from sqlalchemy import inspect, text

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-change-this-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///fashionstore.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'images')
app.config['CINETPAY_API_KEY'] = os.getenv('CINETPAY_API_KEY', '')
app.config['CINETPAY_SITE_ID'] = os.getenv('CINETPAY_SITE_ID', '')
app.config['CINETPAY_WEBHOOK_SECRET'] = os.getenv('CINETPAY_WEBHOOK_SECRET', os.getenv('CINETPAY_API_KEY', ''))

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return db.session.get(User, int(user_id))

@app.context_processor
def inject_notifications():
    from flask_login import current_user

    def cart_quantity(entry):
        if isinstance(entry, dict):
            return int(entry.get('quantite', 0) or 0)
        try:
            return int(entry)
        except (TypeError, ValueError):
            return 0

    if not current_user.is_authenticated:
        return {
            'unread_message_count': 0,
            'cart_item_count': 0,
            'new_order_count': 0,
        }

    from models import Message, Order, OrderItem, Product
    unread_count = Message.query.filter_by(destinataire_id=current_user.id, lu=False).count()

    user_shop_id = getattr(current_user, 'shop_id', None)

    cart_item_count = 0
    if current_user.role == 'client':
        panier = session.get('panier', {})
        cart_item_count = sum(cart_quantity(quantite) for quantite in panier.values())

    new_order_count = 0
    if current_user.role == 'client':
        client_orders_query = Order.query.filter(
            Order.client_id == current_user.id,
            Order.statut.in_(['en attente', 'paye'])
        )
        if user_shop_id is not None and hasattr(Order, 'shop_id'):
            client_orders_query = client_orders_query.filter(Order.shop_id == user_shop_id)
        new_order_count = client_orders_query.count()
    elif current_user.role == 'vendeur':
        vendor_orders_query = db.session.query(db.func.count(db.distinct(Order.id))).join(
            OrderItem, Order.id == OrderItem.order_id
        ).join(Product, Product.id == OrderItem.product_id).filter(
            Product.vendeur_id == current_user.id,
            Order.statut.in_(['en attente', 'paye'])
        )
        if user_shop_id is not None and hasattr(Product, 'shop_id'):
            vendor_orders_query = vendor_orders_query.filter(Product.shop_id == user_shop_id)
        new_order_count = vendor_orders_query.scalar() or 0
    elif current_user.role == 'admin':
        admin_orders_query = Order.query.filter(Order.statut.in_(['en attente', 'paye']))
        if user_shop_id is not None and hasattr(Order, 'shop_id'):
            admin_orders_query = admin_orders_query.filter(Order.shop_id == user_shop_id)
        new_order_count = admin_orders_query.count()

    return {
        'unread_message_count': unread_count,
        'cart_item_count': cart_item_count,
        'new_order_count': new_order_count,
    }

app.register_blueprint(auth_bp)
app.register_blueprint(client_bp)
app.register_blueprint(vendeur_bp)
app.register_blueprint(admin_bp)

_database_ready = False

def ensure_database_ready():
    with app.app_context():
        db.create_all()

        inspector = inspect(db.engine)
        if 'users' in inspector.get_table_names():
            user_columns = {col['name'] for col in inspector.get_columns('users')}
            if 'profile_photo' not in user_columns:
                db.session.execute(text('ALTER TABLE users ADD COLUMN profile_photo VARCHAR(255)'))
                db.session.commit()
            if 'terms_accepted' not in user_columns:
                db.session.execute(text('ALTER TABLE users ADD COLUMN terms_accepted DATETIME'))
                db.session.commit()
            if 'shop_id' not in user_columns:
                db.session.execute(text('ALTER TABLE users ADD COLUMN shop_id INTEGER'))
                db.session.commit()

        from models import User
        if not User.query.filter_by(role='admin').first():
            admin = User(nom='Admin', email='admin@example.com', role='admin', actif=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()

        # Ensure shops table exists (db.create_all() will create it if model present)
        if 'shops' not in inspector.get_table_names():
            db.create_all()
            inspector = inspect(db.engine)

        # Add shop_id columns to other tables if missing. Use simple INTEGER columns to avoid complex FK migration on SQLite.
        table_checks = {
            'products': 'shop_id',
            'product_images': 'shop_id',
            'orders': 'shop_id',
            'payments': 'shop_id',
            'reviews': 'shop_id',
            'messages': 'shop_id'
        }
        for table, col in table_checks.items():
            if table in inspector.get_table_names():
                cols = {c['name'] for c in inspector.get_columns(table)}
                if col not in cols:
                    db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} INTEGER'))
                    db.session.commit()

        if 'products' in inspector.get_table_names():
            product_cols = {c['name'] for c in inspector.get_columns('products')}
            if 'sous_categorie' not in product_cols:
                db.session.execute(text("ALTER TABLE products ADD COLUMN sous_categorie VARCHAR(80)"))
                db.session.commit()
            if 'tailles_disponibles' not in product_cols:
                db.session.execute(text("ALTER TABLE products ADD COLUMN tailles_disponibles VARCHAR(255)"))
                db.session.commit()
            if 'couleurs' not in product_cols:
                db.session.execute(text("ALTER TABLE products ADD COLUMN couleurs VARCHAR(255)"))
                db.session.commit()
            if 'delai_livraison_min' not in product_cols:
                db.session.execute(text("ALTER TABLE products ADD COLUMN delai_livraison_min INTEGER"))
                db.session.commit()
            if 'delai_livraison_max' not in product_cols:
                db.session.execute(text("ALTER TABLE products ADD COLUMN delai_livraison_max INTEGER"))
                db.session.commit()
        # Ensure shops fields exist
        if 'shops' in inspector.get_table_names():
            shop_cols = {c['name'] for c in inspector.get_columns('shops')}
            if 'address' not in shop_cols:
                db.session.execute(text("ALTER TABLE shops ADD COLUMN address VARCHAR(255)"))
                db.session.commit()
            if 'delivery_fee' not in shop_cols:
                db.session.execute(text("ALTER TABLE shops ADD COLUMN delivery_fee FLOAT DEFAULT 5.0"))
                db.session.commit()
            if 'latitude' not in shop_cols:
                db.session.execute(text("ALTER TABLE shops ADD COLUMN latitude FLOAT"))
                db.session.commit()
            if 'longitude' not in shop_cols:
                db.session.execute(text("ALTER TABLE shops ADD COLUMN longitude FLOAT"))
                db.session.commit()
        # Ensure delivery-related columns exist on orders
        if 'orders' in inspector.get_table_names():
            order_cols = {c['name'] for c in inspector.get_columns('orders')}
            if 'mode_livraison' not in order_cols:
                db.session.execute(text("ALTER TABLE orders ADD COLUMN mode_livraison VARCHAR(50)"))
                db.session.commit()
            if 'adresse' not in order_cols:
                db.session.execute(text("ALTER TABLE orders ADD COLUMN adresse VARCHAR(255)"))
                db.session.commit()
            if 'frais_livraison' not in order_cols:
                db.session.execute(text("ALTER TABLE orders ADD COLUMN frais_livraison FLOAT"))
                db.session.commit()
            if 'date_livraison' not in order_cols:
                db.session.execute(text("ALTER TABLE orders ADD COLUMN date_livraison DATETIME"))
                db.session.commit()

        # Ensure payment_events table exists and has expected columns
        if 'payment_events' not in inspector.get_table_names():
            db.create_all()
            inspector = inspect(db.engine)
        if 'payment_events' in inspector.get_table_names():
            event_cols = {c['name'] for c in inspector.get_columns('payment_events')}
            if 'source' not in event_cols:
                db.session.execute(text("ALTER TABLE payment_events ADD COLUMN source VARCHAR(50) DEFAULT 'system'"))
                db.session.commit()

ensure_database_ready()

@app.before_request
def ensure_database_ready_before_request():
    global _database_ready
    if not _database_ready:
        ensure_database_ready()
        _database_ready = True

if __name__ == '__main__':
    app.run(debug=True)
