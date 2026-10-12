"""Endpoints API d'authentification pour les clients (SPA / Angular, POS).

Complètent le login JWT existant avec : inscription locale, vérification
d'e-mail par code, réinitialisation de mot de passe, connexion par lien
magique et login conscient de la double authentification (TOTP).
"""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.models import User
from apps.accounts.serializers import (
    ForgotSerializer,
    MagicLinkSerializer,
    RegisterSerializer,
    RegisterVerifySerializer,
    ResetSerializer,
    UserSerializer,
    WineTokenObtainPairSerializer,
)
from apps.accounts.services import (
    magic_link_token,
    send_email_quiet,
    send_otp_email,
    TooSoonOTP,
    verify_otp,
)
from apps.accounts.services.email_service import raison_echec_email

UserModel = get_user_model()


def _tokens(user):
    refresh = RefreshToken.for_user(user)
    return {
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': UserSerializer(user).data,
    }


# ---------------------------------------------------------------------------
# Inscription
# ---------------------------------------------------------------------------

class RegisterView(APIView):
    """POST /api/auth/register/ — création de compte locale.

    Corps : {username, email, first_name?, last_name?, password}.
    Le compte est créé inactif ; un code de vérification part par e-mail.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        if not getattr(settings, 'AUTH_SIGNUP_ENABLED', True):
            return Response({'detail': 'L’inscription est désactivée.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User(
            username=data['username'],
            email=data['email'],
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            role=User.Role.VENDEUR,
            is_active=False,
            is_staff=getattr(settings, 'SIGNUP_STAFF', False),
        )
        user.set_password(data['password'])
        user.save()

        try:
            envoye = send_otp_email(data['email'], purpose='verify', titre="Votre code de vérification LAZAN'I BETSILEO")
        except TooSoonOTP as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        if not envoye:
            # Aucune vérification ne partira : on annule la création pour que
            # l'utilisateur puisse réessayer avec le même e-mail/identifiant.
            user.delete()
            return Response(
                {'detail': raison_echec_email()},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({
            'detail': 'Compte créé. Un code de vérification vient d’être envoyé par e-mail.',
            'email': data['email'],
        }, status=status.HTTP_201_CREATED)


class RegisterVerifyView(APIView):
    """POST /api/auth/register/verify/ — confirme l'e-mail et active le compte.

    Corps : {email, code}. Renvoie la paire JWT (étape de connexion inutile).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()

        user = User.objects.filter(email__iexact=email).first()
        if user is None or user.is_active:
            return Response({'detail': 'Code invalide ou expiré.'}, status=status.HTTP_400_BAD_REQUEST)
        if not verify_otp(email, 'verify', serializer.validated_data['code']):
            return Response({'detail': 'Code invalide ou expiré.'}, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = True
        user.is_staff = getattr(settings, 'SIGNUP_STAFF', False)
        user.save(update_fields=['is_active', 'is_staff'])
        return Response(_tokens(user))


# ---------------------------------------------------------------------------
# Mot de passe oublié
# ---------------------------------------------------------------------------

class ForgotPasswordView(APIView):
    """POST /api/auth/forgot/ — envoie un code de réinitialisation par e-mail.

    La réponse est identique que le compte existe ou non (anti-fuites).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()

        user = User.objects.filter(email__iexact=email).first()
        titre = "Votre code de réinitialisation LAZAN'I BETSILEO"
        try:
            # Le code est émis même pour un e-mail inconnu (tempo & anti-fuites) ;
            # l'e-mail n'est expédié que si le compte existe.
            send_otp_email(email, purpose='reset', titre=titre)
        except TooSoonOTP:
            return Response({'detail': 'Un code a déjà été envoyé récemment.'}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        return Response({'detail': 'Si un compte existe avec cet e-mail, un code vient d’être envoyé.'})


class ResetPasswordView(APIView):
    """POST /api/auth/reset/ — valide le code et définit un nouveau mot de passe."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user is None or not verify_otp(email, 'reset', serializer.validated_data['code']):
            return Response({'detail': 'Code invalide ou expiré.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data['password'])
        user.save(update_fields=['password'])
        return Response({'detail': 'Mot de passe réinitialisé. Vous pouvez vous connecter.'})


# ---------------------------------------------------------------------------
# Connexion par lien magique (e-mail)
# ---------------------------------------------------------------------------

class MagicLinkRequestView(APIView):
    """POST /api/auth/magic-link/ — envoie un lien de connexion sans mot de passe."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MagicLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user is not None:
            token = magic_link_token(user)
            link = request.build_absolute_uri(f'/admin/magic-link/{token}/')
            send_email_quiet(
                "Votre lien de connexion LAZAN'I BETSILEO",
                email,
                'magic_link',
                context={'prenom': user.first_name or user.username, 'link': link},
            )
        return Response({'detail': 'Si un compte existe avec cet e-mail, un lien de connexion vient d’être envoyé.'})


# ---------------------------------------------------------------------------
# Login JWT conscient de la double authentification
# ---------------------------------------------------------------------------

class WineTokenObtainPairView(TokenObtainPairView):
    """POST /api/auth/login/ — identique à avant, + champ ``totp`` si 2FA activée."""
    serializer_class = WineTokenObtainPairSerializer