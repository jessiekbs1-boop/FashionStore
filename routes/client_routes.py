from datetime import UTC, datetime
import uuid

from flask import Blueprint, render_template, redirect, url_for, request, flash, session, current_app
from flask_login import login_required, current_user
from sqlalchemy import and_, or_

from models import Favorite, Message, Order, OrderItem, Payment, Product, Review, User, db
from models import Shop
from math import radians, cos, sin, asin, sqrt
from utils.geocode import geocode_address
from utils.cinetpay import CinetPayAPI

client_bp = Blueprint('client', __name__)

@client_bp.route('/client')
@login_required
def client_home():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    return redirect(url_for('client.client_dashboard'))

@client_bp.route('/client/dashboard')
@login_required
def client_dashboard():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    produits = Product.query.order_by(Product.created_at.desc()).all()
    favoris_ids = {f.product_id for f in Favorite.query.filter_by(user_id=current_user.id).all()}
    return render_template('client/dashboard.html', produits=produits, favoris_ids=favoris_ids)

@client_bp.route('/client/commandes')
@login_required
def client_orders():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    orders = Order.query.filter_by(client_id=current_user.id).order_by(Order.date.desc()).all()
    return render_template('client/commandes.html', orders=orders)

@client_bp.route('/client/panier')
@login_required
def voir_panier():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    panier = session.get('panier', {})
    products = []
    total = 0
    for product_id, quantite in panier.items():
        produit = db.session.get(Product, int(product_id))
        if produit:
            products.append({'produit': produit, 'quantite': quantite})
            total += produit.prix * quantite
    return render_template('client/panier.html', products=products, total=total)

@client_bp.route('/client/panier/ajouter/<int:product_id>', methods=['POST'])
@login_required
def ajouter_au_panier(product_id):
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    panier = session.get('panier', {})
    quantite = max(1, int(request.form.get('quantite', 1)))
    produit = db.session.get(Product, product_id)
    if produit is None:
        flash('Produit introuvable.')
        return redirect(url_for('client.voir_produits'))

    panier[str(product_id)] = panier.get(str(product_id), 0) + quantite
    session['panier'] = panier
    flash('Produit ajoute au panier.')
    return redirect(url_for('client.voir_produits'))

@client_bp.route('/client/panier/modifier/<int:product_id>', methods=['POST'])
@login_required
def modifier_panier(product_id):
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    panier = session.get('panier', {})
    quantite = int(request.form.get('quantite', 1))
    if quantite <= 0:
        panier.pop(str(product_id), None)
    else:
        panier[str(product_id)] = quantite
    session['panier'] = panier
    flash('Panier mis a jour.')
    return redirect(url_for('client.voir_panier'))

@client_bp.route('/client/panier/supprimer/<int:product_id>', methods=['POST'])
@login_required
def supprimer_du_panier(product_id):
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    panier = session.get('panier', {})
    panier.pop(str(product_id), None)
    session['panier'] = panier
    flash('Produit supprime du panier.')
    return redirect(url_for('client.voir_panier'))

@client_bp.route('/client/commande/passer', methods=['GET', 'POST'])
@login_required
def passer_commande():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    panier = session.get('panier', {})
    if not panier:
        flash('Votre panier est vide.')
        return redirect(url_for('client.client_home'))
    total = 0
    for product_id, quantite in panier.items():
        try:
            pid = int(product_id)
        except ValueError:
            flash('Un produit dans votre panier n\'est plus disponible.')
            return redirect(url_for('client.voir_panier'))
        produit = db.session.get(Product, pid)
        if produit is None:
            flash('Un produit dans votre panier n\'est plus disponible.')
            return redirect(url_for('client.voir_panier'))
        if produit.quantite < quantite:
            flash(f'Stock insuffisant pour le produit {produit.nom}.')
            return redirect(url_for('client.voir_panier'))
        total += produit.prix * quantite
    commande = Order(client_id=current_user.id, date=datetime.now(UTC), statut='en attente', total=total)
    db.session.add(commande)
    db.session.flush()
    # Compute default delivery fee based on products' shops
    try:
        commande.frais_livraison = commande.calculate_delivery_fee()
        db.session.add(commande)
    except Exception:
        # if calculation fails, leave frais_livraison None
        pass
    for product_id, quantite in panier.items():
        produit = db.session.get(Product, int(product_id))
        produit.quantite -= quantite
        item = OrderItem(order_id=commande.id, product_id=produit.id, quantite=quantite, prix=produit.prix)
        db.session.add(item)
    db.session.commit()
    session['panier'] = {}
    flash('Commande passee avec succes.')
    return redirect(url_for('client.choisir_paiement', order_id=commande.id))

