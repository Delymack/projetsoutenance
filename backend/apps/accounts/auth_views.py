"""Vues « pages » de l'espace d'authentification (connexion, inscription,
mot de passe oublié, lien magique, double authentification, sécurité).

Chaque page reprend la charte graphique de la page de connexion
(templates/admin/auth/*) : fond dense, or, verre de vin, formulaires doux.
"""
import hashlib
import re
import secrets
import time

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth import password_validation
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User, VerificationCode
from apps.accounts.services.email_service import raison_echec_email
from apps.accounts.services.sms_service import send_verification_sms
from apps.accounts.utils import generate_code
from apps.accounts.services import (
    clear_totp_attempts,
    magic_link_token,
    magic_link_user,
    obfuscate_totp_secret,
    record_totp_failed,
    send_email_quiet,
    send_otp_email,
    TooSoonOTP,
    totp_locked,
    totp_new_secret,
    totp_qr_svg,
    unobfuscate_totp_secret,
    verify_otp,
    verify_totp,
)

AUTH_BACKEND = 'apps.accounts.backends.EmailOrUsernameBackend'


def _safe_next(request, value, default='/admin/'):
    """Valide une cible de redirection afin de bloquer les open-redirects."""
    if url_has_allowed_host_and_scheme(
        value, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return value
    return default


def _login_user(request, user, next_url=None):
    """Connecte l'utilisateur via le backend maison (signaux/décorateurs OK)."""
    user.backend = AUTH_BACKEND
    login(request, user)
    return redirect(_safe_next(request, next_url))


def _render(request, template, context):
    return render(request, f'admin/auth/{template}.html', context)


_PHONE_RE = re.compile(r'^\+?261[0-9]{9}$')


def _normaliser_telephone(value):
    """Normalise un numéro malgache en ``+261XXXXXXXXX`` (``''`` si vide)."""
    digits = re.sub(r'\D', '', value or '')
    if not digits:
        return ''
    if digits.startswith('261'):
        return '+' + digits
    if len(digits) == 10 and digits.startswith('0'):
        return '+261' + digits[1:]
    if len(digits) == 9:
        return '+261' + digits
    return '+' + digits


# ---------------------------------------------------------------------------
# Inscription
# ---------------------------------------------------------------------------

@require_http_methods(['GET', 'POST'])
def signup_view(request):
    if getattr(request, 'user', None) and request.user.is_authenticated:
        return redirect('/admin/')
    if not getattr(settings, 'AUTH_SIGNUP_ENABLED', True):
        return _render(request, 'message', _message_ctx('signup_disabled'))

    errors = {}
    values = {
        'nom': '', 'username': '', 'email': '', 'telephone': '',
        'first_name': '', 'last_name': '', 'contact_type': 'email',
    }
    if request.method == 'POST':
        for key in values:
            values[key] = request.POST.get(key, '').strip()
        contact_type = values['contact_type'] if values['contact_type'] in ('email', 'sms') else 'email'
        values['contact_type'] = contact_type

        nom = values['nom'].strip()
        if nom and not (values['first_name'] or values['last_name']):
            parties = nom.split()
            values['first_name'] = parties[0] or ''
            values['last_name'] = ' '.join(parties[1:]) if len(parties) > 1 else ''
        if not values['first_name'] and not values['last_name'] and len(nom) < 3:
            errors['nom'] = 'Indiquez un nom d’au moins 3 caractères.'

        email = values['email'].lower()
        if '@' not in email:
            if contact_type == 'email':
                errors['email'] = 'Adresse e-mail invalide.'
        elif User.objects.filter(email__iexact=email).exists():
            errors['email'] = 'Un compte existe déjà avec cet e-mail.'

        telephone = _normaliser_telephone(values['telephone'])
        values['telephone'] = telephone
        if contact_type == 'sms':
            if not telephone:
                errors['telephone'] = 'Le numéro de téléphone est obligatoire pour ce mode d’envoi.'
            elif not _PHONE_RE.match(telephone):
                errors['telephone'] = 'Numéro de téléphone invalide. Format attendu : +261 34 00 000 00.'
            elif User.objects.filter(telephone=telephone).exists():
                errors['telephone'] = 'Un compte existe déjà avec ce numéro.'

        username = values['username'] or (telephone if contact_type == 'sms' else email)
        if not username:
            errors['username'] = 'Le nom d’utilisateur doit contenir au moins 3 caractères.'
        elif len(username) < 3:
            errors['username'] = 'Le nom d’utilisateur doit contenir au moins 3 caractères.'
        elif User.objects.filter(username__iexact=username).exists():
            errors['username'] = 'Ce nom d’utilisateur est déjà pris.'
        values['username'] = username

        password = request.POST.get('password1') or request.POST.get('password') or ''
        password2 = request.POST.get('password2', '')
        if not password:
            errors['password'] = 'Veuillez choisir un mot de passe.'
        elif password2 and password != password2:
            errors['password'] = 'Les deux mots de passe ne correspondent pas.'
        else:
            try:
                password_validation.validate_password(password)
            except ValidationError as exc:
                errors['password'] = exc.messages[0]

        if not errors:
            if contact_type == 'sms' and User.objects.filter(username__iexact=telephone).exists():
                errors['telephone'] = 'Un compte existe déjà avec ce numéro.'
            else:
                user = User(
                    username=username,
                    email=email or None,
                    telephone=telephone or None,
                    first_name=values['first_name'],
                    last_name=values['last_name'],
                    role=User.Role.VENDEUR,
                    is_active=False,
                    is_staff=getattr(settings, 'SIGNUP_STAFF', False),
                )
                user.set_password(password)
                user.save()

                if contact_type == 'sms':
                    # Anti-spam : un code émis il y a moins d'une minute n'est pas réémis.
                    en_attente = (
                        VerificationCode.objects
                        .filter(contact=telephone, purpose=VerificationCode.PURPOSE_SIGNUP, is_used=False)
                        .order_by('-created_at')
                        .first()
                    )
                    if en_attente and not en_attente.can_resend():
                        user.delete()
                        errors['telephone'] = 'Nouveau code déjà envoyé, vérifiez votre téléphone.'
                    else:
                        VerificationCode.objects.filter(
                            contact=telephone, purpose=VerificationCode.PURPOSE_SIGNUP, is_used=False
                        ).delete()
                        code = generate_code()
                        vc = VerificationCode.objects.create(
                            contact=telephone,
                            contact_type=VerificationCode.CONTACT_SMS,
                            purpose=VerificationCode.PURPOSE_SIGNUP,
                        )
                        vc.set_code(code)
                        if send_verification_sms(telephone, code, VerificationCode.PURPOSE_SIGNUP):
                            return redirect(reverse('auth-verify-email') + f'?contact={telephone}&type=sms')
                        vc.delete()
                        user.delete()
                        errors['telephone'] = (
                            "Envoi du SMS impossible : clé API eSMS Africa invalide/expirée, "
                            "solde épuisé ou sender ID non approuvé (voir le journal du serveur)."
                        )
                else:
                    try:
                        envoye = send_otp_email(email, purpose='verify', titre="Votre code de vérification LAZAN'I BETSILEO")
                    except TooSoonOTP:
                        user.delete()
                        errors['email'] = 'Nouveau code déjà envoyé, vérifiez votre boîte mail.'
                    else:
                        if envoye:
                            return redirect(reverse('auth-verify-email') + f'?email={email}')
                        user.delete()
                        errors['email'] = raison_echec_email()

    return _render(request, 'signup', {'errors': errors, 'values': values})


@require_http_methods(['GET', 'POST'])
def verify_email_view(request):
    contact_type = (request.GET.get('type') or request.POST.get('type') or 'email').lower()
    contact_type = contact_type if contact_type in ('email', 'sms') else 'email'
    if contact_type == 'sms':
        contact = (request.GET.get('contact') or request.POST.get('contact') or '').strip()
    else:
        contact = (request.GET.get('email') or request.POST.get('email') or '').strip().lower()
    if not contact:
        return redirect(reverse('auth-signup'))

    def ctx(**extra):
        contexte = {'contact': contact, 'email': contact, 'contact_type': contact_type}
        contexte.update(extra)
        return contexte

    if request.method != 'POST':
        return _render(request, 'verify_email', ctx())

    code = request.POST.get('code', '')
    action = request.POST.get('action', '')

    if contact_type == 'sms':
        user = User.objects.filter(telephone=contact, is_active=False).first()
        vc = (
            VerificationCode.objects
            .filter(contact=contact, purpose=VerificationCode.PURPOSE_SIGNUP, is_used=False)
            .order_by('-created_at')
            .first()
        )
        if user is None:
            return _render(request, 'verify_email', ctx(error='Compte introuvable ou déjà activé.'))

        if action == 'resend':
            if vc and not vc.can_resend():
                return _render(request, 'verify_email', ctx(error='Merci d’attendre avant de demander un nouveau code.'))
            if vc:
                vc.delete()
            nouveau_code = generate_code()
            vc = VerificationCode.objects.create(
                contact=contact,
                contact_type=VerificationCode.CONTACT_SMS,
                purpose=VerificationCode.PURPOSE_SIGNUP,
            )
            vc.set_code(nouveau_code)
            if not send_verification_sms(contact, nouveau_code, VerificationCode.PURPOSE_SIGNUP):
                vc.delete()
                return _render(request, 'verify_email', ctx(error='Envoi du SMS impossible, réessayez.'))
            return _render(request, 'verify_email', ctx(resent=True))

        if vc is None or not vc.verify_code(code):
            if vc:
                vc.increment_attempts()
            return _render(request, 'verify_email', ctx(error='Code invalide ou expiré. Réessayez.'))

        user.is_active = True
        user.is_staff = getattr(settings, 'SIGNUP_STAFF', False)
        user.save(update_fields=['is_active', 'is_staff'])
        vc.set_used()
        return _login_user(request, user, request.POST.get('next') or '/admin/')

    # Canal e-mail
    user = User.objects.filter(email__iexact=contact, is_active=False).first()
    if user is None:
        return _render(request, 'verify_email', ctx(error='Compte introuvable ou déjà activé.'))

    if action == 'resend':
        try:
            envoye = send_otp_email(contact, purpose='verify', titre="Votre code de vérification LAZAN'I BETSILEO")
        except TooSoonOTP as exc:
            return _render(request, 'verify_email', ctx(error=str(exc)))
        if not envoye:
            return _render(request, 'verify_email',
                           ctx(error="Envoi de l'email impossible. Réessayez dans un instant."))
        return _render(request, 'verify_email', ctx(resent=True))

    if verify_otp(contact, 'verify', code):
        user.is_active = True
        user.is_staff = getattr(settings, 'SIGNUP_STAFF', False)
        user.save(update_fields=['is_active', 'is_staff'])
        return _login_user(request, user, request.POST.get('next') or '/admin/')
    return _render(request, 'verify_email', ctx(error='Code invalide ou expiré. Réessayez.'))


# ---------------------------------------------------------------------------
# Mot de passe oublié
# ---------------------------------------------------------------------------

@require_http_methods(['GET', 'POST'])
def forgot_password_view(request):
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()
        try:
            # Code émis même pour un inconnu (anti-fuites) ; e-mail expédié seulement si compte.
            send_otp_email(email, purpose='reset', titre="Votre code de réinitialisation LAZAN'I BETSILEO")
        except TooSoonOTP as exc:
            return _render(request, 'forgot_password', {'email': email, 'error': str(exc)})
        return redirect(reverse('auth-reset-password') + f'?email={email}')
    return _render(request, 'forgot_password', {})


@require_http_methods(['GET', 'POST'])
def reset_password_view(request):
    email = (request.GET.get('email') or request.POST.get('email') or '').strip().lower()
    errors = {}
    if request.method == 'POST':
        code = request.POST.get('code', '')
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if not password1 or password1 != password2:
            errors['password'] = 'Les deux mots de passe ne correspondent pas.'
        else:
            try:
                password_validation.validate_password(password1, user=user)
            except ValidationError as exc:
                errors['password'] = exc.messages[0]
        if not errors and (user is None or not verify_otp(email, 'reset', code)):
            errors['code'] = 'Code invalide ou expiré.'
        if not errors and user is not None:
            user.set_password(password1)
            user.save(update_fields=['password'])
            return redirect(reverse('auth-message') + '?kind=password_ok')
    return _render(request, 'reset_password', {'email': email, 'errors': errors})


# ---------------------------------------------------------------------------
# Connexion par lien magique
# ---------------------------------------------------------------------------

@require_http_methods(['GET', 'POST'])
def magic_link_page_view(request):
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is not None:
            token = magic_link_token(user)
            link = request.build_absolute_uri(reverse('auth-magic-link-confirm', args=[token]))
            send_email_quiet(
                "Votre lien de connexion LAZAN'I BETSILEO",
                email,
                'magic_link',
                context={'prenom': user.first_name or user.username, 'link': link},
            )
        return _render(request, 'message', _message_ctx('magic_sent'))
    return _render(request, 'magic_link', {})


@require_http_methods(['GET'])
def magic_link_confirm_view(request, token):
    if getattr(request, 'user', None) and request.user.is_authenticated:
        if request.session.get('twofa_pending'):
            return redirect('/admin/2fa/verify/')
        return redirect('/admin/')
    user = magic_link_user(token)
    if user is None:
        return _render(request, 'message', _message_ctx('magic_invalid'))
    request.session['twofa_next'] = '/admin/'
    return _login_user(request, user, '/admin/')


# ---------------------------------------------------------------------------
# Double authentification (2FA / TOTP + codes de secours)
# ---------------------------------------------------------------------------

def _hash_recovery(code):
    return hashlib.sha256(f'{code}:{settings.SECRET_KEY}:recovery'.encode()).hexdigest()


def _new_recovery_codes(n=8):
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return ['-'.join(''.join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)) for _ in range(n)]


