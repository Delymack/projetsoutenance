# backend/apps/accounts/services/email_service.py
import os

import requests
from django.conf import settings


def _envoi_reel_autorise():
    """Vrai dès qu'on veut/l'envoi réel doit partir (prod, ou dev avec flag)."""
    if getattr(settings, 'TESTING', False):
        return False
    return not settings.DEBUG or getattr(settings, 'OTP_ENVOI_REEL', False)


def envoi_reel_autorise():
    """Indique si un envoi réel (hors console) doit être tenté.

    Barrière unique partagée par tous les services : en tests et en DEBUG
    (sans ``OTP_ENVOI_REEL``) elle vaut ``False``, ce qui laisse la main au
    mailer Django (console / boîte de test) au lieu d'appeler le fournisseur.
    """
    return _envoi_reel_autorise()


def _envoyer_resend(payload):
    """POST brut vers l'API Resend, sans levée d'exception."""
    api_key = os.getenv('RESEND_API_KEY')
    if not api_key:
        return False, 'clé RESEND_API_KEY absente'
    try:
        response = requests.post(
            'https://api.resend.com/emails',
            json=payload,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=15,
        )
        ok = response.status_code in (200, 201, 202)
        return ok, f'{response.status_code} {response.text[:300]}'
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'


def _envoyer_resend_avec_repli(payload):
    """Envoi Resend, avec repli automatique sur l'expéditeur de bac à sable
    quand le domaine configuré n'est pas encore vérifié chez Resend."""
    ok, detail = _envoyer_resend(payload)
    if ok:
        return True, detail

    if 'domain is not verified' in detail:
        fallback = os.getenv('RESEND_SANDBOX_SENDER', 'onboarding@resend.dev')
        payload = {**payload, 'from': fallback}
        ok, detail = _envoyer_resend(payload)
        if ok:
            print(f"[EMAIL REPLI BAC À SABLE] envoi via {fallback}")
    return ok, detail


def _smtp_disponible():
    """Vrai si un serveur SMTP d'envoi est configuré (``EMAIL_HOST``)."""
    return bool(os.getenv('EMAIL_HOST') or getattr(settings, 'EMAIL_HOST', ''))


def _envoyer_resend_canal(subject, to, text, html):
    """Canal Resend (API HTTP), avec repli bac à sable si domaine non vérifié."""
    payload = {
        'from': os.getenv('RESEND_SENDER_EMAIL', 'noreply@lazani-betsileo.mg'),
        'to': [to],
        'subject': subject,
        'text': text or '',
        'html': html or text or '',
    }
    return _envoyer_resend_avec_repli(payload)


def _envoyer_smtp(subject, to, text, html):
    """Canal SMTP via le mailer Django (``MAILERS['default']``).

    Envoie réellement si ``EMAIL_HOST`` est configuré ; sinon écrit dans la
    console (utilisé comme repli de développement).
    """
    from django.core.mail import EmailMultiAlternatives, mailers

    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None) or (
        "LAZAN'I BETSILEO <no-reply@lazani-betsileo.mg>"
    )
    message = EmailMultiAlternatives(subject, text or '', from_email, [to])
    if html:
        message.attach_alternative(html, 'text/html')
    try:
        mailers['default'].send_messages([message])
        return True, 'smtp ok'
    except Exception as exc:  # noqa: BLE001
        return False, f'{type(exc).__name__}: {exc}'


def raison_echec_email():
    """Texte affiché à l'utilisateur quand l'e-mail n'a pas pu partir.

    Causes usuelles : aucun canal configuré, clé Resend absente, domaine
    d'expédition Resend non vérifié, ou identifiants SMTP invalides. Tant
    qu'aucun domaine Resend n'est vérifié, Resend n'autorise l'envoi qu'à
    l'adresse du propriétaire du compte.
    """
    return (
        "Envoi de l'email de vérification impossible : vérifiez la configuration "
        "d'envoi (SMTP via EMAIL_HOST, ou clé Resend RESEND_API_KEY et domaine "
        "vérifié sur https://resend.com/domains). Tant qu'aucun domaine Resend "
        "n'est vérifié, seul l'envoi vers l'adresse du propriétaire du compte est "
        "accepté (voir le journal du serveur pour le détail)."
    )


