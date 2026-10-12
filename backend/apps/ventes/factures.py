# backend/apps/ventes/factures.py
"""Facture d'une commande du site validée : lien signé et oubli par e-mail.

Une commande du site (« réservation ») n'est pas encaissée au moment de sa
validation : aucune vente (réf. FAC-) n'existe encore, et le client — souvent
sans compte — ne porte aucun jeton. Cette « facture » est un document autonome
dont l'adresse embarque un jeton signé (``TimestampSigner``) : lisible par
tous dans la limite de validité, impossible à deviner par ailleurs.

Le document reste consultable tant que la commande validée est en attente, a
reçu un acompte, ou a été soldée (le lien envoyé à la validation doit rester
bon après le passage en caisse).
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

logger = logging.getLogger(__name__)

EMAIL_SEL = 'lb.facture-commande'
VALIDITE_JOURS = 90
DELAI_SECONDES = VALIDITE_JOURS * 24 * 3600


def url_publique(request=None):
    """Base publique du back-office, pour rendre le lien cliquable.

    `SOCIETE['url_public']` reste prioritaire (le back-office est souvent
    derrière un nom de domaine alors que la requête arrive en 127.0.0.1). Sans
    lui, on reconstruit une absolue depuis la requête courante.
    """
    base = (getattr(settings, 'SOCIETE', {}) or {}).get('url_public', '').rstrip('/')
    if base:
        return base
    if request is not None:
        return request.build_absolute_uri('/').rstrip('/')
    return ''


def facture_accessible(commande):
    """Vrai tant qu'une commande validée reste active ou a été soldée."""
    return (
        commande.source == commande.Source.SITE
        and commande.validation_statut == commande.ValidationStatut.VALIDEE
        and commande.statut
        in (commande.Statut.EN_ATTENTE, commande.Statut.ACOMPTE, commande.Statut.SOLDEE)
    )


def _signer():
    return TimestampSigner(salt=EMAIL_SEL)


def facture_token(commande):
    """Jeton signé et horodaté rattaché à une commande précise."""
    return _signer().sign_object({'id': commande.pk, 'ref': commande.reference})


def verifier_token(commande, token):
    """Vrai si le jeton est valide et bien rattaché à cette commande."""
    if not token:
        return False
    try:
        payload = _signer().unsign_object(token, max_age=DELAI_SECONDES)
    except (BadSignature, SignatureExpired):
        return False
    return payload.get('id') == commande.pk and payload.get('ref') == commande.reference


def facture_url(request, commande):
    """Adresse publique de la facture, signée pour rester privée tout de même."""
    return f"{url_publique(request)}/api/reservations/{commande.pk}/facture/?t={facture_token(commande)}"


def destinataire_facture(commande):
    """E-mail du client : celui saisi à la commande, sinon celui du compte."""
    email = (commande.client.email or '').strip() if commande.client_id else ''
    if not email and commande.compte_client:
        email = (commande.compte_client.email or '').strip()
    return email


def _argent(montant):
    try:
        valeur = Decimal(montant)
    except Exception:  # noqa: BLE001
        return str(montant)
    texte = f'{valeur:,.2f}'.replace(',', ' ')
    if texte.endswith('.00'):
        texte = texte[:-3]
    return f'{texte} Ar'


