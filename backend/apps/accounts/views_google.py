"""Authentification par « Google Account » côté API (SPA / POS).

Le client envoie l'id_token obtenu via Google Identity Services
(google.accounts.id.initialize + credential). Ce module vérifie la signature
du jeton contre les clés publiques de Google (https://www.googleapis.com/...),
puis mappe ou crée l'utilisateur avec les mêmes règles de sécurité que
l'adaptateur allauth (liste blanche d'emails / domaines).
"""
import re

from django.conf import settings
import jwt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.accounts.serializers import UserSerializer
from apps.accounts.services import (
    clear_totp_attempts,
    record_totp_failed,
    totp_locked,
    unobfuscate_totp_secret,
    verify_totp,
)

GOOGLE_JWKS_URL = 'https://www.googleapis.com/oauth2/v3/certs'
GOOGLE_ISSUERS = ('accounts.google.com', 'https://accounts.google.com')

_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True)
    return _jwks_client


def verify_google_id_token(id_token):
    """Vérifie et décode un id_token Google. Retourne les claims, sinon None."""
    if not id_token:
        return None
    client_id = settings.GOOGLE_OAUTH2_CLIENT_ID
    if not client_id:
        return None
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=['RS256'],
            audience=client_id,
            options={'verify_aud': True, 'require': ['exp', 'sub', 'email']},
        )
    except Exception:
        return None
    if claims.get('iss') not in GOOGLE_ISSUERS:
        return None
    if not claims.get('email'):
        return None
    if claims.get('email_verified') is True:
        return claims
    return None


def build_username(email):
    base = re.sub(r'[^\w@.+-]', '_', (email or '').split('@')[0])[:30] or 'google'
    username = base
    n = 1
    while User.objects.filter(username__iexact=username).exists():
        n += 1
        username = f"{base[:24]}{n}"
    return username


def google_user_from_claims(claims):
    """Retourne l'utilisateur lié à l'email Google (création si autorisée)."""
    email = claims['email'].strip().lower()
    domain = email.split('@')[-1]
    allowed_emails = [e.lower() for e in settings.GOOGLE_ALLOWED_EMAILS if e]
    allowed_domains = [d.lower() for d in settings.GOOGLE_ALLOWED_DOMAINS if d]
    restricted = bool(allowed_emails or allowed_domains)
    allowed = (
        (not restricted)
        or domain in allowed_domains
        or email in allowed_emails
    )

    user = User.objects.filter(email__iexact=email).first()
    if user is None and not allowed:
        raise PermissionError(
            f"L'adresse {email} n'est pas autorisée à se connecter."
        )

    if user is None:
        user = User(
            username=build_username(email),
            email=email,
            first_name=claims.get('given_name', ''),
            last_name=claims.get('family_name', ''),
            avatar_url=claims.get('picture', ''),
            google_uid=claims.get('sub', ''),
            role=User.Role.VENDEUR,
            is_staff=getattr(settings, 'GOOGLE_STAFF', False),
        )
        user.set_unusable_password()
        user.save()
    else:
        changes = {}
        if claims.get('picture'):
            changes['avatar_url'] = claims['picture']
        if claims.get('sub'):
            changes['google_uid'] = claims['sub']
        if claims.get('given_name'):
            changes['first_name'] = claims['given_name']
        if claims.get('family_name'):
            changes['last_name'] = claims['family_name']
        if changes:
            User.objects.filter(pk=user.pk).update(**changes)
    return user


class GoogleAuthView(APIView):
    """
    POST /api/auth/google/

    Corps : {"id_token": "eyJhbGciOi..."}  (jeton Google Identity Services)

    Si l'email est autorisé (ou déjà connu), renvoie la paire JWT du projet
    (access + refresh) accompagnée des informations de l'utilisateur.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.GOOGLE_OAUTH2_CLIENT_ID:
            return Response(
                {'detail': 'La connexion Google n\'est pas configurée sur le serveur.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        id_token = request.data.get('id_token')
        claims = verify_google_id_token(id_token)
        if not claims:
            return Response(
                {'detail': 'Jeton Google invalide ou expiré.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            user = google_user_from_claims(claims)
        except PermissionError as exc:
            return Response(
                {'detail': str(exc)},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not user.is_active:
            return Response(
                {'detail': 'Ce compte est désactivé.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # La 2FA ne doit pas être contournée par un id_token Google : si le
        # compte est protégé, un code TOTP valide est exigé (champ ``totp``),
        # avec le même verrouillage anti brute-force que /api/auth/login/.
        if getattr(user, 'totp_enabled', False):
            remaining = totp_locked(user.username)
            if remaining:
                return Response(
                    {'detail': f'Trop de tentatives de code de double authentification. '
                               f'Réessayez dans {max(1, (remaining // 60) + 1)} minute(s).'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            provided = request.data.get('totp', '')
            secret = getattr(user, 'totp_secret', '')
            if not provided or not verify_totp(unobfuscate_totp_secret(secret), provided):
                record_totp_failed(user.username)
                return Response(
                    {'detail': 'Double authentification requise : fournissez un code TOTP valide dans le champ "totp".'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            clear_totp_attempts(user.username)

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        })