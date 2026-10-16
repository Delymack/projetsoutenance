"""Services d'authentification de la cave.

Regroupe les briques réutilisables (« fonctionnalités au-delà de l'imagination ») :

  * code de vérification par e-mail (OTP à 6 chiffres, usage unique, TTL) ;
  * lien de connexion sans mot de passe (magic link, JWT à usage unique) ;
  * double authentification TOTP (RFC 6238 implémentée avec la bibliothèque
    standard — aucun paquet supplémentaire) + QR code SVG via segno ;
  * verrouillage de compte après échecs répétés (cache) ;
  * identification de l'appareil / de l'IP à partir de la requête ;
  * envoi d'e-mails robuste (console en développement, SMTP en production).
"""
import base64
import hashlib
import hmac
import logging
import re
import secrets
import struct
import time
from urllib.parse import quote

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from django.core.mail import mailers
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import LoginEvent, User
from apps.parametres.services import get_param

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Appareil & IP
# ---------------------------------------------------------------------------

_UA_RE = {
    'firefox': r'Firefox/(\d+)',
    'chrome': r'Chrome/(\d+)',
    'edge': r'Edg(?:e|A|iOS)?/(\d+)',
    'safari': r'Version/([\d.]+).*Safari/',
    'opera': r'OPR/(\d+)',
}


def client_ip(request):
    """Adresse IP du client (compatible derrière un proxy de confiance)."""
    if request is None:
        return '127.0.0.1'
    fwd = getattr(request, 'META', {}).get('HTTP_X_FORWARDED_FOR')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or '127.0.0.1'


def device_label(user_agent):
    """Libellé court d’un appareil à partir du User-Agent.

    Ex. « Chrome · 122 · Windows » / « Safari · Mobile · iPhone ».
    """
    ua = (user_agent or '')
    navigator = 'Navigateur'
    version = ''
    for name, pattern in _UA_RE.items():
        match = re.search(pattern, ua, re.IGNORECASE)
        if match:
            navigator = name.capitalize()
            version = match.group(1)
            break
    os_label = 'Inconnu'
    if 'Windows' in ua:
        os_label = 'Windows'
    elif 'Android' in ua:
        os_label = 'Android'
    elif 'iPhone' in ua or 'iPad' in ua or 'iOS' in ua:
        os_label = 'iOS'
    elif 'Mac OS X' in ua or 'Macintosh' in ua:
        os_label = 'macOS'
    elif 'CrOS' in ua:
        os_label = 'ChromeOS'
    elif 'Linux' in ua:
        os_label = 'Linux'
    label = f"{navigator} · {version} · {os_label}" if version else f"{navigator} · {os_label}"
    if 'Mobile' in ua or 'iPhone' in ua or 'Android' in ua:
        label += ' · Mobile'
    return label[:120]


def device_fingerprint(user_agent, ip):
    h = hashlib.sha256()
    h.update((user_agent or '').encode('utf-8', 'ignore'))
    h.update(b'|')
    h.update((ip or '').encode('utf-8', 'ignore'))
    return h.hexdigest()


# ---------------------------------------------------------------------------
# E-mails
# ---------------------------------------------------------------------------

def send_email_quiet(subject, to, template, context=None):
    """Envoie un e-mail riche (HTML + texte). Ne lève jamais d'exception.

    Le canal réel est l'API Resend (``RESEND_API_KEY``) — le même que
    l'inscription du frontend. En développement sans ``OTP_ENVOI_REEL`` et dans
    la suite de tests, on retombe sur le mailer Django (console / boîte de test
    locmem), afin de ne jamais émettre de trafic réseau pendant les tests.
    """
    if not to:
        return False
    context = context or {}
    try:
        body_txt = render_to_string(f'admin/auth/emails/{template}.txt', context)
        body_html = render_to_string(f'admin/auth/emails/{template}.html', context)
    except Exception as exc:  # noqa: BLE001 — ne jamais bloquer la connexion pour un e-mail
        logger.warning('Rendu de l’e-mail impossible (%s) : %s', subject, exc)
        return False

    from .email_service import envoi_reel_autorise, envoyer_email_html

    if envoi_reel_autorise():
        ok, detail = envoyer_email_html(subject, to, body_txt, body_html)
        if not ok:
            logger.error('Envoi de l’e-mail impossible (%s) : %s', subject, detail)
        return ok

    # Développement / tests : mailer Django (console ou boîte de test locmem).
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or "LAZAN'I BETSILEO <no-reply@lazani-betsileo.mg>"
        msg = EmailMultiAlternatives(subject, body_txt, from_email, [to])
        msg.attach_alternative(body_html, 'text/html')
        mailers['default'].send_messages([msg])
        return True
    except Exception as exc:  # noqa: BLE001 — ne jamais bloquer la connexion pour un e-mail
        logger.warning('Envoi d’e-mail impossible (%s) : %s', subject, exc)
        return False


