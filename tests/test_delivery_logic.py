import sys
import os
import pytest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app, db
from models import Shop, User, Product, Order, OrderItem


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.drop_all()


def test_delivery_fee_sum_by_shops(client):
    with app.app_context():
        # create two shops with different fees
        s1 = Shop(nom='Shop A', delivery_fee=3.5)
        s2 = Shop(nom='Shop B', delivery_fee=4.0)
        db.session.add_all([s1, s2])
        db.session.commit()

        # create a vendor user
        vendor = User(nom='Vendeur', email='v@ex.com', role='vendeur', actif=True)
        vendor.set_password('pass')
        db.session.add(vendor)
        db.session.commit()

        # create products attached to each shop
        p1 = Product(nom='P1', prix=10.0, quantite=10, vendeur_id=vendor.id, shop_id=s1.id)
        p2 = Product(nom='P2', prix=15.0, quantite=5, vendeur_id=vendor.id, shop_id=s2.id)
        db.session.add_all([p1, p2])
        db.session.commit()

        # create order with items from both shops
        order = Order(client_id=1, total=25.0)
        db.session.add(order)
        db.session.flush()
        oi1 = OrderItem(order_id=order.id, product_id=p1.id, quantite=1, prix=p1.prix)
        oi2 = OrderItem(order_id=order.id, product_id=p2.id, quantite=1, prix=p2.prix)
        db.session.add_all([oi1, oi2])
        db.session.commit()

        fee = order.calculate_delivery_fee()
        assert pytest.approx(fee, rel=1e-3) == 3.5 + 4.0
