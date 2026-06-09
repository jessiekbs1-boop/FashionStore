import os
import base64
import json
import secrets
from datetime import datetime
from datetime import timedelta
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from models import db, User

auth_bp = Blueprint('auth', __name__)

ALLOWED_PROFILE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
LOGIN_ATTEMPTS = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 10


def _allowed_profile_file(filename):
    if not filename or '.' not in filename:
        return False
    return filename.rsplit('.', 1)[1].lower() in ALLOWED_PROFILE_EXTENSIONS


def _provider_config(provider):
    provider = (provider or '').lower()
    if provider == 'google':
        return {
            'client_id': os.getenv('GOOGLE_CLIENT_ID', ''),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET', ''),
            'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth',
            'token_url': 'https://oauth2.googleapis.com/token',
            'userinfo_url': 'https://openidconnect.googleapis.com/v1/userinfo',
            'scope': 'openid email profile',
            'response_mode': None,
        }
    if provider == 'apple':
        return {
            'client_id': os.getenv('APPLE_CLIENT_ID', ''),
            'client_secret': os.getenv('APPLE_CLIENT_SECRET', ''),
            'auth_url': 'https://appleid.apple.com/auth/authorize',
            'token_url': 'https://appleid.apple.com/auth/token',
            'userinfo_url': None,
            'scope': 'name email',
            'response_mode': 'form_post',
        }
    return None


def _http_json(url, data=None, headers=None):
    request = Request(url, data=data, headers=headers or {}, method='POST' if data is not None else 'GET')
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode('utf-8'))


def _exchange_code(provider, code, redirect_uri):
    config = _provider_config(provider)
    if not config:
        raise ValueError('unsupported_provider')

    payload = urlencode({
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri,
    }).encode('utf-8')

    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    return _http_json(config['token_url'], data=payload, headers=headers)


def _decode_jwt_payload(token):
    try:
        payload_part = token.split('.')[1]
        padded = payload_part + '=' * (-len(payload_part) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode('utf-8'))
        return json.loads(decoded.decode('utf-8'))
    except Exception:
        return {}


def _social_identity(provider, token_response):
    provider = (provider or '').lower()
    if provider == 'google':
        config = _provider_config(provider)
        access_token = token_response.get('access_token')
        if not access_token:
            raise ValueError('missing_access_token')
        headers = {'Authorization': f'Bearer {access_token}'}
        return _http_json(config['userinfo_url'], headers=headers)

    if provider == 'apple':
        id_token = token_response.get('id_token', '')
        return _decode_jwt_payload(id_token)

    raise ValueError('unsupported_provider')


def _find_or_create_social_user(provider, identity):
    email = (identity.get('email') or '').strip().lower()
    name = (identity.get('name') or '').strip()

    if not email:
        sub = (identity.get('sub') or identity.get('user') or '').strip()
        if sub:
            email = f'{provider}_{sub}@social.local'

    if not email:
        return None, 'Adresse email introuvable chez le fournisseur.'

    user = User.query.filter_by(email=email).first()
    if user:
        if not user.actif:
            return None, 'Compte desactive.'
        return user, None

    if not name:
        name = identity.get('given_name') or identity.get('family_name') or email.split('@')[0]

    user = User(nom=name, email=email, role='client', actif=True)
    user.set_password(secrets.token_urlsafe(24))
    db.session.add(user)
    db.session.commit()
    return user, None


@auth_bp.route('/oauth/<provider>/start')
def oauth_start(provider):
    config = _provider_config(provider)
    if not config or not config['client_id'] or not config['client_secret']:
        flash('La connexion sociale n\'est pas configurée pour ce fournisseur.', 'danger')
        return redirect(url_for('auth.login'))

    state = secrets.token_urlsafe(24)
    session_key = f'oauth_state_{provider}'
    session[session_key] = state

    redirect_uri = url_for('auth.oauth_callback', provider=provider, _external=True)
    params = {
        'client_id': config['client_id'],
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': config['scope'],
        'state': state,
    }
    if config.get('response_mode'):
        params['response_mode'] = config['response_mode']

    auth_url = f"{config['auth_url']}?{urlencode(params)}"
    return redirect(auth_url)