@client_bp.route('/client/choisir_paiement/<int:order_id>')
@login_required
def choisir_paiement(order_id):
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    commande = Order.query.filter_by(id=order_id, client_id=current_user.id).first()
    if not commande:
        flash('Commande non trouvee.', 'danger')
        return redirect(url_for('client.client_orders'))
    return render_template('client/choisir_paiement.html', commande=commande)

@client_bp.route('/client/traiter_paiement', methods=['POST'])
@login_required
def traiter_paiement():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    order_id = request.form.get('order_id', type=int)
    montant = request.form.get('montant', type=float)
    methode = request.form.get('mode', type=str)

    commande = Order.query.filter_by(id=order_id, client_id=current_user.id).first()
    if not commande:
        flash('Commande non trouvee.', 'danger')
        return redirect(url_for('client.client_orders'))

    if montant is None or montant <= 0:
        flash('Montant invalide.', 'danger')
        return redirect(url_for('client.choisir_paiement', order_id=commande.id))

    # Delivery fields: may be set from the payment form
    mode_livraison = request.form.get('mode_livraison')
    adresse = request.form.get('adresse')
    frais_livraison = request.form.get('frais_livraison')
    date_livraison_str = request.form.get('date_livraison')

    # Try to parse frais_livraison and date_livraison
    try:
        frais_livraison_val = float(frais_livraison) if frais_livraison not in (None, '') else None
    except ValueError:
        frais_livraison_val = None

    try:
        date_livraison_val = datetime.fromisoformat(date_livraison_str) if date_livraison_str else None
    except Exception:
        date_livraison_val = None

    # persist delivery info on the order before payment
    if mode_livraison:
        commande.mode_livraison = mode_livraison
    if adresse:
        commande.adresse = adresse
    if frais_livraison_val is not None:
        commande.frais_livraison = frais_livraison_val
    if date_livraison_val is not None:
        commande.date_livraison = date_livraison_val

    db.session.add(commande)
    db.session.flush()

    payment_status = 'en attente'
    transaction_id = None

    if methode in ('Carte Bancaire', 'Mobile Money'):
        payment_status = 'paye'
        commande.statut = 'paye'
    elif methode == 'CinetPay':
        payment_status = 'en attente'
        transaction_id = f"CINETPAY-{uuid.uuid4().hex[:12].upper()}"
    else:
        flash('Mode de paiement non supporte.', 'danger')
        return redirect(url_for('client.choisir_paiement', order_id=commande.id))

    payment = Payment(
        order_id=commande.id,
        montant=montant,
        methode=methode,
        statut=payment_status,
        transaction_id=transaction_id,
    )
    db.session.add(payment)
    db.session.commit()
    flash('Paiement traite avec succes.')
    if methode == 'CinetPay':
        return redirect(url_for('client.cinetpay_checkout', payment_id=payment.id))
    return redirect(url_for('client.client_orders'))


