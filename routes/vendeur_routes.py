import os
import uuid

from flask import Blueprint, current_app, redirect, render_template, request, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import and_, or_
from werkzeug.utils import secure_filename

from models import Message, Order, OrderItem, Payment, Product, ProductImage, Review, User, db

vendeur_bp = Blueprint('vendeur', __name__)

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


def _allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def _save_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not _allowed_image(file_storage.filename):
        return None
    original_name = secure_filename(file_storage.filename)
    unique_name = f"{uuid.uuid4().hex}_{original_name}"
    file_storage.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name))
    return unique_name

@vendeur_bp.route('/vendeur')
@login_required
def vendeur_home():
    if current_user.role != 'vendeur':
        return redirect(url_for('auth.login'))
    # Redirect to dashboard page with buttons as requested
    return redirect(url_for('vendeur.vendeur_dashboard'))

@vendeur_bp.route('/vendeur/dashboard')
@login_required
def vendeur_dashboard():
    if current_user.role != 'vendeur':
        return redirect(url_for('auth.login'))
    # Gather dashboard statistics with safe defaults
    total_products = Product.query.filter_by(vendeur_id=current_user.id).count()
    total_quantity = db.session.query(db.func.coalesce(db.func.sum(Product.quantite), 0)).filter_by(vendeur_id=current_user.id).scalar()

    # Total orders containing seller's products
    total_orders = db.session.query(db.func.coalesce(db.func.count(db.distinct(Order.id)), 0))\
        .join(OrderItem, Order.id == OrderItem.order_id)\
        .join(Product, Product.id == OrderItem.product_id)\
        .filter(Product.vendeur_id == current_user.id).scalar()

    total_sales = db.session.query(db.func.coalesce(db.func.sum(OrderItem.quantite), 0)).join(
        Product, Product.id == OrderItem.product_id
    ).join(Order, Order.id == OrderItem.order_id).filter(
        Product.vendeur_id == current_user.id,
        Order.statut.in_(['paye', 'expedie', 'livre'])
    ).scalar()

    revenus = db.session.query(db.func.coalesce(db.func.sum(OrderItem.prix * OrderItem.quantite), 0.0)).join(
        Product, Product.id == OrderItem.product_id
    ).join(Order, Order.id == OrderItem.order_id).filter(
        Product.vendeur_id == current_user.id,
        Order.statut.in_(['paye', 'expedie', 'livre'])
    ).scalar()

    average_rating = db.session.query(db.func.coalesce(db.func.avg(Review.note), 0.0)).filter_by(vendeur_id=current_user.id).scalar()
    unread_messages = Message.query.filter_by(destinataire_id=current_user.id, lu=False).count()
    
    # Get seller's products for dashboard display
    produits = Product.query.filter_by(vendeur_id=current_user.id).order_by(Product.created_at.desc()).all()

    return render_template('vendeur/dashboard.html',
                           total_products=total_products,
                           total_quantity=total_quantity,
                           total_orders=total_orders,
                           total_sales=total_sales,
                           revenus=revenus,
                           average_rating=average_rating,
                           unread_messages=unread_messages,
                           produits=produits)

@vendeur_bp.route('/vendeur/commandes')
@login_required
def commandes():
    if current_user.role != 'vendeur':
        return redirect(url_for('auth.login'))
    # Query orders containing seller's products
    orders = db.session.query(Order)\
        .join(OrderItem, Order.id == OrderItem.order_id)\
        .join(Product, Product.id == OrderItem.product_id)\
        .filter(Product.vendeur_id == current_user.id)\
        .order_by(Order.date.desc())\
        .distinct()\
        .all()
    return render_template('vendeur/gestion_commandes.html', orders=orders)


@vendeur_bp.route('/vendeur/commande/<int:order_id>/statut', methods=['POST'])
@login_required
def update_statut_commande(order_id):
    if current_user.role != 'vendeur':
        return redirect(url_for('auth.login'))

    nouveau_statut = request.form.get('statut', '').strip().lower()
    statuts_valides = {'en attente', 'paye', 'expedie', 'livre'}
    if nouveau_statut not in statuts_valides:
        flash('Statut invalide.', 'danger')
        return redirect(url_for('vendeur.commandes'))

    order = db.session.query(Order).join(OrderItem, Order.id == OrderItem.order_id).join(
        Product, Product.id == OrderItem.product_id
    ).filter(
        Order.id == order_id,
        Product.vendeur_id == current_user.id
    ).first_or_404()

    order.statut = nouveau_statut
    db.session.commit()
    flash('Statut de la commande mis a jour.', 'success')
    return redirect(url_for('vendeur.commandes'))