# ---------------------------------------------------------------------------
# OTP e-mail (vérification à 6 chiffres)
# ---------------------------------------------------------------------------

OTP_MAX_ATTEMPTS = 5


def _otp_key(email, purpose):
    return f'auth:otp:{purpose}:{_normalize(email)}'


def _otp_attempts_key(email, purpose):
    return f'auth:otp:attempts:{purpose}:{_normalize(email)}'


def generate_otp():
    return f'{secrets.randbelow(1000000):06d}'


def send_otp_email(email, purpose='verify', titre=None):
    """Émet un code à 6 chiffres et l’envoie par e-mail.

    Usage unique, TTL configurable (AUTH_OTP_TTL). Les codes précédents sont
    invalidés à chaque nouvel envoi. Retourne ``True`` si envoyé.
    """
    email = _normalize(email)
    ttl = getattr(settings, 'AUTH_OTP_TTL', 600)
    resend = getattr(settings, 'AUTH_OTP_RESEND_SECONDS', 90)

    sent_at = cache.get(f'otp:sent:{email}:{purpose}', 0)
    remaining = resend - (int(time.time()) - int(sent_at))
    if remaining > 0:
        raise TooSoonOTP(remaining)

    code = generate_otp()
    expires = timezone.now() + timezone.timedelta(seconds=ttl)
    cache.set(_otp_key(email, purpose), _hash_otp(code), timeout=ttl)
    cache.set(f'otp:sent:{email}:{purpose}', int(time.time()), timeout=resend)

    titre = titre or ('Votre code de vérification' if purpose != 'reset' else 'Votre code de réinitialisation')
    linked_user = User.objects.filter(email__iexact=email).first()
    prenom = (linked_user.first_name or linked_user.username if linked_user else '')
    envoye = send_email_quiet(
        f'{titre} · {code}',
        email,
        'otp',
        context={'code': code, 'expires': ttl // 60, 'prenom': prenom, 'purpose': purpose},
    )
    if not envoye:
        # L'e-mail n'est pas parti : on libère le code et le délai anti-spam
        # pour qu'une nouvelle tentative soit possible immédiatement.
        cache.delete(_otp_key(email, purpose))
        cache.delete(f'otp:sent:{email}:{purpose}')
        return False
    return code


def verify_otp(email, purpose, code):
    """Vérifie un code OTP (usage unique).

    Le code n'est consommé que s'il est EXACT : une erreur de saisie n'invalide
    plus le code à elle seule (limité à ``OTP_MAX_ATTEMPTS`` tentatives pour
    borner le brute-force par la fenêtre de validité).
    """
    email = _normalize(email)
    key = _otp_key(email, purpose)
    stored = cache.get(key)
    if not stored:
        return False
    if hmac.compare_digest(str(stored), _hash_otp(code or '')):
        cache.delete(key)
        cache.delete(_otp_attempts_key(email, purpose))
        return True

    attempts_key = _otp_attempts_key(email, purpose)
    attempts = int(cache.get(attempts_key, 0) or 0) + 1
    ttl = getattr(settings, 'AUTH_OTP_TTL', 600)
    if attempts >= OTP_MAX_ATTEMPTS:
        cache.delete(key)
        cache.delete(attempts_key)
    else:
        cache.set(attempts_key, attempts, timeout=ttl)
    return False


def _hash_otp(code):
    return hashlib.sha256(f'{code}:{settings.SECRET_KEY}:wineadmin-otp'.encode()).hexdigest()


def _normalize(value):
    return (value or '').strip().lower()


class TooSoonOTP(Exception):
    """Nouveau code déjà envoyé récemment (cooldown)."""

    def __init__(self, remaining):
        self.remaining = remaining
        super().__init__(_('Nouveau code déjà envoyé, réessayez d’ici quelques secondes.'))


# ---------------------------------------------------------------------------
# Lien magique (connexion sans mot de passe)
# ---------------------------------------------------------------------------

def magic_link_token(user):
    """Jeton JWT de connexion sans mot de passe, à usage unique, TTL court."""
    import jwt

    nonce = secrets.token_urlsafe(24)
    payload = {
        'uid': str(user.pk),
        'purpose': 'magic-link',
        'jti': nonce,
        'iat': int(time.time()),
        'exp': int(time.time()) + getattr(settings, 'AUTH_MAGIC_LINK_TTL', 600),
    }
    cache.set(f'auth:magic:{nonce}', str(user.pk), timeout=getattr(settings, 'AUTH_MAGIC_LINK_TTL', 600))
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def magic_link_user(token):
    """Vérifie le lien magique (signature + usage unique) et renvoie l'utilisateur."""
    import jwt

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        if payload.get('purpose') != 'magic-link':
            return None
        nonce = payload.get('jti')
        if not cache.get(f'auth:magic:{nonce}'):
            return None
        user = User.objects.filter(pk=payload.get('uid'), is_active=True).first()
        if user is None:
            return None
        cache.delete(f'auth:magic:{nonce}')
        return user
    except Exception:  # noqa: BLE001 — jetons invalides/expirés ignorés
        return None


# ---------------------------------------------------------------------------
# Double authentification TOTP (RFC 6238, bibliothèque standard)
# ---------------------------------------------------------------------------

def totp_new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def totp_provisioning_uri(secret, user):
    issuer = getattr(settings, 'SOCIALAUTH_ISSUER', None) or "LAZAN'I BETSILEO"
    account = f"{user.get_full_name() or user.username} ({user.email})"
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"


def totp_qr_svg(secret, user):
    """QR code (SVG) de la clé de double authentification, via segno."""
    import segno

    uri = totp_provisioning_uri(secret, user)
    qr = segno.make(uri, error='m')
    return qr.svg_inline(scale=4, dark='#2b1b20', light='#ffffff')


def totp_current_code(secret, at=None):
    """Calcule le code TOTP courant (utile pour les tests)."""
    key = _b32_decode(secret)
    counter = int(at if at is not None else time.time()) // 30
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f'{code:06d}'


def verify_totp(secret, code, drift=1):
    if not secret or not code or not code.isdigit() or len(code) != 6:
        return False
    for delta in range(-drift, drift + 1):
        at = int(time.time()) + delta * 30
        if hmac.compare_digest(totp_current_code(secret, at), code):
            return True
    return False


def _b32_decode(value):
    value = (value or '').upper().strip().replace(' ', '').replace('-', '')
    padding = 8 - (len(value) % 8)
    if padding != 8:
        value += '=' * padding
    return base64.b32decode(value, casefold=True)


def obfuscate_totp_secret(secret):
    if not secret:
        return ''
    key = _derive_totp_key()
    raw = secret.encode('utf-8')
    return base64.b64encode(bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))).decode()