@client_bp.route('/client/delivery/calc', methods=['POST'])
@login_required
def delivery_calc():
    if current_user.role != 'client':
        return {'error': 'unauthorized'}, 403
    addr = request.form.get('address') or request.json.get('address') if request.is_json else request.form.get('address')
    order_id = request.form.get('order_id', type=int) or (request.json.get('order_id') if request.is_json else None)

    # geocode target address
    coords = geocode_address(addr)
    if not coords:
        return {'error': 'unable_to_geocode'}, 400
    lat, lon = coords

    # find shops present in the order; if no order provided, consider all shops
    shop_ids = set()
    if order_id:
        order = Order.query.filter_by(id=order_id, client_id=current_user.id).first()
        if not order:
            return {'error': 'order_not_found'}, 404
        for item in order.items:
            if item.product and getattr(item.product, 'shop_id', None):
                shop_ids.add(item.product.shop_id)
    else:
        shop_ids = {s.id for s in Shop.query.all()}

    def haversine(lat1, lon1, lat2, lon2):
        # return distance in kilometers
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        km = 6371 * c
        return km

    total_fee = 0.0
    per_km = 0.5
    distances = []
    for sid in shop_ids:
        shop = db.session.get(Shop, sid)
        if shop and shop.latitude and shop.longitude:
            d = haversine(lat, lon, shop.latitude, shop.longitude)
            fee = (shop.delivery_fee or 0.0) + d * per_km
            total_fee += fee
            distances.append({'shop_id': sid, 'distance_km': d, 'fee': round(fee,2)})
        else:
            # fallback to static fee
            fee = (shop.delivery_fee or 5.0) if shop else 5.0
            total_fee += fee
            distances.append({'shop_id': sid, 'distance_km': None, 'fee': round(fee,2)})

    # ETA: assume max distance -> days = ceil(distance/50) + 1
    max_d = max((d['distance_km'] or 0) for d in distances) if distances else 0
    import math
    eta_days = int(math.ceil(max_d / 50.0)) + 1 if max_d > 0 else 3
    from datetime import datetime, timedelta
    eta_date = (datetime.utcnow() + timedelta(days=eta_days)).date().isoformat()

    return {'fee': round(total_fee,2), 'eta': eta_date, 'details': distances}

@client_bp.route('/client/paiement/cinetpay/<int:payment_id>')
@login_required
def cinetpay_checkout(payment_id):
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))

    payment = Payment.query.join(Order, Payment.order_id == Order.id).filter(
        Payment.id == payment_id,
        Order.client_id == current_user.id,
        Payment.methode == 'CinetPay'
    ).first_or_404()

    # Initialize CinetPay API
    api_key = current_app.config.get('CINETPAY_API_KEY')
    site_id = current_app.config.get('CINETPAY_SITE_ID')
    
    if not api_key or not site_id:
        flash('CinetPay not configured. Please add credentials.', 'danger')
        return redirect(url_for('client.client_orders'))
    
    cinetpay = CinetPayAPI(api_key, site_id)
    
    # Generate CinetPay payment link
    return_url = url_for('client.cinetpay_return', payment_id=payment_id, _external=True)
    notify_url = url_for('client.cinetpay_webhook', _external=True)
    
    payment_url = cinetpay.generate_payment_link(
        transaction_id=payment.transaction_id,
        amount=payment.montant,
        description=f"Order #{payment.order_id}",
        return_url=return_url,
        notify_url=notify_url,
        customer_email=current_user.email,
        currency="XOF"
    )
    
    if payment_url:
        return redirect(payment_url)
    else:
        flash('Failed to generate CinetPay payment link.', 'danger')
        return redirect(url_for('client.choisir_paiement', order_id=payment.order_id))


@client_bp.route('/client/paiement/cinetpay/retour/<int:payment_id>')
@login_required
def cinetpay_return(payment_id):
    """Handle return from CinetPay after user completes payment."""
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))

    payment = Payment.query.join(Order, Payment.order_id == Order.id).filter(
        Payment.id == payment_id,
        Order.client_id == current_user.id,
        Payment.methode == 'CinetPay'
    ).first_or_404()

    # Verify payment status with CinetPay
    api_key = current_app.config.get('CINETPAY_API_KEY')
    site_id = current_app.config.get('CINETPAY_SITE_ID')
    
    if api_key and site_id:
        cinetpay = CinetPayAPI(api_key, site_id)
        if cinetpay.verify_payment(payment.transaction_id):
            payment.statut = 'paye'
            payment.order.statut = 'paye'
            db.session.commit()
            flash('Paiement CinetPay confirme avec succes.', 'success')
            return redirect(url_for('client.client_orders'))
    
    flash('Paiement en attente de confirmation. Verifiez votre compte.', 'info')
    return redirect(url_for('client.client_orders'))


