import os
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User

auth_bp = Blueprint('auth', __name__)

ALLOWED_PROFILE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}


def _allowed_profile_file(filename):
    if not filename or '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_PROFILE_EXTENSIONS

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nom = request.form.get('nom', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        role = request.form.get('role', '').strip().lower()
        localisation = request.form.get('localisation', '').strip() or None
        terms_accepted = request.form.get('terms_accepted') == 'on'

        if not nom or not email or len(password) < 6:
            flash('Veuillez remplir correctement le formulaire.')
            return redirect(url_for('auth.register'))

        if not terms_accepted:
            flash('Vous devez accepter les conditions d\'utilisation.', 'danger')
            return redirect(url_for('auth.register'))

        if role not in ('client', 'vendeur', 'admin'):
            flash('Role invalide.')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Email deja utilise.')
            return redirect(url_for('auth.register'))

        user = User(nom=nom, email=email, role=role, localisation=localisation)
        user.terms_accepted = datetime.utcnow()
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Inscription reussie. Connectez-vous.')
        return redirect(url_for('auth.login'))
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.actif:
            login_user(user)
            if user.role == 'client':
                return redirect(url_for('client.client_home'))
            elif user.role == 'vendeur':
                return redirect(url_for('vendeur.vendeur_home'))
            elif user.role == 'admin':
                return redirect(url_for('admin.admin_home'))
        else:
            flash('Identifiants invalides ou compte desactive.')
            return redirect(url_for('auth.login'))
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/')
def index():
    return render_template('home.html')


@auth_bp.route('/conditions')
def conditions():
    return render_template('conditions.html')


@auth_bp.route('/profile')
@login_required
def profile():
    edit_mode = request.args.get('edit', '0') == '1'
    return render_template('profile.html', edit_mode=edit_mode)


@auth_bp.route('/profile/update', methods=['POST'])
@login_required
def update_profile():
    nom = request.form.get('nom', '').strip()
    email = request.form.get('email', '').strip().lower()
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '').strip()
    profile_photo = request.files.get('profile_photo')

    if not nom or not email:
        flash('Nom et email sont requis.', 'danger')
        return redirect(url_for('auth.profile', edit=1))

    existing_user = User.query.filter(User.email == email, User.id != current_user.id).first()
    if existing_user:
        flash('Cet email est deja utilise.', 'danger')
        return redirect(url_for('auth.profile', edit=1))

    if not current_user.check_password(current_password):
        flash('Mot de passe actuel incorrect.', 'danger')
        return redirect(url_for('auth.profile', edit=1))

    if new_password and len(new_password) < 6:
        flash('Le nouveau mot de passe doit contenir au moins 6 caracteres.', 'danger')
        return redirect(url_for('auth.profile', edit=1))

    if profile_photo and profile_photo.filename:
        if not _allowed_profile_file(profile_photo.filename):
            flash('Format image non supporte.', 'danger')
            return redirect(url_for('auth.profile', edit=1))

        safe_name = secure_filename(profile_photo.filename)
        extension = safe_name.rsplit('.', 1)[1].lower()
        filename = f"profile_{current_user.id}_{int(datetime.utcnow().timestamp())}.{extension}"
        destination = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        profile_photo.save(destination)
        current_user.profile_photo = filename

    current_user.nom = nom
    current_user.email = email

    if new_password:
        current_user.set_password(new_password)

    db.session.commit()
    flash('Profil mis a jour avec succes.', 'success')
    return redirect(url_for('auth.profile'))