def _canaux_email():
    """Ordre des canaux d'envoi selon ``EMAIL_PROVIDER``.

    - ``smtp``   : SMTP d'abord, Resend en secours ;
    - ``resend`` : Resend d'abord, SMTP en secours ;
    - ``auto`` (défaut) : Resend d'abord si sa clé existe, sinon SMTP d'abord.

    Les canaux non configurés sont écartés.
    """
    provider = (os.getenv('EMAIL_PROVIDER') or 'auto').strip().lower()
    if provider == 'smtp':
        ordre = ['smtp', 'resend']
    elif provider == 'resend':
        ordre = ['resend', 'smtp']
    else:
        ordre = ['resend', 'smtp'] if os.getenv('RESEND_API_KEY') else ['smtp', 'resend']

    disponibles = {
        'resend': bool(os.getenv('RESEND_API_KEY')),
        'smtp': _smtp_disponible(),
    }
    return [c for c in ordre if disponibles[c]]


def envoyer_email_html(subject, to, text, html=None):
    """Envoie un e-mail (texte + HTML) via le(s) canal(aux) configuré(s).

    Resend (API) et SMTP (``EMAIL_HOST``) peuvent coexister : on tente dans
    l'ordre défini par ``EMAIL_PROVIDER`` et on s'arrête au premier succès.
    Renvoie ``(ok, detail)``. Aucun appel réseau si ``envoi_reel_autorise()``
    est faux : l'appelant conserve alors le repli « mailer Django ».
    """
    if not to:
        return False, 'destinataire vide'
    if not _envoi_reel_autorise():
        return False, 'envoi réel désactivé (console Django)'

    canaux = _canaux_email()
    echecs = []
    for canal in canaux:
        if canal == 'resend':
            ok, detail = _envoyer_resend_canal(subject, to, text, html)
        else:
            ok, detail = _envoyer_smtp(subject, to, text, html)
        if ok:
            return True, f'{canal} : {detail}'
        echecs.append(f'{canal} : {detail[:150]}')

    # Aucun canal réel n'a fonctionné. En développement sans SMTP, on ne bloque
    # pas l'inscription : l'e-mail part via le mailer par défaut (console, ou
    # fichier .eml dans backend/var/mail/).
    if not _smtp_disponible() and getattr(settings, 'DEBUG', False) \
            and not getattr(settings, 'TESTING', False):
        print(f"[EMAIL REPLI DEV] canaux en échec ({' | '.join(echecs)}) — repli mailer Django.")
        ok, detail = _envoyer_smtp(subject, to, text, html)
        if ok:
            return True, 'repli mailer Django (dev)'

    return False, ' | '.join(echecs) or 'aucun canal e-mail configuré'


def send_verification_email(email, code, purpose):
    """
    Envoie un e-mail de vérification via les canaux configurés (Resend / SMTP).

    - DEBUG sans OTP_ENVOI_REEL (ou en tests) : le code est affiché en console.
    - Sinon : envoi réel. Le même canal sert l'inscription du frontend et les
      pages de confirmation du backend.
    """
    purpose_text = 'inscription' if purpose == 'signup' else 'connexion'
    message = (
        f"Bonjour,\n\n"
        f"Votre code de vérification pour votre {purpose_text} est : {code}\n\n"
        f"Ce code expire dans 10 minutes.\n\n"
        f"L'équipe Lazan'i Betsileo\n"
    )
    html = (
        f"<html><body>"
        f"<p>Bonjour,</p>"
        f"<p>Votre code de vérification pour votre {purpose_text} est&nbsp;:</p>"
        f"<p style=\"font-size:28px;letter-spacing:6px;font-weight:bold\">{code}</p>"
        f"<p>Ce code expire dans 10 minutes.</p>"
        f"<p>L'équipe Lazan'i Betsileo</p>"
        f"</body></html>"
    )

    if not _envoi_reel_autorise():
        print(f"[EMAIL CONSOLE] À {email} | Code: {code} | Objectif: {purpose}")
        return True

    ok, detail = envoyer_email_html(
        "Vérification de votre compte - Lazan'i Betsileo", email, message, html
    )
    if not ok:
        print(f"[EMAIL ERREUR] {detail}")
    return ok