@auth_bp.route('/oauth/<provider>/callback', methods=['GET', 'POST'])
def oauth_callback(provider):
    config = _provider_config(provider)
    if not config or not config['client_id'] or not config['client_secret']:
        flash('La connexion sociale n\'est pas configurée pour ce fournisseur.', 'danger')
        return redirect(url_for('auth.login'))

    incoming = request.form if request.method == 'POST' else request.args
    expected_state = session.pop(f'oauth_state_{provider}', None)
    incoming_state = incoming.get('state')
    if not expected_state or incoming_state != expected_state:
        flash('Session OAuth invalide. Recommencez la connexion.', 'danger')
        return redirect(url_for('auth.login'))

    code = incoming.get('code')
    if not code:
        flash('Code de connexion manquant.', 'danger')
        return redirect(url_for('auth.login'))

    redirect_uri = url_for('auth.oauth_callback', provider=provider, _external=True)
    try:
        token_response = _exchange_code(provider, code, redirect_uri)
        identity = _social_identity(provider, token_response)
        if provider == 'apple' and request.method == 'POST':
            posted_user = incoming.get('user')
            if posted_user:
                try:
                    posted_profile = json.loads(posted_user)
                    identity.setdefault('name', f"{posted_profile.get('name', {}).get('firstName', '')} {posted_profile.get('name', {}).get('lastName', '')}".strip())
                    identity.setdefault('email', posted_profile.get('email'))
                except Exception:
                    pass

        user, error_message = _find_or_create_social_user(provider, identity)
        if error_message:
            flash(error_message, 'danger')
            return redirect(url_for('auth.login'))

        login_user(user)
        flash('Connexion reussie.', 'success')
        return redirect(url_for('client.client_home'))
    except (HTTPError, URLError, ValueError, KeyError, json.JSONDecodeError) as exc:
        current_app.logger.exception('OAuth %s failed: %s', provider, exc)
        flash('Connexion sociale impossible pour le moment.', 'danger')
        return redirect(url_for('auth.login'))

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

        if role not in ('client', 'vendeur'):
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
        
        # Automatically log in the user after registration
        login_user(user)
        flash('Inscription reussie. Bienvenue!')
        
        # Redirect to appropriate dashboard based on role
        if user.role == 'client':
            return redirect(url_for('client.client_home'))
        elif user.role == 'vendeur':
            return redirect(url_for('vendeur.vendeur_home'))
        elif user.role == 'admin':
            return redirect(url_for('admin.admin_home'))
        else:
            return redirect(url_for('auth.index'))
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        now = datetime.utcnow()
        state = LOGIN_ATTEMPTS.get(email, {'count': 0, 'locked_until': None})
        locked_until = state.get('locked_until')
        if locked_until and locked_until > now:
            remaining = int((locked_until - now).total_seconds() // 60) + 1
            flash(f'Trop de tentatives. Reessayez dans {remaining} minute(s).', 'danger')
            return redirect(url_for('auth.login'))

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password) and user.actif:
            LOGIN_ATTEMPTS.pop(email, None)
            login_user(user)
            if user.role == 'client':
                return redirect(url_for('client.client_home'))
            elif user.role == 'vendeur':
                return redirect(url_for('vendeur.vendeur_home'))
            elif user.role == 'admin':
                return redirect(url_for('admin.admin_home'))
        else:
            state['count'] = int(state.get('count', 0)) + 1
            if state['count'] >= MAX_LOGIN_ATTEMPTS:
                state['locked_until'] = now + timedelta(minutes=LOCKOUT_MINUTES)
                state['count'] = 0
            LOGIN_ATTEMPTS[email] = state
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
    if current_user.is_authenticated:
        if current_user.role == 'client':
            return redirect(url_for('client.client_home'))
        if current_user.role == 'vendeur':
            return redirect(url_for('vendeur.vendeur_home'))
        if current_user.role == 'admin':
            return redirect(url_for('admin.admin_home'))
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
