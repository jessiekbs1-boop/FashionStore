from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from models import db, User, Product, Order, Payment, Shop
from utils.geocode import geocode_address

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
@login_required
def admin_home():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    if current_user.shop_id:
        users = User.query.filter_by(shop_id=current_user.shop_id).all()
        products = Product.query.filter_by(shop_id=current_user.shop_id).all()
        orders = Order.query.filter_by(shop_id=current_user.shop_id).all()
        produits = Product.query.filter_by(shop_id=current_user.shop_id).order_by(Product.created_at.desc()).all()
    else:
        users = User.query.all()
        products = Product.query.all()
        orders = Order.query.all()
        produits = Product.query.order_by(Product.created_at.desc()).all()
    # Get all products for dashboard display
    return render_template('admin/dashboard.html', users=users, products=products, orders=orders, produits=produits)

@admin_bp.route('/admin/gestion_paiements')
@login_required
def gestion_paiements():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    payments_query = Payment.query
    if current_user.shop_id:
        payments_query = payments_query.filter_by(shop_id=current_user.shop_id)
    payments = payments_query.order_by(Payment.date.desc()).all()
    return render_template('admin/gestion_paiements.html', payments=payments)

@admin_bp.route('/admin/utilisateurs')
@login_required
def gestion_utilisateurs():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    users_query = User.query
    if current_user.shop_id:
        users_query = users_query.filter_by(shop_id=current_user.shop_id)
    users = users_query.all()
    return render_template('admin/gestion_utilisateurs.html', users=users)

@admin_bp.route('/admin/utilisateur/desactiver/<int:user_id>', methods=['POST'])
@login_required
def desactiver_utilisateur(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    user = User.query.get_or_404(user_id)
    if current_user.shop_id and user.shop_id != current_user.shop_id:
        flash('Acces refuse.', 'danger')
        return redirect(url_for('admin.gestion_utilisateurs'))
    user.actif = False
    db.session.commit()
    flash('Utilisateur desactive.')
    return redirect(url_for('admin.gestion_utilisateurs'))

@admin_bp.route('/admin/utilisateur/supprimer/<int:user_id>', methods=['POST'])
@login_required
def supprimer_utilisateur(user_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    user = User.query.get_or_404(user_id)
    if current_user.shop_id and user.shop_id != current_user.shop_id:
        flash('Acces refuse.', 'danger')
        return redirect(url_for('admin.gestion_utilisateurs'))
    # Delete related products and orders to avoid foreign key constraint errors
    for product in user.products:
        # Delete order_items related to product
        for item in product.order_items:
            db.session.delete(item)
        db.session.delete(product)
    for order in user.orders:
        # Delete payment related to order to avoid integrity error
        if order.payment:
            db.session.delete(order.payment)
        # Delete order_items related to order to avoid integrity error
        for item in order.items:
            db.session.delete(item)
        db.session.delete(order)
    db.session.delete(user)
    db.session.commit()
    flash('Utilisateur supprime.')
    return redirect(url_for('admin.gestion_utilisateurs'))

@admin_bp.route('/admin/produits')
@login_required
def gestion_produits_admin():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    products_query = Product.query
    if current_user.shop_id:
        products_query = products_query.filter_by(shop_id=current_user.shop_id)
    products = products_query.all()
    return render_template('admin/gestion_produits.html', products=products)

@admin_bp.route('/admin/produit/supprimer/<int:product_id>', methods=['POST'])
@login_required
def supprimer_produit_admin(product_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    produit = Product.query.get_or_404(product_id)
    if current_user.shop_id and produit.shop_id != current_user.shop_id:
        flash('Acces refuse.', 'danger')
        return redirect(url_for('admin.gestion_produits_admin'))
    # Delete related order_items first to avoid foreign key constraint error
    order_items = produit.order_items
    for item in order_items:
        db.session.delete(item)
    db.session.delete(produit)
    db.session.commit()
    flash('Produit supprime.')
    return redirect(url_for('admin.gestion_produits_admin'))

@admin_bp.route('/admin/commandes')
@login_required
def gestion_commandes():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    orders_query = Order.query
    if current_user.shop_id:
        orders_query = orders_query.filter_by(shop_id=current_user.shop_id)
    orders = orders_query.all()
    return render_template('admin/gestion_commandes.html', orders=orders)


@admin_bp.route('/admin/boutiques')
@login_required
def gestion_boutiques():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    shops_query = Shop.query
    if current_user.shop_id:
        shops_query = shops_query.filter_by(id=current_user.shop_id)
    shops = shops_query.order_by(Shop.created_at.desc()).all()
    return render_template('admin/gestion_boutiques.html', shops=shops)


@admin_bp.route('/admin/boutique/ajouter', methods=['POST'])
@login_required
def ajouter_boutique():
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    nom = request.form.get('nom')
    address = request.form.get('address')
    delivery_fee = request.form.get('delivery_fee')
    try:
        fee = float(delivery_fee) if delivery_fee not in (None, '') else 0.0
    except ValueError:
        fee = 0.0
    shop = Shop(nom=nom, address=address, delivery_fee=fee)
    # try to geocode address
    try:
        coords = geocode_address(address)
        if coords:
            shop.latitude, shop.longitude = coords
    except Exception:
        pass
    db.session.add(shop)
    db.session.commit()
    flash('Boutique ajoutee.')
    return redirect(url_for('admin.gestion_boutiques'))


@admin_bp.route('/admin/boutique/modifier/<int:shop_id>', methods=['GET', 'POST'])
@login_required
def modifier_boutique(shop_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    shop = Shop.query.get_or_404(shop_id)
    if current_user.shop_id and shop.id != current_user.shop_id:
        flash('Acces refuse.', 'danger')
        return redirect(url_for('admin.gestion_boutiques'))
    if request.method == 'POST':
        shop.nom = request.form.get('nom')
        shop.address = request.form.get('address')
        try:
            shop.delivery_fee = float(request.form.get('delivery_fee') or 0)
        except ValueError:
            shop.delivery_fee = 0.0
        # try to geocode updated address
        try:
            coords = geocode_address(shop.address)
            if coords:
                shop.latitude, shop.longitude = coords
        except Exception:
            pass
        db.session.commit()
        flash('Boutique modifiee.')
        return redirect(url_for('admin.gestion_boutiques'))
    return render_template('admin/modifier_boutique.html', shop=shop)


@admin_bp.route('/admin/boutique/supprimer/<int:shop_id>', methods=['POST'])
@login_required
def supprimer_boutique(shop_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    shop = Shop.query.get_or_404(shop_id)
    if current_user.shop_id and shop.id != current_user.shop_id:
        flash('Acces refuse.', 'danger')
        return redirect(url_for('admin.gestion_boutiques'))
    # optionally detach products
    for p in shop.products:
        p.shop_id = None
    db.session.delete(shop)
    db.session.commit()
    flash('Boutique supprimee.')
    return redirect(url_for('admin.gestion_boutiques'))

@admin_bp.route('/admin/commande/supprimer/<int:order_id>', methods=['POST'])
@login_required
def supprimer_commande_admin(order_id):
    if current_user.role != 'admin':
        return redirect(url_for('auth.login'))
    order = Order.query.get_or_404(order_id)
    if current_user.shop_id and order.shop_id != current_user.shop_id:
        flash('Acces refuse.', 'danger')
        return redirect(url_for('admin.gestion_commandes'))
    # Delete related order_items
    for item in order.items:
        db.session.delete(item)
    db.session.delete(order)
    db.session.commit()
    flash('Commande supprimee.')
    return redirect(url_for('admin.gestion_commandes'))
