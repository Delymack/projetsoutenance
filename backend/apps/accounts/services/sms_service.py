# backend/apps/accounts/services/sms_service.py
import os

import requests
from django.conf import settings


def _envoi_reel_autorise():
    """Vrai dès qu'on veut/l'envoi réel doit partir (prod, ou dev avec flag)."""
    if getattr(settings, 'TESTING', False):
        return False
    return not settings.DEBUG or getattr(settings, 'OTP_ENVOI_REEL', False)


def send_verification_sms(phone, code, purpose):
    """
    Envoie un SMS de vérification via l'API eSMS Africa.

    - DEBUG sans OTP_ENVOI_REEL (ou en tests) : le code est affiché en console.
    - Sinon : envoi réel via POST https://sms.esmsafrica.io/api/messages/send
      (authentification Bearer, corps {to, text, sender_id}).

    Rappels d'exploitation : le sender ID doit être approuvé (sender-ids), et
    la balance du compte doit être positive (Billing → Top Up).
    """
    purpose_text = 'inscription' if purpose == 'signup' else 'connexion'
    message = f"Lazan'i Betsileo - Votre code de {purpose_text}: {code}. Expire dans 10 min."

    if not _envoi_reel_autorise():
        print(f"[SMS CONSOLE] À {phone} | Code: {code} | Message: {message}")
        return True

    api_key = os.getenv('ESMS_API_KEY')
    if not api_key:
        print(f"[SMS ERREUR] clé ESMS_API_KEY absente — SMS non envoyé à {phone}")
        return False

    try:
        response = requests.post(
            'https://sms.esmsafrica.io/api/messages/send',
            json={
                'to': phone,
                'text': message,
                'sender_id': os.getenv('ESMS_SENDER_ID', 'eSMS'),
            },
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=15,
        )
        ok = response.status_code in (200, 201) and response.json().get('status') in (
            'submitted', 'queued', 'delivered',
        )
        if not ok:
            print(f"[SMS ERREUR] {response.status_code} {response.text[:300]}")
        return ok
    except Exception as exc:
        print(f"[SMS ERREUR] {type(exc).__name__}: {exc}")
        return False