def message_facture_commande(commande):
    """Prépare l'e-mail de validation : ``(sujet, texte, html, destinataire)``."""
    societe = (getattr(settings, 'SOCIETE', {}) or {})
    nom_societe = societe.get('nom', "LAZAN'I BETSILEO")
    client = commande.client
    nom_client = f"{client.prenom} {client.nom}".strip() if commande.client_id else 'Cher client'
    destinataire = destinataire_facture(commande)
    lien = facture_url(None, commande)

    lignes = list(commande.lignes.select_related('produit'))
    resumer = '\n'.join(
        f"  - {ligne.quantite} x {ligne.produit.nom} ({_argent(ligne.prix_unitaire)} x {ligne.quantite})"
        for ligne in lignes
    )
    reception = (
        f"Votre commande sera livrée à : {commande.adresse_livraison}"
        if commande.mode_reception == commande.ModeReception.LIVRAISON
        else "Votre commande est à retirer en boutique."
    )
    suite = []
    if commande.date_expiration:
        suite.append(f"Retenez votre commande jusqu'au {commande.date_expiration:%d/%m/%Y}.")
    if lien:
        suite.append(f"Votre facture est disponible ici : {lien}")
    else:
        suite.append('La facture restera consultable depuis votre historique.')

    sujet = f"Commande {commande.reference} validée — {nom_societe}"
    paragraphes = [
        f"Bonjour {nom_client},",
        f"Votre commande {commande.reference} a été validée par notre équipe.",
        reception,
        f"Récapitulatif :\n{resumer}\n\n"
        f"Total : {_argent(commande.montant_total)}",
    ]
    if commande.montant_acompte:
        paragraphes.append(f"Acompte déjà versé : {_argent(commande.montant_acompte)}")
    paragraphes.append(f"Reste à payer : {_argent(commande.solde_du)}")
    paragraphes.extend(suite)
    paragraphes.append(f"Merci pour votre confiance,\nL'équipe {nom_societe}")
    texte = '\n\n'.join(paragraphes) + '\n'

    lignes_html = ''.join(
        f"<tr><td>{ligne.quantite} × {ligne.produit.nom}</td>"
        f"<td align='right'>{_argent(ligne.prix_unitaire * ligne.quantite)}</td></tr>"
        for ligne in lignes
    )
    bloc_tva = ''
    from apps.parametres.tva import decomposition as _decomposition
    detail_tva = _decomposition(commande.montant_total, commande.taux_tva, commande.tva_incluse)
    if detail_tva.get('active'):
        bloc_tva = (
            f"<tr><td>Base HT</td><td align='right'>{_argent(detail_tva['ht'])}</td></tr>"
            f"<tr><td>{detail_tva['libelle']} (incluse)</td><td align='right'>{_argent(detail_tva['tva'])}</td></tr>"
        )
    bouton = (
        f"<a href='{lien}' style='display:inline-block;margin:18px 0;padding:12px 20px;"
        f"background:#641b2c;color:#fff;border-radius:8px;font-weight:700;text-decoration:none;'>"
        f"Voir ma facture</a>"
        if lien
        else ''
    )
    lignes_fin = '<br>'.join(suite)
    bloc_acompte = (
        f"<tr><td>Acompte déjà versé</td>"
        f"<td align='right'>{_argent(commande.montant_acompte)}</td></tr>"
        if commande.montant_acompte
        else ''
    )
    html = (
        "<html><body style='font-family:Helvetica,Arial,sans-serif;color:#2b1b20;"
        "max-width:600px;margin:0 auto;'>"
        "<h2 style='color:#641b2c;'>"
        f"Votre commande {commande.reference} a été validée</h2>"
        f"<p>Bonjour {nom_client},</p>"
        f"<p>{reception}</p>"
        f"<table style='width:100%;border-collapse:collapse;margin-top:14px;'>"
        f"<thead><tr><th style='text-align:left;border-bottom:1px solid #ece5df;'>Article</th>"
        f"<th style='border-bottom:1px solid #ece5df;'>Sous-total</th></tr></thead>"
        f"<tbody>{lignes_html}{bloc_tva}"
        f"<tr><td><strong>Total</strong></td><td align='right'><strong>{_argent(commande.montant_total)}</strong></td></tr>"
        f"{bloc_acompte}"
        f"<tr><td><strong>Reste à payer</strong></td>"
        f"<td align='right'><strong>{_argent(commande.solde_du)}</strong></td></tr>"
        f"</tbody></table>{bouton}"
        f"<p style='color:#6f5f62;font-size:.85rem;'>{lignes_fin}</p>"
        f"<p style='color:#6f5f62;font-size:.85rem;'>Merci pour votre confiance, "
        f"{nom_societe}</p></body></html>"
    )

    return sujet, texte, html, destinataire


def envoyer_facture_commande(commande, request=None):
    """Envoie la facture de commande. Renvoie ``(ok, detail)``, ne lève jamais.

    Hors production (tests / DEBUG), l'e-mail est affiché en console comme les
    codes OTP, sans appel réseau.
    """
    sujet, texte, html, destinataire = message_facture_commande(commande)
    if not destinataire:
        return False, 'aucune adresse email enregistrée pour ce client'

    from apps.accounts.services.email_service import envoi_reel_autorise, envoyer_email_html

    if not envoi_reel_autorise():
        print(f"[EMAIL CONSOLE] {sujet} → {destinataire} | {facture_url(request, commande)}")
        return True, 'console'

    ok, detail = envoyer_email_html(sujet, destinataire, texte, html)
    if not ok:
        print(f"[EMAIL ERREUR] {detail}")
    return ok, detail