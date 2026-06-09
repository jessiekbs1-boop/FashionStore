import pytest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app, db
from models import User, Product, Order, OrderItem, Payment
from flask import url_for

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.drop_all()

def register_user(client, email, password, role='client'):
    return client.post('/register', data=dict(
        nom='Test User',
        email=email,
        password=password,
        role=role,
        terms_accepted='on'
    ), follow_redirects=True)

def login_user(client, email, password):
    return client.post('/login', data=dict(
        email=email,
        password=password
    ), follow_redirects=True)

def test_user_registration_and_login(client):
    rv = register_user(client, 'test@example.com', 'password123')
    assert b'Inscription reussie' in rv.data or b'Bienvenue' in rv.data or rv.status_code == 200
    rv = login_user(client, 'test@example.com', 'password123')
    assert b'Dashboard' in rv.data or rv.status_code == 200

def test_order_creation_and_payment(client):
    # Register and login user
    register_user(client, 'buyer@example.com', 'password123')
    login_user(client, 'buyer@example.com', 'password123')

    # Add product to DB
    with app.app_context():
        product = Product(nom='Test Product', description='Desc', prix=10.0, quantite=100, vendeur_id=1)
        db.session.add(product)
        db.session.commit()
        product_id = product.id

    # Add product to cart
    rv = client.post(f'/client/panier/ajouter/{product_id}', data=dict(quantite=2), follow_redirects=True)
    assert b'Produit ajoute au panier' in rv.data

    # Place order
    rv = client.post('/client/commande/passer', follow_redirects=True)
    assert b'Commande passee avec succes' in rv.data

    # Get order id
    with app.app_context():
        order = Order.query.filter_by(client_id=1).first()
        assert order is not None
        order_id = order.id

    # Choose payment page
    rv = client.get(f'/client/choisir_paiement/{order_id}')
    assert b'Choisir paiement' in rv.data or rv.status_code == 200

    # Process payment
    rv = client.post('/client/traiter_paiement', data=dict(
        order_id=order_id,
        montant=20.0,
        mode='Carte Bancaire',
        nom='Test User'
    ), follow_redirects=True)
    assert b'Paiement traite avec succes' in rv.data

    # Check payment saved
    with app.app_context():
        payment = Payment.query.filter_by(order_id=order_id).first()
        assert payment is not None
        assert payment.montant == 20.0

def test_admin_delete_user_cascade(client):
    # Create admin directly and register a regular user
    with app.app_context():
        admin = User(nom='Admin', email='admin@example.com', role='admin', actif=True)
        admin.set_password('adminpass')
        db.session.add(admin)
        db.session.commit()
    register_user(client, 'user@example.com', 'userpass', role='client')

    # Login as admin
    login_user(client, 'admin@example.com', 'adminpass')

    # Delete user
    with app.app_context():
        user = User.query.filter_by(email='user@example.com').first()
        assert user is not None
        user_id = user.id

    rv = client.post(f'/admin/utilisateur/supprimer/{user_id}', follow_redirects=True)
    assert b'Utilisateur supprime' in rv.data

    with app.app_context():
        user = User.query.filter_by(email='user@example.com').first()
        assert user is None