@client_bp.route('/client/paiement/cinetpay/webhook', methods=['POST'])
def cinetpay_webhook():
    """Handle CinetPay webhook notification."""
    try:
        data = request.get_json() or request.form.to_dict()
        transaction_id = data.get('transaction_id')
        status = data.get('status', '').lower()
        
        if not transaction_id:
            return {'error': 'missing_transaction_id'}, 400
        
        payment = Payment.query.filter_by(transaction_id=transaction_id).first()
        if not payment:
            return {'error': 'payment_not_found'}, 404
        
        # Update payment status based on CinetPay webhook
        if status in ('accepted', 'confirmed', 'success'):
            payment.statut = 'paye'
            payment.order.statut = 'paye'
            db.session.commit()
            return {'status': 'ok'}, 200
        elif status in ('rejected', 'failed'):
            payment.statut = 'echoue'
            db.session.commit()
            return {'status': 'ok'}, 200
        else:
            # pending, processing, etc
            payment.statut = 'en attente'
            db.session.commit()
            return {'status': 'ok'}, 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return {'error': str(e)}, 500

@client_bp.route('/client/produits')
@login_required
def voir_produits():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    query = request.args.get('q', '').strip()
    categorie = request.args.get('categorie', '').strip()
    taille = request.args.get('taille', '').strip()
    marque = request.args.get('marque', '').strip()
    localisation = request.args.get('localisation', '').strip()
    min_prix = request.args.get('min_prix', type=float)
    max_prix = request.args.get('max_prix', type=float)
    page = request.args.get('page', 1, type=int)

    products_query = Product.query

    if query:
        like_pattern = f"%{query}%"
        products_query = products_query.filter(
            or_(Product.nom.ilike(like_pattern), Product.description.ilike(like_pattern))
        )

    filters = []
    if categorie:
        filters.append(Product.categorie == categorie)
    if taille:
        filters.append(Product.taille == taille)
    if marque:
        filters.append(Product.marque.ilike(f"%{marque}%"))
    if localisation:
        filters.append(or_(Product.localisation.ilike(f"%{localisation}%"), User.localisation.ilike(f"%{localisation}%")))
        products_query = products_query.join(User, User.id == Product.vendeur_id)
    if min_prix is not None:
        filters.append(Product.prix >= min_prix)
    if max_prix is not None:
        filters.append(Product.prix <= max_prix)

    if filters:
        products_query = products_query.filter(and_(*filters))

    pagination = products_query.order_by(Product.created_at.desc()).paginate(page=page, per_page=9, error_out=False)
    products = pagination.items
    favoris_ids = {f.product_id for f in Favorite.query.filter_by(user_id=current_user.id).all()}
    categories = ['homme', 'femme', 'enfant']
    tailles = ['XS', 'S', 'M', 'L', 'XL']

    return render_template(
        'client/produits.html',
        products=products,
        query=query,
        categorie=categorie,
        taille=taille,
        marque=marque,
        localisation=localisation,
        min_prix=min_prix,
        max_prix=max_prix,
        categories=categories,
        tailles=tailles,
        pagination=pagination,
        favoris_ids=favoris_ids,
    )

@client_bp.route('/client/favoris')
@login_required
def mes_favoris():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))

    favoris = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.created_at.desc()).all()
    return render_template('client/favoris.html', favoris=favoris)

@client_bp.route('/client/favoris/toggle/<int:product_id>', methods=['POST'])
@login_required
def toggle_favori(product_id):
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))

    product = db.session.get(Product, product_id)
    if product is None:
        flash('Produit introuvable.', 'danger')
        return redirect(url_for('client.voir_produits'))

    favori = Favorite.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if favori:
        db.session.delete(favori)
        flash('Produit retire des favoris.', 'info')
    else:
        db.session.add(Favorite(user_id=current_user.id, product_id=product_id))
        flash('Produit ajoute aux favoris.', 'success')

    db.session.commit()
    return redirect(request.referrer or url_for('client.voir_produits'))

