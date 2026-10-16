# backend/apps/accounts/serializers.py
import re

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import VerificationCode
from .services import (
    clear_totp_attempts,
    record_totp_failed,
    totp_locked,
    unobfuscate_totp_secret,
    verify_totp,
)

User = get_user_model()

PHONE_REGEX = re.compile(r'^(\+261|261)?[0-9]{9}$')


def normaliser_contact(contact: str) -> str:
    """
    Forme canonique d'un contact OTP.

    L'envoi stocke le contact normalisé (`+261XXXXXXXXX` ou e-mail en
    minuscules) : la vérification et le renvoi doivent produire exactement la
    même forme, sinon la recherche `VerificationCode.objects.get(contact=...)`
    échoue et « Code invalide ou expiré » s'affiche avec un code pourtant juste.
    """
    contact = (contact or '').strip()
    if '@' in contact:
        return contact.lower()
    if contact.startswith('261'):
        return '+' + contact
    if contact.startswith('+261'):
        return contact
    return '+261' + contact[-9:] if len(contact) >= 9 else contact


class SignupSendCodeSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=150, required=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    telephone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=True, min_length=8)
    contact_type = serializers.ChoiceField(choices=[('email', 'email'), ('sms', 'sms')])

    def validate_password(self, value):
        try:
            password_validation.validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate(self, attrs):
        contact_type = attrs.get('contact_type')
        email = attrs.get('email', '').strip()
        telephone = attrs.get('telephone', '').strip()
        nom = attrs.get('nom', '').strip()

        if not nom:
            raise serializers.ValidationError({"nom": "Le nom est obligatoire."})

        if contact_type == VerificationCode.CONTACT_EMAIL:
            if not email:
                raise serializers.ValidationError({"email": "L'email est obligatoire pour ce mode d'envoi."})
            try:
                EmailValidator()(email)
            except ValidationError:
                raise serializers.ValidationError({"email": "Format d'email invalide."})
            if User.objects.filter(email__iexact=email).exists():
                raise serializers.ValidationError({"email": "Un compte existe déjà avec cet email."})
            attrs['contact'] = email.lower()
        else:
            if not telephone:
                raise serializers.ValidationError({"telephone": "Le numéro de téléphone est obligatoire pour ce mode d'envoi."})
            if not PHONE_REGEX.match(telephone):
                raise serializers.ValidationError({"telephone": "Format de téléphone invalide. Utilisez un format +261XXXXXXXXX ou 261XXXXXXXXX."})
            # Normaliser
            if telephone.startswith('261'):
                telephone_norm = '+' + telephone
            elif telephone.startswith('+261'):
                telephone_norm = telephone
            else:
                telephone_norm = '+261' + telephone[-9:] if len(telephone) >= 9 else telephone
            attrs['contact'] = telephone_norm
            if User.objects.filter(username=telephone_norm).exists() or User.objects.filter(telephone=telephone_norm).exists():
                raise serializers.ValidationError({"telephone": "Un compte existe déjà avec ce numéro."})

        return attrs


class SignupVerifySerializer(serializers.Serializer):
    contact = serializers.CharField(max_length=150)
    code = serializers.CharField(max_length=6)

    def validate_contact(self, value):
        return normaliser_contact(value)

    def validate_code(self, value):
        if not value.isdigit() or len(value) != 6:
            raise serializers.ValidationError("Le code doit être composé de 6 chiffres.")
        return value


class LoginSendCodeSerializer(serializers.Serializer):
    contact = serializers.CharField(max_length=150)
    contact_type = serializers.ChoiceField(choices=[('email', 'email'), ('sms', 'sms')])

    def validate(self, attrs):
        contact = attrs.get('contact', '').strip()
        contact_type = attrs.get('contact_type')
        if not contact:
            raise serializers.ValidationError({"contact": "Ce champ est obligatoire."})

        if contact_type == VerificationCode.CONTACT_EMAIL:
            try:
                EmailValidator()(contact)
            except ValidationError:
                raise serializers.ValidationError({"contact": "Format d'email invalide."})
            if not User.objects.filter(email__iexact=contact).exists():
                raise serializers.ValidationError({"contact": "Aucun compte trouvé avec cet email."})
            attrs['contact'] = contact.lower()
        else:
            if not PHONE_REGEX.match(contact):
                raise serializers.ValidationError({"contact": "Format de téléphone invalide."})
            if contact.startswith('261'):
                contact_norm = '+' + contact
            elif contact.startswith('+261'):
                contact_norm = contact
            else:
                contact_norm = '+261' + contact[-9:] if len(contact) >= 9 else contact
            attrs['contact'] = contact_norm
            if not (User.objects.filter(username=contact_norm).exists() or User.objects.filter(telephone=contact_norm).exists()):
                raise serializers.ValidationError({"contact": "Aucun compte trouvé avec ce numéro."})
        return attrs


class LoginVerifySerializer(serializers.Serializer):
    contact = serializers.CharField(max_length=150)
    code = serializers.CharField(max_length=6)
    # Second facteur exigé uniquement si le compte a activé la 2FA.
    totp = serializers.CharField(max_length=6, required=False, allow_blank=True)

    def validate_contact(self, value):
        return normaliser_contact(value)

    def validate_code(self, value):
        if not value.isdigit() or len(value) != 6:
            raise serializers.ValidationError("Le code doit être composé de 6 chiffres.")
        return value


class ResendCodeSerializer(serializers.Serializer):
    contact = serializers.CharField(max_length=150)

    def validate_contact(self, value):
        return normaliser_contact(value)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'telephone', 'role', 'is_active']
        read_only_fields = ['id']


class RegisterSerializer(serializers.Serializer):
    """Inscription locale (identifiant + e-mail + mot de passe)."""

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value.strip()).exists():
            raise serializers.ValidationError('Ce nom d’utilisateur est déjà pris.')
        return value.strip()

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError('Un compte existe déjà avec cet e-mail.')
        return email

    def validate_password(self, value):
        try:
            password_validation.validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class RegisterVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)

    def validate_code(self, value):
        return value.strip()


class ForgotSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_code(self, value):
        return value.strip()

    def validate_password(self, value):
        try:
            password_validation.validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class MagicLinkSerializer(serializers.Serializer):
    email = serializers.EmailField()


class WineTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login JWT conscient de la double authentification (TOTP)."""

    totp = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate(self, attrs):
        # Le mot de passe est authentifié D'ABORD : le contrôle TOTP ne doit
        # porter que sur l'utilisateur réellement authentifié. Sinon un
        # identifiant (notamment numérique) pourrait désigner un autre compte
        # et court-circuiter l'exigence de double authentification.
        data = super().validate(attrs)
        user = self.user
        if getattr(user, 'totp_enabled', False):
            username = user.username
            if totp_locked(username):
                raise serializers.ValidationError({
                    'totp': 'Trop de tentatives de code de double authentification. Compte temporairement verrouillé.',
                })
            provided = attrs.get('totp', '')
            if not provided or not verify_totp(
                unobfuscate_totp_secret(getattr(user, 'totp_secret', '')), provided
            ):
                record_totp_failed(username)
                raise serializers.ValidationError({
                    'totp': 'Code de double authentification invalide ou manquant.',
                })
            clear_totp_attempts(username)
        data['user'] = UserSerializer(user).data
        return data
