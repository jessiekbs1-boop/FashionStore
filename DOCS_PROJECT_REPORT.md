# Rapport pédagogique — Store Fashion

## Résumé
Ce document explique l'architecture, les composants et la logique métier du projet "Store Fashion". Il est destiné à un étudiant en génie logiciel préparant une soutenance : comprendre, réviser et expliquer le code devant un jury.

---

## 1. Architecture générale

Store Fashion est une application web développée avec Flask (Python) suivant une architecture MVC légère :
- Modèle (Models) : `models.py` — définition des tables et relations via SQLAlchemy.
- Vue (Templates) : dossier `templates/` — fichiers Jinja2 HTML, CSS (`static/style.css`) et JS pour l'interaction.
- Contrôleur (Routes) : dossier `routes/` — blueprints Flask séparés par rôle : `auth_routes.py`, `client_routes.py`, `vendeur_routes.py`, `admin_routes.py`.
- Utilitaires : dossier `utils/` — intégration CinetPay, géocodage, Twilio SMS.
- Entrée de l'application : `app.py` — configuration, enregistrement des blueprints, initialisation DB.

Le projet suit une séparation de responsabilités claire : chaque blueprint gère les routes liées à un rôle.

Diagramme simplifié (textuel) :

App -> Blueprints (auth, client, vendeur, admin)
Blueprints -> Models (User, Product, Order, Payment, Shop, ...)
Blueprints -> Templates (render_template(...))
Blueprints -> Utils (CinetPay, geocode, twilio)

---

## 2. Rôle des dossiers et fichiers

- `app.py` : Point d'entrée de l'application; configure Flask, SQLAlchemy, LoginManager; crée tables si nécessaire; registre les blueprints.
- `models.py` : Déclare tous les modèles SQLAlchemy et leurs relations.
- `routes/` : Contient les blueprints :
  - `auth_routes.py` : Inscription, connexion, profil, gestion du logout, conditions.
  - `client_routes.py` : Parcours client : catalogue, panier, commandes, paiements (CinetPay), messages.
  - `vendeur_routes.py` : Espace vendeur : ajouter/modifier produits, voir commandes, messages.
  - `admin_routes.py` : Espace admin : gestion utilisateurs, produits, commandes, boutiques.
- `templates/` : Fichiers Jinja2. `base.html` est le layout principal.
- `static/` : `style.css` et `images/`.
- `utils/` : intégrations externes : `cinetpay.py`, `geocode.py`, `twilio_sms.py`.
- `tests/` : tests unitaires / fonctionnels (pytest).

---

## 3. Fonctionnement de `app.py`

Objectif : initialiser l'application et préparer l'environnement d'exécution.

Étapes importantes :
1. Charger les variables d'environnement via `python-dotenv` (si disponible).
2. Configurer `Flask` : `SECRET_KEY`, `SQLALCHEMY_DATABASE_URI`, `UPLOAD_FOLDER`, clés CinetPay.
3. `db.init_app(app)` : initialise SQLAlchemy.
4. `login_manager = LoginManager()` : configure Flask-Login, définit `user_loader`.
5. `inject_notifications()` (context_processor) : fournit des compteurs (messages non lus, items panier, nouvelles commandes) disponibles dans tous les templates.
6. Enregistrement des blueprints : `auth_bp`, `client_bp`, `vendeur_bp`, `admin_bp`.
7. `ensure_database_ready()` : logique pragmatique pour créer les tables et ajouter des colonnes manquantes via `ALTER TABLE` si nécessaire (utile pour SQLite sans migrations formelles).

Variables importantes :
- `app.config['SQLALCHEMY_DATABASE_URI']` : chaîne de connection DB.
- `app.config['UPLOAD_FOLDER']` : dossier pour sauvegarde des images.
- `app.config['CINETPAY_*']` : clés pour CinetPay.

Remarque pour la soutenance : expliquer pourquoi `ensure_database_ready()` existe (confort/développement) et mentionner que la bonne pratique en production serait d'utiliser Alembic/Flask-Migrate.

---

## 4. Rôle des modèles (`models.py`)

Fichiers principaux et objectifs :

