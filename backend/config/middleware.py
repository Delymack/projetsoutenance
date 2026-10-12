from django.conf import settings
from django.shortcuts import redirect

REMEMBER_ME_AGE = getattr(settings, 'REMEMBER_ME_AGE', 60 * 60 * 24 * 30)

# Chemins autorisés pendant une double authentification en attente.
# `/api/` est VOLONTAIREMENT absent : une session authentifiée sans 2FA
# validée ne doit pas pouvoir consommer l'API (caisse, dashboard). Les
# clients JWT (frontend Angular) restent fonctionnels : ils ne passent pas
# par la session et gèrent leur propre 2FA au login.
_2FA_SAFE_PREFIXES = ('/admin/2fa/verify/', '/admin/logout/', '/static/', '/admin/login/')


class TwoFactorMiddleware:
    """Bloque les sessions en attente de double authentification.

    Après un login sur un compte protégé par 2FA, le signal ``user_logged_in``
    pose le drapeau ``twofa_pending`` en session. Tant qu'il n'est pas levé, seules
    les pages de vérification / déconnexion / API sont accessibles. Cela couvre
    le login classique, la connexion Google et les liens magiques.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (
            getattr(settings, 'AUTH_2FA_ENABLED', True)
            and getattr(request, 'user', None) is not None
            and request.user.is_authenticated
            and request.session.get('twofa_pending')
            and not any(request.path.startswith(p) for p in _2FA_SAFE_PREFIXES)
        ):
            return redirect('/admin/2fa/verify/')
        return self.get_response(request)


class SessionExpiryMiddleware:
    """Applique la durée de session choisie au login (« Rester connecté »).

    - Cookie/formulaire ``remember_me=1`` → session longue (30 jours par défaut).
    - Sinon → session limitée à la fermeture du navigateur.

    Doit être déclaré APRÈS ``django.contrib.sessions.middleware.SessionMiddleware``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        session = request.session
        authed = bool(session.get('_auth_user_id'))
        remember = request.COOKIES.get('remember_me') == '1'

        login_path = request.path.rstrip('/').endswith('/login')
        is_auth_post = request.method == 'POST' and login_path and not authed
        is_logout_post = request.method == 'POST' and 'logout' in request.path

        # POST de connexion : le rôle n'est pas encore écrit en session, on
        # lit le choix dans le formulaire pour que le cookie de session soit
        # immédiatement cohérent (durée longue ou session navigateur).
        if is_auth_post:
            session.set_expiry(REMEMBER_ME_AGE if request.POST.get('remember_me') == '1' else 0)

        # Requêtes courantes (déjà connecté) : on maintient l'expiration.
        if authed:
            session.set_expiry(REMEMBER_ME_AGE if remember else 0)

        response = self.get_response(request)

        considered_logged_in = authed or (is_auth_post and not is_logout_post)
        if considered_logged_in and not is_logout_post:
            keep_remember = remember if authed else (request.POST.get('remember_me') == '1' if is_auth_post else remember)
            response.set_cookie(
                'remember_me',
                '1' if keep_remember else '0',
                max_age=REMEMBER_ME_AGE if keep_remember else None,
                samesite='Lax',
                httponly=False,
            )
        else:
            response.delete_cookie('remember_me')

        return response