@vendeur_bp.route('/vendeur/produit/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_produit():
    if current_user.role != 'vendeur':
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        nom = request.form['nom']
        description = request.form.get('description', '').strip()
        categorie = request.form.get('categorie', '').strip().lower() or None
        taille = request.form.get('taille', '').strip().upper() or None
        marque = request.form.get('marque', '').strip() or None
        localisation = request.form.get('localisation', '').strip() or current_user.localisation
        prix = request.form.get('prix', type=float)
        ancien_prix = request.form.get('ancien_prix', type=float)
        quantite = request.form.get('quantite', type=int)

        if prix is None or prix <= 0 or quantite is None or quantite < 0:
            flash('Prix ou quantite invalide.', 'danger')
            return redirect(url_for('vendeur.ajouter_produit'))

        produit = Product(
            nom=nom,
            description=description,
            prix=prix,
            ancien_prix=ancien_prix,
            quantite=quantite,
            categorie=categorie,
            taille=taille,
            marque=marque,
            localisation=localisation,
            vendeur_id=current_user.id,
        )

        image_file = request.files.get('image')
        image_paths = []
        if image_file and image_file.filename:
            saved = _save_image(image_file)
            if saved is None:
                flash('Format image non supporte.', 'danger')
                return redirect(url_for('vendeur.ajouter_produit'))
            produit.image = saved
            image_paths.append(saved)

        db.session.add(produit)
        db.session.flush()

        for index, extra_image in enumerate(request.files.getlist('images')):
            saved = _save_image(extra_image)
            if saved:
                image_paths.append(saved)
                db.session.add(ProductImage(product_id=produit.id, image_path=saved, position=index))

        db.session.commit()
        flash('Produit ajoute avec succes.')
        return redirect(url_for('vendeur.vendeur_home'))
    return render_template('vendeur/ajouter_produit.html')

@vendeur_bp.route('/vendeur/produit/modifier/<int:produit_id>', methods=['GET', 'POST'])
@login_required
def modifier_produit(produit_id):
    if current_user.role != 'vendeur':
        return redirect(url_for('auth.login'))
    produit = Product.query.get_or_404(produit_id)
    if produit.vendeur_id != current_user.id:
        flash('Acces refuse.')
        return redirect(url_for('vendeur.vendeur_home'))
    if request.method == 'POST':
        produit.nom = request.form['nom']
        produit.description = request.form.get('description', '').strip()
        produit.prix = request.form.get('prix', type=float)
        produit.ancien_prix = request.form.get('ancien_prix', type=float)
        produit.quantite = request.form.get('quantite', type=int)
        produit.categorie = request.form.get('categorie', '').strip().lower() or None
        produit.taille = request.form.get('taille', '').strip().upper() or None
        produit.marque = request.form.get('marque', '').strip() or None
        produit.localisation = request.form.get('localisation', '').strip() or produit.localisation

        image_file = request.files.get('image')
        if image_file and image_file.filename:
            filename = _save_image(image_file)
            if filename is None:
                flash('Format image non supporte.', 'danger')
                return redirect(url_for('vendeur.modifier_produit', produit_id=produit.id))
            produit.image = filename

        for index, extra_image in enumerate(request.files.getlist('images')):
            saved = _save_image(extra_image)
            if saved:
                db.session.add(ProductImage(product_id=produit.id, image_path=saved, position=index))

        db.session.commit()
        flash('Produit modifie avec succes.')
        return redirect(url_for('vendeur.vendeur_home'))
    return render_template('vendeur/modifier_produit.html', produit=produit)

@vendeur_bp.route('/vendeur/produit/supprimer/<int:produit_id>', methods=['POST'])
@login_required
def supprimer_produit(produit_id):
    if current_user.role != 'vendeur':
        return redirect(url_for('auth.login'))
    produit = Product.query.get_or_404(produit_id)
    if produit.vendeur_id != current_user.id:
        flash('Acces refuse.')
        return redirect(url_for('vendeur.vendeur_home'))
    db.session.delete(produit)
    db.session.commit()
    flash('Produit supprime.')
    return redirect(url_for('vendeur.vendeur_home'))

@vendeur_bp.route('/vendeur/stock')
@login_required
def stock_vendeur():
    if current_user.role != 'vendeur':
        return redirect(url_for('auth.login'))
    produits = Product.query.filter_by(vendeur_id=current_user.id).all()
    return render_template('vendeur/stock.html', produits=produits)


@vendeur_bp.route('/vendeur/messages', methods=['GET', 'POST'])
@login_required
def messages_vendeur():
    if current_user.role != 'vendeur':
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        destinataire_id = request.form.get('destinataire_id', type=int)
        contenu = request.form.get('contenu', '').strip()
        destinataire = User.query.filter_by(id=destinataire_id, role='client', actif=True).first()
        if destinataire and contenu:
            db.session.add(Message(expediteur_id=current_user.id, destinataire_id=destinataire.id, contenu=contenu))
            db.session.commit()
            flash('Message envoye avec succes.', 'success')
        else:
            flash('Message invalide.', 'danger')
        return redirect(url_for('vendeur.messages_vendeur', partenaire_id=destinataire_id))

    partenaires = User.query.filter_by(role='client', actif=True).order_by(User.nom.asc()).all()
    partenaire_id = request.args.get('partenaire_id', type=int)
    conversation = []
    partenaire = None
    unread_by_partner = {}

    for partenaire_candidat in partenaires:
        unread_by_partner[partenaire_candidat.id] = Message.query.filter_by(
            expediteur_id=partenaire_candidat.id,
            destinataire_id=current_user.id,
            lu=False,
        ).count()

    if partenaire_id:
        partenaire = User.query.filter_by(id=partenaire_id, role='client').first()
        if partenaire:
            conversation = Message.query.filter(
                or_(
                    and_(Message.expediteur_id == current_user.id, Message.destinataire_id == partenaire_id),
                    and_(Message.expediteur_id == partenaire_id, Message.destinataire_id == current_user.id),
                )
            ).order_by(Message.date.asc()).all()
            Message.query.filter_by(expediteur_id=partenaire_id, destinataire_id=current_user.id, lu=False).update({'lu': True})
            db.session.commit()

    return render_template(
        'vendeur/messages.html',
        partenaires=partenaires,
        conversation=conversation,
        partenaire_selectionne=partenaire,
        unread_by_partner=unread_by_partner,
    )
