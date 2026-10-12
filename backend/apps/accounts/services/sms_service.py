# backend/apps/accounts/services/sms_service.py
"""
Envoi du code de vérification par SMS via l'API eSMS Africa (passerelle réelle,
couverture Madagascar : Telma, Orange, Airtel — ~0,075 USD / SMS local).

Modes :
- TESTING (tests unitaires) ou DEBUG sans OTP_ENVOI_REEL : le code est seulement
  affiché dans la console du serveur (aucun appel réseau, aucun coût).
- Sinon : envoi réel en POST https://sms.esmsafrica.io/api/messages/send
  (Bearer, corps {to, text, sender_id}, numéro au format E.164 +261…).

Exploitation :
- ESMS_API_KEY doit être une clé « esms_live_… » active.
- ESMS_SENDER_ID doit être un sender approuvé (Dashboard → /sender-ids).
- Le portefeuille doit avoir un solde suffisant (Billing → Top Up).
"""
import os

import requests
from django.conf import settings

# Message lisible par code HTTP renvoyé par eSMS.
_ERREURS_HTTP = {
    400: "Requête refusée par eSMS : numéro invalide ou aucune route vers ce pays.",
    401: "Clé API eSMS invalide/expirée (401). Vérifiez ESMS_API_KEY.",
    402: "Solde eSMS insuffisant (402). Rechargez le portefeuille pour envoyer des SMS.",
    403: "Sender ID non approuvé (403). Approuvez ESMS_SENDER_ID sur /sender-ids.",
    409: "Message identique déjà envoyé au même numéro il y a moins de 5 minutes (409).",
    413: "Message trop long (413).",
    422: "Corps de requête invalide (422) : 'to' ou 'text' manquant.",
    429: "Trop de requêtes (429) : limite de débit eSMS atteinte, réessayez plus tard.",
}


def _envoi_reel_autorise():
    """Vrai dès qu'un envoi réel doit partir (prod, ou dev avec OTP_ENVOI_REEL)."""
    if getattr(settings, 'TESTING', False):
        return False
    return not settings.DEBUG or getattr(settings, 'OTP_ENVOI_REEL', False)


def _vers_e164(phone):
    """Convertit un numéro malgache en E.164 (+261XXXXXXXXX) ; None si impossible."""
    chiffres = ''.join(c for c in str(phone or '') if c.isdigit())
    if chiffres.startswith('261') and len(chiffres) == 12:
        return '+' + chiffres
    if len(chiffres) == 10 and chiffres.startswith('0'):
        chiffres = chiffres[1:]                    # 0 initial local → 3XXXXXXXX
    if len(chiffres) == 9:
        return '+261' + chiffres
    return None


def send_verification_sms(phone, code, purpose):
    """
    Envoie un SMS de vérification via l'API eSMS Africa.

    - DEBUG sans OTP_ENVOI_REEL (ou en tests) : le code est affiché en console.
    - Sinon : envoi réel. Ne renvoie True QUE si eSMS accepte le message
      (status 'submitted'/'queued'/'delivered') ; tout autre cas journalise la
      raison exacte (401/402/403/…) et renvoie False.
    """
    purpose_text = 'inscription' if purpose == 'signup' else 'connexion'
    message = f"Lazan'i Betsileo - Votre code de {purpose_text}: {code}. Expire dans 10 min."

    if not _envoi_reel_autorise():
        print(f"[SMS CONSOLE] À {phone} | Code: {code} | Message: {message}")
        return True

    numero = _vers_e164(phone)
    if numero is None:
        print(f"[SMS ERREUR] Numéro non convertible en E.164 : {phone!r} — SMS non envoyé.")
        return False

    api_key = os.getenv('ESMS_API_KEY') or getattr(settings, 'ESMS_API_KEY', '')
    if not api_key:
        print("[SMS ERREUR] ESMS_API_KEY absente — SMS non envoyé.")
        return False
    sender_id = os.getenv('ESMS_SENDER_ID') or getattr(settings, 'ESMS_SENDER_ID', 'eSMS')

    try:
        response = requests.post(
            'https://sms.esmsafrica.io/api/messages/send',
            json={'to': numero, 'text': message, 'sender_id': sender_id},
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"[SMS ERREUR] Réseau eSMS injoignable — {type(exc).__name__}: {exc}")
        return False

    if response.status_code in (200, 201):
        try:
            statut = response.json().get('status')
        except ValueError:
            statut = None
        if statut in ('submitted', 'queued', 'delivered'):
            print(f"[SMS OK] Envoyé à {numero} (status={statut}).")
            return True
        print(f"[SMS ERREUR] Réponse eSMS inattendue : {response.status_code} {response.text[:300]}")
        return False

    raison = _ERREURS_HTTP.get(response.status_code, f"Erreur HTTP {response.status_code}")
    print(f"[SMS ERREUR] {raison} → {response.text[:300]}")
    return False