def _recovery_list(user):
    raw = user.recovery_codes or ''
    return [c for c in raw.split(',') if c]


def _save_recovery(user, hashed_codes):
    user.recovery_codes = ','.join(hashed_codes)
    user.save(update_fields=['recovery_codes'])


@login_required
def enable_2fa_view(request):
    if getattr(request.user, 'totp_enabled', False):
        return redirect(reverse('auth-account'))
    if request.session.get('twofa_pending'):
        return redirect('/admin/2fa/verify/')

    secret = request.session.get('totp_pending_secret') or totp_new_secret()
    request.session['totp_pending_secret'] = secret

    error = None
    if request.method == 'POST':
        action = request.POST.get('action', 'confirm')
        if action == 'cancel':
            request.session['totp_pending_secret'] = None
            return redirect(reverse('auth-account'))
        code = (request.POST.get('code') or '').strip()
        if verify_totp(secret, code):
            request.user.totp_secret = obfuscate_totp_secret(secret)
            request.user.totp_enabled = True
            plain_codes = _new_recovery_codes()
            _save_recovery(request.user, [_hash_recovery(c) for c in plain_codes])
            request.user.save(update_fields=['totp_secret', 'totp_enabled'])
            request.session['totp_pending_secret'] = None
            request.session['twofa_pending'] = False
            request.session['recovery_codes_display'] = plain_codes
            return redirect(reverse('auth-message') + '?kind=2fa_enabled')
        error = 'Code invalide. Vérifiez l’heure de votre appareil (réglée sur l’heure automatique).'

    return _render(request, 'twofa_enable', {
        'secret': secret,
        'qr_svg': totp_qr_svg(secret, request.user),
        'error': error,
    })


