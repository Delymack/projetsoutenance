"""Routes « pages » de l'espace d'authentification (montées sous /admin/).

Ces vues sont enregistrées AVANT `admin.site.urls` pour ne pas être captées
par le back-office, et héritent toutes de la charte graphique LAZAN' BETSILEO.
"""
from django.urls import path

from apps.accounts import auth_views
from apps.accounts.global_search import recherche_globale_view
from apps.accounts.notification_views import notification_action

urlpatterns = [
    path('notifications/action/', notification_action, name='notifications-action'),
    path('recherche/', recherche_globale_view, name='recherche-globale'),
    path('signup/', auth_views.signup_view, name='auth-signup'),
    path('verify-email/', auth_views.verify_email_view, name='auth-verify-email'),
    path('forgot-password/', auth_views.forgot_password_view, name='auth-forgot-password'),
    path('reset-password/', auth_views.reset_password_view, name='auth-reset-password'),
    path('magic-link/', auth_views.magic_link_page_view, name='auth-magic-link'),
    path('magic-link/<str:token>/', auth_views.magic_link_confirm_view, name='auth-magic-link-confirm'),
    path('2fa/enable/', auth_views.enable_2fa_view, name='auth-2fa-enable'),
    path('2fa/verify/', auth_views.verify_2fa_view, name='auth-2fa-verify'),
    path('2fa/disable/', auth_views.disable_2fa_view, name='auth-2fa-disable'),
    path('account/', auth_views.account_security_view, name='auth-account'),
    path('account/logout-others/', auth_views.logout_others_view, name='auth-logout-others'),
    path('account/session/<str:session_key>/delete/', auth_views.revoke_session_view, name='auth-revoke-session'),
    path('message/', auth_views.message_view, name='auth-message'),
]