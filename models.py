from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # client, vendeur, admin
    actif = db.Column(db.Boolean, default=True)
    localisation = db.Column(db.String(120), nullable=True)
    profile_photo = db.Column(db.String(255), nullable=True)
    terms_accepted = db.Column(db.DateTime, nullable=True)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True)

    products = db.relationship('Product', backref='vendeur', lazy=True, cascade="all, delete-orphan")
    orders = db.relationship('Order', backref='client', lazy=True, cascade="all, delete-orphan")
    sent_messages = db.relationship('Message', foreign_keys='Message.expediteur_id', backref='expediteur', lazy=True, cascade="all, delete-orphan")
    received_messages = db.relationship('Message', foreign_keys='Message.destinataire_id', backref='destinataire', lazy=True, cascade="all, delete-orphan")
    favoris = db.relationship('Favorite', backref='user', lazy=True, cascade="all, delete-orphan")
    avis_donnes = db.relationship('Review', foreign_keys='Review.client_id', backref='client', lazy=True, cascade="all, delete-orphan")
    avis_recus = db.relationship('Review', foreign_keys='Review.vendeur_id', backref='vendeur', lazy=True, cascade="all, delete-orphan")

    shop = db.relationship('Shop', backref='members', foreign_keys=[shop_id])

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    prix = db.Column(db.Float, nullable=False)
    ancien_prix = db.Column(db.Float, nullable=True)
    quantite = db.Column(db.Integer, nullable=False)
    image = db.Column(db.String(255), nullable=True)
    categorie = db.Column(db.String(50), nullable=True)
    sous_categorie = db.Column(db.String(80), nullable=True)
    taille = db.Column(db.String(20), nullable=True)
    tailles_disponibles = db.Column(db.String(255), nullable=True)
    couleurs = db.Column(db.String(255), nullable=True)
    delai_livraison_min = db.Column(db.Integer, nullable=True)
    delai_livraison_max = db.Column(db.Integer, nullable=True)
    marque = db.Column(db.String(80), nullable=True)
    localisation = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    vendeur_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True)

    order_items = db.relationship('OrderItem', backref='product', lazy=True, cascade="all, delete-orphan")
    images = db.relationship('ProductImage', backref='product', lazy=True, cascade="all, delete-orphan")
    favoris = db.relationship('Favorite', backref='product', lazy=True, cascade="all, delete-orphan")

    @property
    def image_principale(self):
        if self.image:
            return self.image
        if self.images:
            ordered_images = sorted(self.images, key=lambda image: (image.position or 0, image.id or 0))
            return ordered_images[0].image_path if ordered_images else None
        return None

class ProductImage(db.Model):
    __tablename__ = 'product_images'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    position = db.Column(db.Integer, default=0)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True)

class Favorite(db.Model):
    __tablename__ = 'favorites'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'product_id', name='uq_user_product_favorite'),)

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    statut = db.Column(db.String(50), default='en attente')  # en attente, paye, expedie, livre
    total = db.Column(db.Float, nullable=False)
    mode_livraison = db.Column(db.String(50), nullable=True)  # 'livraison' or 'retrait'
    adresse = db.Column(db.String(255), nullable=True)
    frais_livraison = db.Column(db.Float, nullable=True)
    date_livraison = db.Column(db.DateTime, nullable=True)

    def calculate_delivery_fee(self):
        # Sum distinct delivery fees for shops present in the order
        shop_ids = set()
        for item in self.items:
            if item.product and getattr(item.product, 'shop_id', None):
                shop_ids.add(item.product.shop_id)
        total_fee = 0.0
        for sid in shop_ids:
            shop = db.session.get(Shop, sid)
            if shop and shop.delivery_fee:
                try:
                    total_fee += float(shop.delivery_fee)
                except Exception:
                    continue
        return total_fee
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True)

    items = db.relationship('OrderItem', backref='order', lazy=True, cascade="all, delete-orphan")
    payment = db.relationship('Payment', uselist=False, backref='order', cascade="all, delete-orphan")

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantite = db.Column(db.Integer, nullable=False)
    prix = db.Column(db.Float, nullable=False)

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    montant = db.Column(db.Float, nullable=False)
    methode = db.Column(db.String(50), nullable=False)  # Mobile Money, Carte Bancaire, Paiement à la livraison
    statut = db.Column(db.String(50), default='en attente')
    transaction_id = db.Column(db.String(120), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True)
    events = db.relationship('PaymentEvent', backref='payment', lazy=True, cascade="all, delete-orphan")


class PaymentEvent(db.Model):
    __tablename__ = 'payment_events'
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=False)
    event_type = db.Column(db.String(80), nullable=False)
    payload = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(50), nullable=False, default='system')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    vendeur_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    note = db.Column(db.Integer, nullable=False)
    commentaire = db.Column(db.Text, nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True)

    __table_args__ = (db.CheckConstraint('note >= 1 AND note <= 5', name='ck_review_note_range'),)

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    expediteur_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    destinataire_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    contenu = db.Column(db.Text, nullable=False)
    lu = db.Column(db.Boolean, default=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    shop_id = db.Column(db.Integer, db.ForeignKey('shops.id'), nullable=True)


class Shop(db.Model):
    __tablename__ = 'shops'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(150), unique=True, nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship('User', backref='owned_shop', foreign_keys=[owner_id])
    products = db.relationship('Product', backref='shop', lazy=True, cascade="all, delete-orphan")
    # Pickup address and delivery fee (simple model for delivery calculation)
    address = db.Column(db.String(255), nullable=True)
    delivery_fee = db.Column(db.Float, default=5.0)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