def unobfuscate_totp_secret(stored):
    if not stored:
        return ''
    try:
        key = _derive_totp_key()
        raw = base64.b64decode(stored.encode('utf-8'))
        return bytes(b ^ key[i % len(key)] for i, b in enumerate(raw)).decode('utf-8')
    except Exception:  # noqa: BLE001
        return ''


def _derive_totp_key():
    return hashlib.pbkdf2_hmac(
        'sha256', settings.SECRET_KEY.encode('utf-8'), b'wineadmin-totp-v1', 50000, dklen=16
    )


# ---------------------------------------------------------------------------
# Verrouillage de compte après échecs répétés
# ---------------------------------------------------------------------------

def _lock_key(identifier):
    return f'auth:pass:{_normalize(identifier) or "?"}'


def record_failed_attempt(identifier):
    """Compte un échec. Renvoie ``True`` si le compte vient d'être verrouillé.

    Anti-DoS : un verrouillage déjà actif n'est JAMAIS prolongé par de nouvelles
    tentatives — il expire toujours à l'heure initialement prévue.
    """
    identifier = _normalize(identifier) or '?'
    max_attempts = int(get_param('securite_verrouillage_essais', getattr(settings, 'LOGIN_MAX_ATTEMPTS', 5)))
    window_min = int(get_param('securite_verrouillage_duree', getattr(settings, 'LOGIN_LOCKOUT_MINUTES', 15)))
    window = window_min * 60

    key = _lock_key(identifier)
    now = int(time.time())
    data = cache.get(key)
    locked_until = data.get('locked_until', 0) if data else 0
    if locked_until > now:
        return True, locked_until
    if not data or data['first'] < now - window:
        data = {'count': 0, 'first': now}
    data['count'] += 1

    locked = data['count'] >= max_attempts
    if locked:
        until = now + window
        data['locked_until'] = until
        cache.set(key, data, timeout=window + 60)
        return True, until
    cache.set(key, data, timeout=window + 60)
    return False, 0


