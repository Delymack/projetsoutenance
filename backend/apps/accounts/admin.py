# backend/apps/accounts/admin.py
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.template.response import TemplateResponse
from django.urls import path
from django.shortcuts import redirect

from .models import User, VerificationCode
from .services import generate_otp
from .services.sms_service import send_verification_sms


class TestSMSForm(forms.Form):
    """Formulaire de test : un numéro et le type de message à envoyer."""
    telephone = forms.CharField(
        label='Numéro du destinataire',
        max_length=20,
        help_text='Format +261XXXXXXXXX, 261XXXXXXXXX ou 03X XX XXX XX.',
        widget=forms.TextInput(attrs={'placeholder': '+261 34 00 000 00'}),
    )
    purpose = forms.ChoiceField(
        label='Type de message',
        choices=[('signup', 'Inscription'), ('login', 'Connexion')],
    )


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    # Codes de vérification : le contact, l'usage, s'il a servi, quand il expire.
    # Le canal, les tentatives et la date de création restent sur la fiche.
    list_display = ('contact', 'purpose', 'is_used', 'expires_at')
    list_filter = ('contact_type', 'purpose', 'is_used')
    search_fields = ('contact',)
    readonly_fields = ('id', 'code_hash', 'created_at', 'updated_at')
    change_list_template = 'admin/accounts/verificationcode/change_list.html'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('test-sms/', self.admin_site.admin_view(self.test_sms_view), name='test-envoi-sms'),
        ]
        return custom_urls + urls

    def test_sms_view(self, request):
        """
        Envoie un SMS de vérification réel pour tester la passerelle eSMS Africa.

        Utile en soutenance : on saisit un numéro, on reçoit le vrai SMS avec le
        code, sans passer par le formulaire d'inscription du site.
        """
        initial = {}
        telephone_prefill = request.GET.get('telephone')
        if telephone_prefill:
            initial['telephone'] = telephone_prefill
        form = TestSMSForm(request.POST or None, initial=initial)
        resultat = None

        if request.method == 'POST' and form.is_valid():
            telephone = form.cleaned_data['telephone']
            purpose = form.cleaned_data['purpose']
            code = generate_otp()
            envoye = send_verification_sms(telephone, code, purpose)
            resultat = {
                'succes': envoye,
                'telephone': telephone,
                'code': code,
                'purpose': purpose,
            }
            if envoye:
                self.message_user(request, f'SMS envoyé à {telephone} (code {code}).', level='success')
            else:
                self.message_user(
                    request,
                    "Échec de l'envoi. Vérifiez le solde eSMS Africa et la clé API "
                    "(voir la console du serveur pour le détail).",
                    level='error',
                )

        return TemplateResponse(request, 'admin/accounts/test_sms.html', {
            'form': form,
            'resultat': resultat,
            'opts': self.model._meta,
            'title': "Tester l'envoi de SMS",
        })

    # Un code de vérification : à qui il a été envoyé, à quoi il sert, s'il a
    # servi et jusqu'à quand il vaut. L'empreinte, les tentatives et l'origine
    # sont des données techniques : elles restent, repliées.
    fieldsets = (
        ('Code', {'fields': ('contact', 'contact_type', 'purpose', 'is_used')}),
        ('Validité', {'fields': ('expires_at', 'attempts', 'last_sent_at')}),
        ('Technique', {
            'fields': ('id', 'code_hash', 'user_data', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # Comptes : l'identifiant, l'email, le rôle et les deux droits qui décident de
    # l'accès. Le nom civil reste sur la fiche.
    list_display = ('username', 'email', 'role', 'is_active', 'is_staff')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    actions = ['envoyer_sms_test']
    fieldsets = (
        (None, {'fields': ('username', 'email', 'first_name', 'last_name', 'password')}),
        ('Informations personnelles', {'fields': ('telephone',)}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {'fields': ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff')}),
    )

    @admin.action(description="Tester l'envoi SMS vers ce compte")
    def envoyer_sms_test(self, request, queryset):
        """
        Ouvre la page de test SMS pré-remplie avec le téléphone du premier
        compte sélectionné. Un seul compte à la fois : le téléphone est unique.
        """
        compte = queryset.first()
        if compte is None:
            self.message_user(request, "Sélectionnez un compte.", level='error')
            return None
        telephone = (compte.telephone or '').strip()
        if not telephone:
            self.message_user(
                request, f"Le compte « {compte} » n'a pas de numéro de téléphone.",
                level='error',
            )
            return None
        from django.urls import reverse
        url = reverse('admin:test-envoi-sms')
        return redirect(f'{url}?telephone={telephone}')