@require_http_methods(['GET', 'POST'])
def verify_2fa_view(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return redirect('/admin/login/')
    if not request.session.get('twofa_pending'):
        return redirect('/admin/')
    # La 2FA a été désactivée ailleurs pendant que la session attendait : on débloque.
    if not getattr(request.user, 'totp_enabled', False):
        request.session['twofa_pending'] = False
        return redirect('/admin/')

    if request.method == 'POST':
        # Verrouillage anti brute-force : un attaquant ne doit pas pouvoir
        # essayer des codes à l'infini, même avec un mot de passe volé.
        remaining = totp_locked(request.user.username)
        if remaining:
            return _render(request, 'twofa_verify', {
                'error': True,
                'locked': True,
                'locked_minutes': max(1, (remaining // 60) + 1),
                'recovery_count': len(_recovery_list(request.user)),
            })

        code = (request.POST.get('code') or '').strip()
        valid = False
        secret = unobfuscate_totp_secret(getattr(request.user, 'totp_secret', ''))

        if request.POST.get('action') == 'recovery':
            hashed = _hash_recovery(code.upper())
            codes = _recovery_list(request.user)
            if hashed in codes:
                _save_recovery(request.user, [c for c in codes if c != hashed])
                valid = True
        elif verify_totp(secret, code):
            valid = True

        if valid:
            clear_totp_attempts(request.user.username)
            request.session['twofa_pending'] = False
            target = request.session.pop('twofa_next', None) or request.POST.get('next') or '/admin/'
            return redirect(_safe_next(request, target))
        record_totp_failed(request.user.username)
        return _render(request, 'twofa_verify', {
            'error': True,
            'recovery_count': len(_recovery_list(request.user)),
        })

    return _render(request, 'twofa_verify', {
        'recovery_count': len(_recovery_list(request.user)),
    })


@login_required
def disable_2fa_view(request):
    if not getattr(request.user, 'totp_enabled', False):
        return redirect(reverse('auth-account'))
    if request.method == 'POST':
        password = request.POST.get('password', '')
        if request.user.check_password(password):
            request.user.totp_enabled = False
            request.user.totp_secret = ''
            request.user.save(update_fields=['totp_enabled', 'totp_secret'])
            _save_recovery(request.user, [])
            return redirect(reverse('auth-message') + '?kind=2fa_disabled')
        return _render(request, 'twofa_disable', {'error': 'Mot de passe incorrect.'})
    return _render(request, 'twofa_disable', {})


# ---------------------------------------------------------------------------
# Espace « Sécurité du compte »
# ---------------------------------------------------------------------------

@login_required
def account_security_view(request):
    user = request.user
    sessions = []
    store = SessionStore
    for raw in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        try:
            data = store(raw.session_key).load()
        except Exception:  # noqa: BLE001 — sessions illisibles ignorées
            continue
        if str(data.get('_auth_user_id', '')) != str(user.pk):
            continue
        sessions.append({
            'key': raw.session_key,
            'expire_date': raw.expire_date,
            'login_at': data.get('login_at'),
            'device': data.get('device') or 'Appareil inconnu',
            'ip': data.get('ip') or '',
            'current': raw.session_key == request.session.session_key,
        })
    sessions.sort(key=lambda s: (s['current'] is False, s['login_at'] or 0))
    return _render(request, 'security', {
        'sessions': sessions,
        'events': user.connexions.all()[:15],
        'recovery_count': len(_recovery_list(user)),
    })


def _revoke(user, session_keys=None, *, exclude=None):
    store = SessionStore
    for raw in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if exclude and raw.session_key == exclude:
            continue
        if session_keys and raw.session_key not in session_keys:
            continue
        try:
            data = store(raw.session_key).load()
        except Exception:  # noqa: BLE001
            continue
        if str(data.get('_auth_user_id', '')) == str(user.pk):
            raw.delete()


@login_required
@require_http_methods(['POST'])
def logout_others_view(request):
    _revoke(request.user, exclude=request.session.session_key)
    return redirect(reverse('auth-account'))


@login_required
@require_http_methods(['POST'])
def revoke_session_view(request, session_key):
    if session_key != request.session.session_key:
        _revoke(request.user, [session_key])
    return redirect(reverse('auth-account'))


# ---------------------------------------------------------------------------
# Messages génériques
# ---------------------------------------------------------------------------

_MESSAGES = {
    'magic_sent': {
        'icon': 'fa-envelope-open-text', 'titre': 'Lien de connexion envoyé',
        'message': 'Vérifiez votre boîte mail : un lien de connexion sans mot de passe vous attend. Il expire dans 10 minutes.',
        'action': 'Retour à la connexion', 'url': '/admin/login/',
    },
    'magic_invalid': {
        'icon': 'fa-link-slash', 'titre': 'Lien invalide ou expiré',
        'message': 'Ce lien de connexion ne peut plus être utilisé. Demandez-en un nouveau ou connectez-vous normalement.',
        'action': 'Se connecter', 'url': '/admin/login/',
    },
    '2fa_enabled': {
        'icon': 'fa-shield-halved', 'titre': 'Double authentification activée',
        'message': 'Votre compte est maintenant protégé par un code à 6 chiffres renouvelé toutes les 30 secondes.',
        'action': 'Espace sécurité', 'url': '/admin/account/',
    },
    '2fa_disabled': {
        'icon': 'fa-shield', 'titre': 'Double authentification désactivée',
        'message': 'Votre compte n’exige plus de code à chaque connexion. Pensez à un mot de passe fort.',
        'action': 'Espace sécurité', 'url': '/admin/account/',
    },
    'signup_disabled': {
        'icon': 'fa-ban', 'titre': 'Inscription désactivée',
        'message': 'Les inscriptions sont momentanément fermées. Contactez un administrateur pour créer un compte.',
        'action': 'Retour à la connexion', 'url': '/admin/login/',
    },
    'password_ok': {
        'icon': 'fa-key', 'titre': 'Mot de passe réinitialisé',
        'message': 'Vous pouvez maintenant vous connecter avec votre nouveau mot de passe.',
        'action': 'Se connecter', 'url': '/admin/login/',
    },
}


def _message_ctx(kind):
    info = _MESSAGES[kind]
    return {
        'kind': kind,
        'msg_icon': info['icon'],
        'msg_title': info['titre'],
        'msg_body': info['message'],
        'msg_action': info.get('action', ''),
        'msg_url': info.get('url', ''),
    }


@require_http_methods(['GET'])
def message_view(request):
    kind = request.GET.get('kind', 'magic_sent')
    if kind not in _MESSAGES:
        kind = 'magic_sent'
    context = _message_ctx(kind)
    codes = request.session.pop('recovery_codes_display', None)
    if kind == '2fa_enabled' and codes:
        context['recovery_codes_view'] = codes
    return _render(request, 'message', context)