@client_bp.route('/client/messages', methods=['GET', 'POST'])
@login_required
def client_messages():
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        destinataire_id = request.form.get('destinataire_id', type=int)
        contenu = request.form.get('contenu', '').strip()
        destinataire = User.query.filter_by(id=destinataire_id, role='vendeur', actif=True).first()
        if destinataire and contenu:
            db.session.add(Message(expediteur_id=current_user.id, destinataire_id=destinataire.id, contenu=contenu))
            db.session.commit()
            flash('Message envoye avec succes.', 'success')
        else:
            flash('Message invalide.', 'danger')
        return redirect(url_for('client.client_messages', partenaire_id=destinataire_id))

    partenaires = User.query.filter_by(role='vendeur', actif=True).order_by(User.nom.asc()).all()
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
        partenaire = User.query.filter_by(id=partenaire_id, role='vendeur').first()
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
        'client/messages.html',
        partenaires=partenaires,
        conversation=conversation,
        partenaire_selectionne=partenaire,
        unread_by_partner=unread_by_partner,
    )

@client_bp.route('/client/vendeur/<int:vendeur_id>/avis', methods=['POST'])
@login_required
def noter_vendeur(vendeur_id):
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))

    vendeur = User.query.filter_by(id=vendeur_id, role='vendeur').first_or_404()
    note = request.form.get('note', type=int)
    commentaire = request.form.get('commentaire', '').strip()

    if note is None or note < 1 or note > 5:
        flash('La note doit etre entre 1 et 5.', 'danger')
        return redirect(request.referrer or url_for('client.client_orders'))

    a_deja_commande = db.session.query(Order.id).join(OrderItem, Order.id == OrderItem.order_id).join(
        Product, Product.id == OrderItem.product_id
    ).filter(
        Order.client_id == current_user.id,
        Product.vendeur_id == vendeur.id,
        Order.statut.in_(['paye', 'expedie', 'livre'])
    ).first()

    if not a_deja_commande:
        flash('Vous devez acheter avant de noter ce vendeur.', 'warning')
        return redirect(request.referrer or url_for('client.client_orders'))

    deja_note = Review.query.filter_by(client_id=current_user.id, vendeur_id=vendeur.id).first()
    if deja_note:
        deja_note.note = note
        deja_note.commentaire = commentaire
    else:
        db.session.add(Review(client_id=current_user.id, vendeur_id=vendeur.id, note=note, commentaire=commentaire))

    db.session.commit()
    flash('Avis enregistre avec succes.', 'success')
    return redirect(request.referrer or url_for('client.client_orders'))

@client_bp.route('/client/commande/<int:order_id>/modifier')
@login_required
def modifier_commande(order_id):
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    # Logique : rediriger vers la page voir les produits pour choisir un autre produit
    return redirect(url_for('client.voir_produits'))

@client_bp.route('/client/commande/<int:order_id>/supprimer', methods=['POST'])
@login_required
def supprimer_commande(order_id):
    if current_user.role != 'client':
        return redirect(url_for('auth.login'))
    commande = Order.query.filter_by(id=order_id, client_id=current_user.id).first()
    if not commande:
        flash('Commande non trouvee ou acces refuse.', 'danger')
        return redirect(url_for('client.client_orders'))
    # Remettre à jour le stock des produits de la commande côté vendeur
    items = OrderItem.query.filter_by(order_id=commande.id).all()
    for item in items:
        produit = db.session.get(Product, item.product_id)
        if produit:
            produit.quantite += item.quantite

    # Supprimer les items liés
    OrderItem.query.filter_by(order_id=commande.id).delete()
    # Supprimer la commande
    db.session.delete(commande)
    db.session.commit()
    flash('Commande supprimee avec succes et stock mis a jour.', 'success')
    return redirect(url_for('client.client_orders'))