- `User` : représente un utilisateur (client, vendeur, admin). Champs notables : `nom`, `email`, `password_hash`, `role`, `shop_id`.
- `Product` : produit publié par un vendeur. Champs : `nom`, `description`, `prix`, `quantite`, `vendeur_id`, `shop_id`.
- `ProductImage` : images additionnelles d'un produit.
- `Favorite` : lien utilisateur↔produit (favoris).
- `Order` : commande passée par un client. Contient `items` (OrderItem), montant `total`, `statut`, `frais_livraison`, `shop_id`.
- `OrderItem` : relation produit–commande (quantité, prix unitaire au moment de la commande).
- `Payment` : enregistrement d'un paiement (méthode, statut, transaction_id, shop_id).
- `PaymentEvent` : journal des événements liés aux paiements (création, webhook reçu, confirmé, échoué).
- `Review` : avis client→vendeur.
- `Message` : messagerie interne.
- `Shop` : représentation d'une boutique (owner_id, address, delivery_fee, coords).

But pédagogique : chaque table modélise un concept métier et contient les relations nécessaires (clé étrangère, backrefs) pour simplifier l'accès depuis les blueprints.

---

## 5. Relations entre les tables

- `User` (1) -- (N) `Product` via `vendeur_id` : un vendeur a plusieurs produits.
- `Shop` (1) -- (N) `Product` via `shop_id` : une boutique possède plusieurs produits.
- `User` (1) -- (N) `Order` via `client_id` : un client a plusieurs commandes.
- `Order` (1) -- (N) `OrderItem` : une commande contient plusieurs articles.
- `Product` (1) -- (N) `OrderItem` : un produit peut apparaître dans plusieurs commandes.
- `Order` (1) -- (1) `Payment` : une commande a typiquement un paiement (one-to-one via `payment` backref).
- `Payment` (1) -- (N) `PaymentEvent` : logs d'événements.
- `User` (1) -- (N) `Message` (sent & received) : messagerie entre utilisateurs.

Expliquer au jury : la conception vise la simplicité et la lecture fluide dans le code (ex : `order.items`, `product.order_items`, `user.products`).

---

## 6. Fonctionnement des routes Flask

Organisation : un blueprint par domaine utilisateur.

Pattern commun :
1. Vérifier rôle (`current_user.role`) et autorisation.
2. Récupérer les entités via SQLAlchemy.
3. Faire la logique métier (calcul frais, validation stock, créer commande, etc.).
4. Effectuer `db.session.add()` / `db.session.commit()`.
5. Rediriger / rendre template.

Exemple simplifié (`/client/commande/passer`) :
- Vérifie que le panier n'est pas vide.
- Valide la disponibilité & le stock de chaque produit.
- Crée `Order`, `OrderItem` pour chaque produit.
- Décrémente le stock (`produit.quantite -= quantite`).
- Calcule `frais_livraison` si nécessaire.
- Vide le `session['panier']`.
- Redirige vers la page de choix du paiement.

Points d'attention :
- Utilisation de `session` pour stocker le panier côté client.
- Nombreuses routes prototypées pour : ajouter/modifier/supprimer produit (vendeur), gérer utilisateurs (admin), messages (client/vendeur).

---

## 7. Système d'authentification

Bibliothèque : `Flask-Login`.

Flux :
- `register` : création de `User` (hash du mot de passe avec Werkzeug), enregistrement `terms_accepted`.
- Après création, l'utilisateur est automatiquement connecté (`login_user(user)`) et redirigé vers son dashboard.
- `login` : vérifie `email` et `password` (via `check_password`).
- `logout` : `logout_user()`.

Sécurité ajoutée :
- Limitation des tentatives de connexion (protection anti-brute-force) : en mémoire dans `LOGIN_ATTEMPTS` (implémentation simple pour la démonstration). En production, utiliser Redis ou services spécialisés.

Variables clés :
- `user.password_hash` : mot de passe haché.
- `login_user(user)` : marque la session utilisateur comme authentifiée.

---

## 8. Système multi-boutiques

Concept : chaque `Produit`, `Order`, `Payment`, `Message`, `Review` peut être rattaché à une `Shop` via `shop_id`. Un `User` peut aussi être lié à une `Shop` (champ `shop_id`) pour représenter un administrateur/vendeur d'une boutique.