def is_locked(identifier):
    identifier = _normalize(identifier) or '?'
    data = cache.get(_lock_key(identifier))
    if not data:
        return 0
    until = data.get('locked_until', 0)
    return max(until - int(time.time()), 0)


def clear_attempts(identifier):
    identifier = _normalize(identifier) or '?'
    cache.delete(_lock_key(identifier))


def _totp_lock_key(identifier):
    return f'auth:totp:{_normalize(identifier) or "?"}'


def record_totp_failed(identifier, max_attempts=5, window_min=15):
    """Compte un échec TOTP (2FA). Indépendant du verrouillage du mot de passe,
    mais bloque le code de seconde étape après ``max_attempts`` échecs.

    Anti-DoS : un verrouillage déjà actif n'est jamais prolongé.
    """
    identifier = _normalize(identifier) or '?'
    now = int(time.time())
    window = window_min * 60
    key = _totp_lock_key(identifier)
    data = cache.get(key)
    locked_until = data.get('locked_until', 0) if data else 0
    if locked_until > now:
        return True, locked_until
    if not data or data['first'] < now - window:
        data = {'count': 0, 'first': now}
    data['count'] += 1

    locked = data['count'] >= max_attempts
    if locked:
        until = now + window
        data['locked_until'] = until
        cache.set(key, data, timeout=window + 60)
        return True, until
    cache.set(key, data, timeout=window + 60)
    return False, 0


def totp_locked(identifier):
    """Secondes restantes avant déverrouillage TOTP (0 = non verrouillé)."""
    identifier = _normalize(identifier) or '?'
    data = cache.get(_totp_lock_key(identifier))
    if not data:
        return 0
    until = data.get('locked_until', 0)
    return max(until - int(time.time()), 0)


def clear_totp_attempts(identifier):
    identifier = _normalize(identifier) or '?'
    cache.delete(_totp_lock_key(identifier))


def lockout_info(identifier):
    """Infos de verrouillage pour l'affichage (secondes restantes)."""
    remaining = is_locked(identifier)
    if not remaining:
        return {'locked': False}
    return {
        'locked': True,
        'remaining': remaining,
        'minutes': max(1, int(remaining // 60) + (1 if remaining % 60 else 0)),
    }


# ---------------------------------------------------------------------------
# Recherche d'utilisateur partagée
# ---------------------------------------------------------------------------

def find_user(identifier):
    """Retrouve un compte par identifiant de connexion (nom d'utilisateur ou e-mail).

    Ne résout JAMAIS un identifiant purement numérique comme une clé primaire :
    sinon un identifiant comme « 42 » pourrait désigner un autre compte et
    court-circuiter les contrôles associés (verrouillage, double authentification).
    """
    if not identifier:
        return None
    value = identifier.strip()
    if not value:
        return None
    return (
        User.objects.filter(username__iexact=value).first()
        or User.objects.filter(email__iexact=value).first()
    )


# ---------------------------------------------------------------------------
# Alertes de sécurité
# ---------------------------------------------------------------------------

def send_new_device_alert(user, request, appareil, event):
    """Alerte e-mail si la connexion vient d'un appareil jamais vu.

    On compare la dernière connexion réussie précédente : si l'adresse IP et
    l'appareil diffèrent, c'est probablement un nouveau terminal → alerte.
    """
    ip = client_ip(request)
    prior = user.connexions.filter(statut=LoginEvent.Statut.SUCCESS, pk__lt=event.pk).first()
    if prior is None:
        return False
    if prior.ip == ip and prior.appareil == appareil:
        return False
    send_email_quiet(
        'Nouvelle connexion détectée sur votre compte',
        user.email,
        'login_alert',
        context={'prenom': user.first_name or user.username, 'appareil': appareil, 'ip': ip},
    )
    return True
