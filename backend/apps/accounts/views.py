# backend/apps/accounts/views.py
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import VerificationCode
from .serializers import (
    LoginSendCodeSerializer,
    LoginVerifySerializer,
    ResendCodeSerializer,
    SignupSendCodeSerializer,
    SignupVerifySerializer,
    UserSerializer,
)
from .services import (
    clear_totp_attempts,
    record_totp_failed,
    totp_locked,
    unobfuscate_totp_secret,
    verify_totp,
)
from .services.email_service import raison_echec_email, send_verification_email
from .services.sms_service import send_verification_sms
from .utils import generate_code

User = get_user_model()


def envoyer_code(contact, code, contact_type, purpose):
    """Envoie le code de vérification au contact (e-mail ou SMS)."""
    if contact_type == 'email':
        return send_verification_email(contact, code, purpose)
    return send_verification_sms(contact, code, purpose)


def erreur_envoi(contact_type):
    """Raison affichée au client quand le prestataire n'a pas accepté l'envoi."""
    if contact_type == 'email':
        return raison_echec_email()
    return ("Envoi du SMS impossible : clé API eSMS Africa invalide/expirée, "
            "solde épuisé ou sender ID non approuvé (voir le journal du serveur "
            "pour le détail).")


def code_en_attente(contact, purpose):
    """Dernier code non utilisé pour ce contact, ou ``None``.

    On utilise ``first()`` (et non ``get()``) : d'anciens doublons ne doivent
    jamais provoquer une erreur 500 ``MultipleObjectsReturned``.
    """
    return (
        VerificationCode.objects
        .filter(contact=contact, purpose=purpose, is_used=False)
        .order_by('-created_at')
        .first()
    )


def secondes_restantes(vc):
    """Secondes avant expiration du code (0 si déjà expiré)."""
    return max(0, int((vc.expires_at - timezone.now()).total_seconds()))


class SignupSendCodeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if not getattr(settings, 'AUTH_SIGNUP_ENABLED', True):
            return Response({'error': "L'inscription est désactivée."},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = SignupSendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        contact = data['contact']

        # Anti-spam : un code émis il y a moins d'une minute n'est pas réémis.
        # L'utilisateur le reçoit une seule fois et utilise « Renvoyer le code »
        # si nécessaire (le renvoi est lui-même soumis au délai de 60 s).
        en_attente = code_en_attente(contact, VerificationCode.PURPOSE_SIGNUP)
        if en_attente and not en_attente.can_resend():
            return Response(
                {'message': 'Code déjà envoyé', 'expires_in': secondes_restantes(en_attente)},
                status=status.HTTP_200_OK,
            )

        # Supprimer les anciens codes non utilisés pour ce contact.
        VerificationCode.objects.filter(
            contact=contact, purpose=VerificationCode.PURPOSE_SIGNUP, is_used=False
        ).delete()

        code = generate_code()
        vc = VerificationCode.objects.create(
            contact=contact,
            contact_type=data['contact_type'],
            purpose=VerificationCode.PURPOSE_SIGNUP,
            user_data={
                'nom': data['nom'],
                'email': data.get('email', '').strip().lower() if data.get('email') else '',
                'telephone': data.get('contact') if data.get('contact_type') == 'sms' else data.get('telephone', ''),
                'password': make_password(data['password']),
            },
        )
        vc.set_code(code)

        if not envoyer_code(contact, code, data['contact_type'], VerificationCode.PURPOSE_SIGNUP):
            # L'envoi a échoué : on retire le code pour laisser réessayer tout de suite.
            vc.delete()
            return Response({'error': erreur_envoi(data['contact_type'])},
                            status=status.HTTP_502_BAD_GATEWAY)

        return Response({'message': 'Code envoyé', 'expires_in': secondes_restantes(vc)},
                        status=status.HTTP_200_OK)


class SignupVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = SignupVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact = serializer.validated_data['contact']
        code = serializer.validated_data['code']

        vc = code_en_attente(contact, VerificationCode.PURPOSE_SIGNUP)
        if vc is None:
            return Response({'error': 'Code invalide ou expiré'}, status=status.HTTP_400_BAD_REQUEST)

        if vc.is_blocked:
            return Response({'error': 'Trop de tentatives. Veuillez demander un nouveau code.'}, status=status.HTTP_400_BAD_REQUEST)
        if vc.is_expired:
            return Response({'error': 'Code expiré, veuillez en demander un nouveau.'}, status=status.HTTP_400_BAD_REQUEST)
        if not vc.verify_code(code):
            vc.increment_attempts()
            remaining = max(0, 5 - vc.attempts)
            return Response({'error': f'Code incorrect ({remaining} tentatives restantes)'}, status=status.HTTP_400_BAD_REQUEST)

        user_data = vc.user_data or {}
        # Normalise : l'inscription par SMS seul n'a pas d'e-mail (None, jamais
        # la chaîne vide — la colonne e-mail est unique).
        email = (user_data.get('email') or '').strip().lower()
        telephone = (user_data.get('telephone') or '').strip()

        # Contrôle de doublon ciblé : on n'interroge l'e-mail que s'il existe,
        # sinon ``filter(email='')`` bloquerait toute inscription SMS.
        deja_pris = (email and User.objects.filter(email__iexact=email).exists()) or (
            telephone and User.objects.filter(username=telephone).exists()
        )
        if deja_pris:
            vc.set_used()
            return Response({'error': 'Ce compte existe déjà'}, status=status.HTTP_400_BAD_REQUEST)

        nom = (user_data.get('nom') or '').strip()
        parties = nom.split(' ') if nom else []
        try:
            with transaction.atomic():
                user = User.objects.create(
                    username=telephone or email,
                    email=email or None,
                    first_name=parties[0] if parties else '',
                    last_name=' '.join(parties[1:]) if len(parties) > 1 else '',
                    password=user_data.get('password'),
                    telephone=telephone,
                    is_active=True,
                    # Inscription publique boutique : le compte créé est un client,
                    # pas un membre d'équipe (le défaut du modèle est VENDEUR).
                    role=User.Role.CLIENT,
                )
        except IntegrityError:
            # Course entre deux vérifications simultanées du même contact.
            vc.set_used()
            return Response({'error': 'Ce compte existe déjà'}, status=status.HTTP_400_BAD_REQUEST)

        vc.set_used()
        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'Inscription réussie',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }, status=status.HTTP_201_CREATED)


class LoginSendCodeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        contact = data['contact']

        en_attente = code_en_attente(contact, VerificationCode.PURPOSE_LOGIN)
        if en_attente and not en_attente.can_resend():
            return Response(
                {'message': 'Code déjà envoyé', 'expires_in': secondes_restantes(en_attente)},
                status=status.HTTP_200_OK,
            )

        VerificationCode.objects.filter(
            contact=contact, purpose=VerificationCode.PURPOSE_LOGIN, is_used=False
        ).delete()

        code = generate_code()
        vc = VerificationCode.objects.create(
            contact=contact,
            contact_type=data['contact_type'],
            purpose=VerificationCode.PURPOSE_LOGIN,
        )
        vc.set_code(code)

        if not envoyer_code(contact, code, data['contact_type'], VerificationCode.PURPOSE_LOGIN):
            vc.delete()
            return Response({'error': erreur_envoi(data['contact_type'])},
                            status=status.HTTP_502_BAD_GATEWAY)

        return Response({'message': 'Code envoyé', 'expires_in': secondes_restantes(vc)},
                        status=status.HTTP_200_OK)


class LoginVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact = serializer.validated_data['contact']
        code = serializer.validated_data['code']

        vc = code_en_attente(contact, VerificationCode.PURPOSE_LOGIN)
        if vc is None:
            return Response({'error': 'Code invalide ou expiré'}, status=status.HTTP_400_BAD_REQUEST)

        if vc.is_blocked:
            return Response({'error': 'Trop de tentatives. Veuillez demander un nouveau code.'}, status=status.HTTP_400_BAD_REQUEST)
        if vc.is_expired:
            return Response({'error': 'Code expiré, veuillez en demander un nouveau.'}, status=status.HTTP_400_BAD_REQUEST)
        if not vc.verify_code(code):
            vc.increment_attempts()
            remaining = max(0, 5 - vc.attempts)
            return Response({'error': f'Code incorrect ({remaining} tentatives restantes)'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email__iexact=contact) if '@' in contact else (User.objects.filter(username=contact).first() or User.objects.filter(telephone=contact).first())
        except User.DoesNotExist:
            vc.set_used()
            return Response({'error': 'Utilisateur introuvable'}, status=status.HTTP_400_BAD_REQUEST)

        if not user:
            vc.set_used()
            return Response({'error': 'Utilisateur introuvable'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_active:
            return Response({'error': 'Compte désactivé'}, status=status.HTTP_400_BAD_REQUEST)

        # Le code OTP ne remplace pas le second facteur : un compte protégé par
        # la 2FA doit fournir son code TOTP même en connexion par code.
        if getattr(user, 'totp_enabled', False):
            if totp_locked(user.username):
                return Response({
                    'error': 'Trop de tentatives de code de double authentification. Compte temporairement verrouillé.',
                    'totp_required': True,
                }, status=status.HTTP_400_BAD_REQUEST)
            provided_totp = serializer.validated_data.get('totp', '')
            if not provided_totp or not verify_totp(
                unobfuscate_totp_secret(user.totp_secret or ''), provided_totp
            ):
                record_totp_failed(user.username)
                return Response({
                    'error': 'Code de double authentification invalide ou manquant.',
                    'totp_required': True,
                }, status=status.HTTP_400_BAD_REQUEST)
            clear_totp_attempts(user.username)

        vc.set_used()
        refresh = RefreshToken.for_user(user)
        return Response({
            'message': 'Connexion réussie',
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class ResendCodeView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        contact = serializer.validated_data['contact']

        vc = VerificationCode.objects.filter(
            contact=contact, is_used=False
        ).order_by('-created_at').first()

        if not vc:
            return Response({'error': 'Aucun code en attente pour ce contact'}, status=status.HTTP_400_BAD_REQUEST)

        if not vc.can_resend():
            remaining = int(60 - (timezone.now() - vc.last_sent_at).total_seconds())
            return Response({'error': f'Veuillez attendre {remaining} secondes avant de renvoyer le code.'}, status=status.HTTP_400_BAD_REQUEST)

        code = generate_code()
        vc.set_code(code)

        if not envoyer_code(vc.contact, code, vc.contact_type, vc.purpose):
            return Response({'error': erreur_envoi(vc.contact_type)},
                            status=status.HTTP_502_BAD_GATEWAY)

        return Response({'message': 'Code renvoyé', 'expires_in': 600}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .serializers import UserSerializer

        return Response(UserSerializer(request.user).data)