Implémentation :
- Lors des requêtes dans `admin_routes.py` et `vendeur_routes.py`, les requêtes filtrent par `current_user.shop_id` si ce champ est présent.
- Lors de la création de produits, `shop_id` est automatiquement assigné.
- Lors du passage de commande, si tous les produits du panier proviennent d'une seule boutique, `order.shop_id` est assigné.

Raisonnement : ce modèle permet une isolation logique des données par boutique et un futur calcul de commissions/rapports.

---

## 9. Panier et commandes

- Panier (côté client) : stocké dans `session['panier']` sous forme `{product_id: quantite}`.
- Ajouter au panier : route POST qui met à jour la session.
- Passer commande : vérifie la disponibilité, crée `Order` et `OrderItem`, réduit le stock, calcule livraison.

Détails techniques :
- `Order.calculate_delivery_fee()` : additionne `delivery_fee` distincts par boutique.
- `frais_livraison` peut être recalculé via un endpoint `delivery_calc` qui appelle `utils.geocode.geocode_address()` pour calculer la distance et estimer un coût.

Exemple :
```python
panier = session.get('panier', {})
for product_id, quantite in panier.items():
    produit = db.session.get(Product, int(product_id))
    item = OrderItem(order_id=commande.id, product_id=produit.id, quantite=quantite, prix=produit.prix)
    db.session.add(item)
```

---

## 10. Système de paiement

Approche : plusieurs méthodes supportées (Carte, Mobile Money, CinetPay). Actuellement :
- `CinetPay` : intégration via `utils/cinetpay.py`.
- Pour CinetPay : la route `client.cinetpay_checkout` génère une URL de paiement et redirige l'utilisateur.
- `client.cinetpay_return` vérifie le statut côté API après redirection.
- `client.cinetpay_webhook` : route serveur recevant les notifications (webhook) de CinetPay.

Robustesse ajoutée :
- `PaymentEvent` enregistre tous les événements liés aux paiements (création, redirect, webhook reçu, confirmation).
- Validation de signature webhook (HMAC) via `CinetPayAPI.validate_webhook()` et variable `CINETPAY_WEBHOOK_SECRET`.
- Idempotence simple : si `payment.statut == 'paye'`, ne pas re-traiter.

Variables clés :
- `Payment.transaction_id` : identifiant externe utilisé pour vérifier le paiement.
- `Payment.statut` : `en attente`, `paye`, `echoue`.

---

## 11. Messagerie

- Modèle : `Message` (expediteur_id, destinataire_id, contenu, lu, shop_id).
- Routes : échange entre client et vendeur via listes de conversations et envoi POST.
- UX : pages `templates/client/messages.html` et `templates/vendeur/messages.html`.
- Fonctionnalité : marquage `lu` automatique lors de consultation.

Remarque : en production, on pourrait améliorer avec WebSockets (socket.io) pour temps réel.

---

## 12. Dashboards (client, vendeur, admin)

- `client_dashboard` : affiche produits récents, actions de base (ajouter au panier, favoris).
- `vendeur_dashboard` : statistiques vendeur (nombre produits, ventes, revenus, note moyenne). Les requêtes sont filtrées par `vendeur_id` et éventuellement `shop_id`.
- `admin_dashboard` : vue globale (utilisateurs, produits, commandes). Si `admin.shop_id` est défini, l'admin voit seulement sa boutique.

Chaque dashboard est une vue Jinja qui récupère données via ORM et les présente avec des composants réutilisables (cards, grilles de produits).

---

## 13. Technologies utilisées et justification

- Python + Flask : léger, adapté aux projets académiques, facilité d'apprentissage et large écosystème.
- SQLAlchemy (Flask-SQLAlchemy) : ORM pour relations, requêtes lisibles.
- Flask-Login : gestion de session/auth.
- Jinja2 Templates + Bootstrap 5 : rendu HTML/CSS simple et responsive.
- Requests : appels HTTP externes (CinetPay, Nominatim).
- PyTest : tests automatisés.

