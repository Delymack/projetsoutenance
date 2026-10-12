# backend/apps/accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, VerificationCode


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    # Codes de vérification : le contact, l'usage, s'il a servi, quand il expire.
    # Le canal, les tentatives et la date de création restent sur la fiche.
    list_display = ('contact', 'purpose', 'is_used', 'expires_at')
    list_filter = ('contact_type', 'purpose', 'is_used')
    search_fields = ('contact',)
    readonly_fields = ('id', 'code_hash', 'created_at', 'updated_at')
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
    fieldsets = (
        (None, {'fields': ('username', 'email', 'first_name', 'last_name', 'password')}),
        ('Informations personnelles', {'fields': ('telephone',)}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {'fields': ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff')}),
    )