Choix pédagogiques : simplicité, transparence du code et facilité de déploiement sur small VPS.

---

## 14. Sécurité de base implémentée

- Hachage des mots de passe (Werkzeug `generate_password_hash`).
- Limitation simple des tentatives de connexion (mémoire, à remplacer par Redis pour production).
- Validation et restriction des formats d'images uploadées.
- Vérification de signature webhook (HMAC) pour CinetPay.
- Contrôles d'accès par rôle (`current_user.role`) et filtrage `shop_id` pour isolation.

A améliorer pour la production : CSRF, Content Security Policy, HTTPs, validation stricte des entrées, limitation d'upload size, protection contre injection.

---

## 15. Fonctionnement des templates HTML/CSS/JS

- `templates/base.html` : layout principal avec barre de navigation, offcanvas menu et injection des messages flash. Toutes les pages héritent de `base.html`.
- `templates/*` : pages spécifiques utilisent blocs Jinja (`block content`) et s'appuient sur variables passées depuis les routes.
- CSS : `static/style.css` centralise la charte graphique (variables CSS, components cards, menu).
- JS léger : interactions (offcanvas closing, affichage conditionnel des champs de paiement, appel du endpoint `delivery_calc` pour calcul frais).

Exemple (JS) : dans `choisir_paiement.html`, la fonction `fetchFee(address)` appelle `POST /client/delivery/calc` pour obtenir le coût et la date estimée.

---

## Annexes — Exemples de code et explications pas-à-pas

### 1) Inscription (extrait simplifié)

Objectif : créer l'utilisateur et le connecter.

```python
# auth_routes.register (extrait)
user = User(nom=nom, email=email, role=role, localisation=localisation)
user.set_password(password)
db.session.add(user)
db.session.commit()
# login automatique
login_user(user)
return redirect(url_for('client.client_home' if user.role=='client' else 'vendeur.vendeur_home'))
```

Étapes : validation des champs → création du modèle → persist → connexion → redirection.

### 2) Passage de commande (extrait)

Objectif : transformer le panier en commande persistée

```python
commande = Order(client_id=current_user.id, total=total, statut='en attente')
db.session.add(commande)
db.session.flush()
for product_id, quantite in panier.items():
    produit = db.session.get(Product, int(product_id))
    produit.quantite -= quantite
    db.session.add(OrderItem(order_id=commande.id, product_id=produit.id, quantite=quantite, prix=produit.prix))
db.session.commit()
```

Étapes : validation stock → créer `Order` → créer `OrderItem` → mettre à jour stock → commit.

### 3) Webhook CinetPay (extrait)

Objectif : recevoir notification paiement et marquer le paiement comme `paye`.

```python
payload_raw = request.get_data(as_text=True)
if not cinetpay.validate_webhook(signature, payload_raw, webhook_secret):
    return {'error':'invalid_signature'}, 401
payment = Payment.query.filter_by(transaction_id=transaction_id).first()
if status in ('accepted','confirmed') and payment.statut != 'paye':
    payment.statut = 'paye'
    payment.order.statut = 'paye'
    db.session.commit()
```

---

## Recommandations pour la soutenance (ce qu'il faut mettre en avant)

1. Expliquez la séparation claire MVC et le rôle des blueprints.
2. Montrez un scénario complet : inscription → ajout produit → panier → commande → paiement.
3. Démontrez la gestion multi-boutique (filtrage `shop_id`).
4. Présentez les limitations et les pistes d'amélioration (migrations Alembic, CSRF, tests supplémentaires, déploiement Docker, monitoring).
5. Ayez quelques exemples SQLAlchemy (joins, aggregates) prêts à expliquer les requêtes de dashboard.

---

## Prochaines tâches recommandées (pour production)

- Mettre en place Alembic/Flask-Migrate pour migrations DB.
- Ajouter CSRF (Flask-WTF) et validation côté serveur.
- Stocker sessions et rate-limit en Redis pour persistance et scalabilité.
- Ajouter tests d'intégration (paiement webhook simulé).
- Automatiser le déploiement (Docker + CI/CD).

---

## Fichier généré
Le rapport est enregistré dans `DOCS_PROJECT_REPORT.md` à la racine du projet.


