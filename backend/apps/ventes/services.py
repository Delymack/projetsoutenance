import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, DecimalField, F, IntegerField, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.clients.models import Client, ReglementClient
from apps.produits.models import Produit
from apps.stocks.models import Stock, MouvementStock
from apps.ventes.factures import envoyer_facture_commande
from apps.ventes.models import (
    Vente, LigneVente, Paiement, RetourVente, Reservation, LigneReservation, SessionCaisse,
)
from apps.ventes.politiques import (
    devise, jours_validite_reservation, plafond_remise, session_caisse_requise,
)
from apps.promotions.services import (
    meilleure_promotion,
    promotions_candidat_qs,
    promotion_applicable,
    remise_promotion,
)

DEUX = Decimal('0.01')

logger = logging.getLogger(__name__)


def _money(valeur):
    """Arrondit au centime, comme attendu pour des montants en devise locale."""
    return Decimal(valeur).quantize(DEUX, rounding=ROUND_HALF_UP)


def _to_decimal(valeur, defaut='0'):
    """Convertit une valeur de formulaire/API en Decimal sans lever d'exception."""
    if valeur is None or valeur == '':
        return Decimal(defaut)
    try:
        return Decimal(str(valeur))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(defaut)


def _regles_facture(date_facture, taux_tva_force=None, tva_incluse_force=None):
    """Capture les règles de TVA et d’échéance pour figer la facture émise."""
    from apps.parametres.services import get_config

    config = get_config()
    try:
        taux_tva = Decimal(str(
            config['ventes_tva'] if taux_tva_force is None else taux_tva_force
        ))
        delai_jours = int(config['ventes_delai_paiement_jours'])
        tva_incluse = bool(
            config['ventes_tva_incluse']
            if tva_incluse_force is None else tva_incluse_force
        )
    except (KeyError, InvalidOperation, TypeError, ValueError):
        raise ValidationError({
            'facture': 'Le taux de TVA ou le délai de paiement configuré est invalide.'
        })
    if not taux_tva.is_finite() or not Decimal('0') <= taux_tva <= Decimal('100'):
        raise ValidationError({'ventes_tva': 'Le taux de TVA doit être compris entre 0 et 100 %.'})
    if not 0 <= delai_jours <= 3650:
        raise ValidationError({
            'ventes_delai_paiement_jours': 'Le délai de paiement doit être compris entre 0 et 3650 jours.'
        })

    return (
        taux_tva.quantize(DEUX),
        tva_incluse,
        date_facture + timedelta(days=delai_jours),
    )


def _base_vers_ttc(montant, taux_tva, tva_incluse):
    from apps.parametres.tva import base_vers_ttc
    return base_vers_ttc(montant, taux_tva, tva_incluse)


def _ttc_vers_base(montant, taux_tva, tva_incluse):
    from apps.parametres.tva import ttc_vers_base
    return ttc_vers_base(montant, taux_tva, tva_incluse)


class VenteService:
    @staticmethod
    def promotions_candidats(produit, type_client=None, quantite=1):
        """
        Promotions actives ciblant ce produit (sélection directe ou catégorie).
        Préchargées pour éviter une requête par ligne de vente.
        """
        return list(
            promotions_candidat_qs(produit, type_client=type_client, quantite=quantite)
            .prefetch_related('categories')
        )

    @staticmethod
    def calculer_remise_produit(produit, prix_unitaire, quantite=1, type_client=None,
                                promos=None):
        """
        Recherche la promotion active la plus avantageuse pour ce produit et
        calcule la remise sur la ligne complète (``quantite`` unités).

        Toutes les conditions sont évaluées : fenêtre de dates, créneau happy
        hour, quantité minimale et segment de client.

        Retourne ``(remise_ligne, prix_final_ligne, promotion|None)``.
        """
        if promos is None:
            promos = VenteService.promotions_candidats(
                produit, type_client=type_client, quantite=quantite
            )
        meilleure, remise = meilleure_promotion(
            produit, prix_unitaire, quantite=quantite,
            type_client=type_client, promos=promos,
        )
        if meilleure is None:
            return Decimal('0'), prix_unitaire * quantite, None

        return remise, prix_unitaire * quantite - remise, meilleure

    @staticmethod
    def _resolve_conditionnement(produit, unite=None, type_client=None):
        """
        Détermine l'unité réellement vendue et son prix.

        Une promotion étant toujours exprimée par bouteille, la remise est
        calculée sur le prix à la bouteille puis reconduite au conditionnement :
        un pack de 6 vendu à prix dégressif reste donc remisé au même taux.
        """
        unite = unite or produit.unite_vente or Produit.UniteVente.BOUTEILLE
        if unite not in dict(Produit.UniteVente.choices):
            unite = Produit.UniteVente.BOUTEILLE
        contenance = 1 if unite == Produit.UniteVente.BOUTEILLE else produit.bouteilles_par_unite
        prix_unitaire = produit.prix_unitaire_pour_client(type_client, unite)
        return unite, contenance, _money(prix_unitaire)

    @staticmethod
    @transaction.atomic
    def creer_vente(client_id, mode_paiement, lignes_data, utilisateur,
                    paiements=None, motif_remise='', session=None, acompte_anticipe=0,
                    client_libelle='', reference_paiement='', tarifs_verrouilles=None,
                    tarifs_verrouilles_ttc=False, taux_tva_facture=None,
                    tva_incluse_facture=None):
        """
        Encaisse une vente de façon atomique.

        * ``client_id`` : optionnel. Absent ou nul, la vente est anonyme
          (client de passage) ; ``client_libelle`` porte alors le nom donné au
          comptoir pour qu'il apparaisse sur le ticket.
        * ``paiements`` : liste de ``{mode, montant, reference}`` pour un
          règlement mixte. Absente, un paiement unique sur ``mode_paiement``,
          avec ``reference_paiement`` pour les opérateurs et le chèque.
        * ``lignes_data`` : liste de ``{produit_id, quantite, unite?,
          remise_manuelle?}`` ; ``quantité`` compte les unités vendues et le
          stock est décompté en bouteilles (quantité × contenance).
        * ``acompte_anticipe`` : déjà encaissé hors vente (réservation) ; les
          encaissements doivent alors couvrir ``total − acompte_anticipe``.
        """
        # 1. Client optionnel : une vente anonyme (client de passage) est
        #    autorisée. Sans client, ni crédit, ni points, ni ciblage par
        #    segment : la vente reste purement commerciale.
        client = None
        type_client = None
        if client_id:

            # Ligne verrouillée : protège le plafond de crédit et les points
            # face aux ventes concurrentes.
            try:
                client = Client.objects.select_for_update().get(id=client_id)
            except Client.DoesNotExist:
                raise ValidationError({"client": "Client introuvable."})
            type_client = client.type_client

        if not lignes_data:
            raise ValidationError({"lignes": "La vente doit contenir au moins une ligne."})

        # Un moyen de paiement retiré du paramétrage ne peut plus être saisi,
        # même via l'API : le code reste valide (l'historique se relit) mais
        # il n'est plus proposé. Sans cela, désactiver un mode serait sans
        # effet sur les appels directs. En règlement mixte, ``mode_paiement``
        # n'est qu'un placeholder : ce sont les lignes de ``paiements``
        # qui font foi, elles sont contrôlées plus bas.
        from apps.ventes.paiements import est_actif
        if not paiements and not est_actif(mode_paiement):
            raise ValidationError({
                "mode_paiement": "Ce moyen de paiement n'est plus accepté (paramètres de la caisse)."
            })

        # Le crédit est un engagement : il exige une fiche client avec un
        # plafond autorisé. Une vente anonyme ne peut pas en créer un.
        if mode_paiement == Vente.ModePaiement.CREDIT and (client is None or client.max_credit <= 0):
            raise ValidationError({"client": "Le paiement en compte exige un client autorisé."})

        taux_tva, tva_incluse, date_echeance = _regles_facture(
            timezone.localdate(),
            taux_tva_force=taux_tva_facture,
            tva_incluse_force=tva_incluse_facture,
        )

        # Le crédit consenti dans un règlement mixte est traité comme du crédit.
        if paiements:
            from apps.ventes.paiements import est_actif
            for p in paiements:
                if not est_actif(p.get('mode')):
                    raise ValidationError({
                        "paiements": "Un moyen de paiement du règlement n'est plus accepté (paramètres de la caisse)."
                    })
                if p.get('mode') == Vente.ModePaiement.CREDIT and (client is None or client.max_credit <= 0):
                    raise ValidationError({
                        "paiements": "Le paiement en compte exige un client autorisé."
                    })

        produits_demandes = set()
        for ligne in lignes_data:
            produit_id = ligne.get('produit_id')
            quantite = ligne.get('quantite')

            if produit_id in produits_demandes:
                raise ValidationError({"lignes": "Chaque produit ne peut apparaître qu'une seule fois dans une vente."})
            produits_demandes.add(produit_id)

            if not produit_id:
                raise ValidationError({"produit": "Identifiant du produit manquant."})

            if not quantite or quantite <= 0:
                raise ValidationError({"quantite": f"Quantité invalide pour le produit {produit_id}."})

        # 9. Créer la vente (temporairement sans total)
        vente = Vente.objects.create(
            client=client,
            client_libelle=('' if client else (client_libelle or '').strip()[:150]),
            utilisateur=utilisateur,
            mode_paiement=mode_paiement,
            motif_remise=motif_remise.strip()[:255],
            session=session,
            total=0,
            taux_tva=taux_tva,
            tva_incluse=tva_incluse,
            date_echeance=date_echeance,
        )

        total_general = Decimal('0')
        remise_manuelle_totale = Decimal('0')
        produits_stocker = {}  # produit_id -> (stock verrouillé, bouteilles restantes)

        for ligne in lignes_data:
            produit_id = ligne.get('produit_id')
            quantite = ligne.get('quantite')

            # 2. Vérifier les produits
            try:
                produit = Produit.objects.select_for_update().get(id=produit_id)
            except Produit.DoesNotExist:
                raise ValidationError({"produit": f"Produit {produit_id} introuvable."})

            if not produit.statut:
                raise ValidationError({"produit": f"Le produit \"{produit.nom}\" n'est pas disponible pour la vente."})

            # 3. Vérifier les quantités (doit être > 0)
            if not quantite or quantite <= 0:
                raise ValidationError({"quantite": f"Quantité invalide pour le produit {produit.nom}."})

            unite, contenance, prix_catalogue = VenteService._resolve_conditionnement(
                produit, ligne.get('unite'), type_client=type_client
            )
            if tarifs_verrouilles and produit_id in tarifs_verrouilles:
                prix_verrouille = _money(_to_decimal(tarifs_verrouilles[produit_id]))
                prix_catalogue = (
                    _ttc_vers_base(prix_verrouille, taux_tva, tva_incluse)
                    if tarifs_verrouilles_ttc else prix_verrouille
                )
            prix_unitaire = _base_vers_ttc(prix_catalogue, taux_tva, tva_incluse)
            quantite_bouteilles = quantite * contenance

            # 4. Vérifier le stock disponible (en bouteilles)
            if produit_id in produits_stocker:
                stock = produits_stocker[produit_id][0]
            else:
                try:
                    stock = Stock.objects.select_for_update().get(produit=produit)
                except Stock.DoesNotExist:
                    raise ValidationError({"stock": f"Aucun stock défini pour {produit.nom}."})
                produits_stocker[produit_id] = [stock, 0]

            if stock.quantite < quantite_bouteilles:
                unite_txt = f" ({quantite} × {produit.conditionnement_libelle})" if unite != Produit.UniteVente.BOUTEILLE else ""
                raise ValidationError({
                    "stock": f"Stock insuffisant pour {produit.nom}{unite_txt}. "
                             f"Disponible: {stock.quantite} bouteille(s), Demandé: {quantite_bouteilles}"
                })

            # 5 & 6. Promotion applicable à la ligne, puis calcul du sous-total.
            #    La promotion raisonne en bouteilles, puis on la reconduit à l'unité.
            prix_bouteille = prix_catalogue / contenance
            candidats = VenteService.promotions_candidats(
                produit, type_client=type_client, quantite=quantite_bouteilles
            )

            # Promotion automatique applicable à la ligne
            promo_appliquee = None
            _, _, promo_appliquee = VenteService.calculer_remise_produit(
                produit, prix_bouteille, quantite=quantite_bouteilles,
                type_client=type_client, promos=candidats,
            )

            # 7. Remise promotionnelle, puis remise manuelle du caissier.
            remise_promo_bouteilles = Decimal('0')
            if promo_appliquee is not None:
                remise_promo_bouteilles = remise_promotion(
                    promo_appliquee, prix_bouteille, quantite_bouteilles
                )
            remise_promo = _money(remise_promo_bouteilles * contenance)
            remise_promo = _base_vers_ttc(remise_promo, taux_tva, tva_incluse)

            brut_ligne = prix_unitaire * quantite
            remise_manuelle = _money(_to_decimal(ligne.get('remise_manuelle')))
            plafond = plafond_remise(utilisateur, brut_ligne)
            if remise_manuelle < 0:
                raise ValidationError({
                    "remise_manuelle": f"Remise manuelle négative sur {produit.nom}."
                })
            if remise_manuelle > 0:
                if plafond is not None and remise_manuelle > plafond:
                    if plafond == 0:
                        raise ValidationError({
                            "remise_manuelle": "La remise manuelle est réservée aux administrateurs."
                        })
                    raise ValidationError({
                        "remise_manuelle":
                            f"Remise manuelle trop élevée sur {produit.nom} : "
                            f"maximum {plafond} pour ce poste."
                    })
                if remise_promo + remise_manuelle > brut_ligne:
                    raise ValidationError({
                        "remise_manuelle":
                            f"Remises ({remise_promo + remise_manuelle}) supérieures au montant "
                            f"de la ligne ({brut_ligne}) pour {produit.nom}."
                    })

            total_remise_ligne = remise_promo + remise_manuelle
            sous_total = _money(brut_ligne - total_remise_ligne)

            # 10. Créer les lignes de vente
            LigneVente.objects.create(
                vente=vente,
                produit=produit,
                quantite=quantite,
                prix_unitaire=prix_unitaire,
                remise=total_remise_ligne,
                remise_manuelle=remise_manuelle,
                sous_total=sous_total,
                promotion=promo_appliquee,
                unite=unite,
                contenance=contenance,
            )

            # 11. Diminuer automatiquement le stock (en bouteilles)
            stock.quantite -= quantite_bouteilles
            stock.save()

            libelle_unite = f" — {quantite} × {produit.conditionnement_libelle}" if unite != Produit.UniteVente.BOUTEILLE else ""
            MouvementStock.objects.create(
                produit=produit,
                quantite=-quantite_bouteilles,
                type_mouvement=MouvementStock.TypeMouvement.SORTIE,
                description=f"Vente {vente.reference}{libelle_unite}",
                reference_id=vente.reference,
                utilisateur=utilisateur
            )

            # 8. Accumuler pour le total général
            total_general += sous_total
            remise_manuelle_totale += remise_manuelle

        # Une remise manuelle sans motif n'est pas traçable : on la refuse.
        if remise_manuelle_totale > 0 and not motif_remise.strip():
            raise ValidationError({
                "motif_remise": "Le motif est obligatoire pour justifier une remise manuelle."
            })

        # Mise à jour du total de la vente
        vente.total = _money(total_general)
        vente.remise_manuelle_totale = _money(remise_manuelle_totale)
        vente.acompte_anticipe = _money(_to_decimal(acompte_anticipe))
        if vente.acompte_anticipe > vente.total:
            raise ValidationError({
                "acompte_anticipe": "L'acompte ne peut pas dépasser le total de la vente."
            })
        vente.save()

        # 12. Encaissement : un règlement simple, ou un règlement mixte dont on
        #     retient le mode principal (le plus élevé) pour les listes et filtres.
        credit_encaisse = VenteService._enregistrer_paiements(
            vente, paiements=paiements, mode_defaut=mode_paiement, client=client,
            reference_simple=reference_paiement,
        )

        # 13. Fidélité : crédit client + points accumulés. Une vente anonyme
        #     n'ouvre ni dette ni fidélité : le comptoir l'a déjà refusée plus haut.
        if client is not None:
            if credit_encaisse:
                if Decimal(client.solde_du) + credit_encaisse > Decimal(client.max_credit):
                    raise ValidationError({
                        "client":
                            f"Plafond de crédit dépassé ({client.max_credit}). "
                            f"Solde dû actuel : {client.solde_du}, encaissement à crédit : {credit_encaisse}."
                    })
                client.solde_du = _money(Decimal(client.solde_du) + credit_encaisse)

            points = client.points_pour_montant(total_general)
            if points:
                client.points_fidelite += points

            if credit_encaisse or points:
                client.save()

        return vente

    @staticmethod
    def _enregistrer_paiements(vente, paiements, mode_defaut, client, reference_simple=''):
        """
        Écrit les encaissements d'une vente et renvoie le montant intégralement
        porté au compte client. Vérifie que les règlements couvrent exactement
        ce qui reste à payer : une caisse ne doit jamais encaisser plus (ni
        moins) que dû, acompte antérieur déduit.
        """
        a_encaisser = _money(Decimal(vente.total) - Decimal(vente.acompte_anticipe))

        if paiements:
            lignes = []
            for p in paiements:
                mode = p.get('mode') or mode_defaut
                if mode not in dict(Vente.ModePaiement.choices):
                    raise ValidationError({"paiements": f"Mode de paiement inconnu : {mode}."})
                montant = _money(_to_decimal(p.get('montant')))
                if montant <= 0:
                    raise ValidationError({"paiements": "Chaque encaissement doit être strictement positif."})
                reference = (p.get('reference') or '').strip()[:100]
                # Un opérateur de mobile money ou un chèque se rapproche ligne
                # à ligne avec son justificatif : sans référence, la clôture
                # ne peut pas justifier l'encaissement.
                if mode in Vente.MODES_A_REFERENCE_OBLIGATOIRE and not reference:
                    raise ValidationError({
                        "paiements":
                            f"Référence de transaction obligatoire pour un règlement "
                            f"en {Vente.ModePaiement(mode).label}."
                    })
                lignes.append((mode, montant, reference))

            total_encaisse = sum((m for _, m, _ in lignes), Decimal('0'))
            if _money(total_encaisse) != a_encaisser:
                if a_encaisser == 0:
                    raise ValidationError({
                        "paiements": "La vente est déjà entièrement réglée par son acompte."
                    })
                raise ValidationError({
                    "paiements":
                        f"Le total des encaissements ({_money(total_encaisse)}) ne correspond pas "
                        f"au montant restant à payer ({a_encaisser})."
                })
        else:
            if a_encaisser == 0:
                # Vente déjà entièrement couverte par un acompte antérieur :
                # rien n'entre en caisse, donc aucune ligne d'encaissement.
                # Créer un Paiement à 0 serait un mensonge comptable — et la
                # base interdit un montant nul de toute façon.
                return Decimal('0.00')
            # Vente simple : l'opérateur ou le chèque réclame sa référence dès
            # l'encaissement, sinon la ligne n'est pas justifiable.
            lignes = [(mode_defaut, a_encaisser, (reference_simple or '')[:100])]
            if mode_defaut in Vente.MODES_A_REFERENCE_OBLIGATOIRE and not lignes[0][2]:
                raise ValidationError({
                    "mode_paiement":
                        f"Référence de transaction obligatoire pour un règlement "
                        f"en {Vente.ModePaiement(mode_defaut).label}."
                })

        for mode, montant, reference in lignes:
            Paiement.objects.create(
                vente=vente, mode=mode, montant=montant, reference=reference
            )

        if len({mode for mode, _, _ in lignes}) > 1:
            # Mode principal = celui qui apporte le plus (départage : le plus petit
            # mode en cas d'égalité, pour rester déterministe).
            principal = sorted(lignes, key=lambda l: (-l[1], l[0]))[0][0]
            if vente.mode_paiement != principal:
                vente.mode_paiement = principal
                vente.save(update_fields=['mode_paiement'])

        return sum((m for mode, m, _ in lignes if mode == Vente.ModePaiement.CREDIT), Decimal('0.00'))

    @staticmethod
    @transaction.atomic
    def annuler_vente(vente_id, utilisateur=None):
        try:
            vente = Vente.objects.select_for_update().get(id=vente_id)
        except Vente.DoesNotExist:
            raise ValidationError({"vente": "Vente introuvable."})

        # Empêcher une double annulation
        if vente.statut == Vente.Statut.ANNULEE:
            raise ValidationError({"vente": "Cette vente est déjà annulée."})

        lignes = LigneVente.objects.filter(vente=vente).select_related('produit')

        # Des retours partiels ont déjà réintégré du stock : on les annule
        # d'abord, sinon le réapprovisionnement de l'annulation les compterait
        # deux fois et le stock serait faux.
        for retour in RetourVente.objects.filter(vente=vente).select_related('ligne'):
            stock = _stock_de( retour.ligne.produit)
            if stock is None:
                raise ValidationError({
                    "stock": f"Aucun stock trouvé pour « {retour.ligne.produit.nom} » : "
                             f"annulation impossible afin de préserver l'intégrité des stocks."
                })
            quantite = retour.quantite * max(int(retour.ligne.contenance or 1), 1)
            stock.quantite = max(stock.quantite - quantite, 0)
            stock.save()
            MouvementStock.objects.create(
                produit=retour.ligne.produit,
                quantite=-quantite,
                type_mouvement=MouvementStock.TypeMouvement.SORTIE,
                description=f"Annulation retour {retour.reference_retour} (vente {vente.reference})",
                reference_id=vente.reference,
                utilisateur=utilisateur or vente.utilisateur,
            )
        RetourVente.objects.filter(vente=vente).delete()

        # Restaurer les quantités dans le stock
        for ligne in lignes:
            stock = _stock_de(ligne.produit)
            if stock is None:
                raise ValidationError({
                    "stock": f"Aucun stock trouvé pour « {ligne.produit.nom} » : "
                             f"annulation impossible afin de préserver l'intégrité des stocks. "
                             f"Créez le stock de ce produit puis réessayez."
                })
            stock.quantite += ligne.quantite_bouteilles
            stock.save()

            libelle_unite = ""
            if ligne.unite != Produit.UniteVente.BOUTEILLE:
                libelle_unite = f" — {ligne.quantite} × {ligne.produit.conditionnement_libelle}"

            # Enregistrer le mouvement de retour
            MouvementStock.objects.create(
                produit=ligne.produit,
                quantite=ligne.quantite_bouteilles,
                type_mouvement=MouvementStock.TypeMouvement.RETOUR,
                description=f"Annulation Vente {vente.reference}{libelle_unite}",
                reference_id=vente.reference,
                utilisateur=utilisateur or vente.utilisateur
            )

        # Restituer les encaissements de la vente (une vente annulée n'est
        # jamais due : espèces rendues, crédit rendu au client).
        credit_rendu = sum(
            (p.montant for p in vente.paiements.all() if p.mode == Vente.ModePaiement.CREDIT),
            Decimal('0.00'),
        )
        Paiement.objects.filter(vente=vente).delete()

        # Changer le statut
        vente.statut = Vente.Statut.ANNULEE
        vente.montant_retourne = 0
        vente.save()

        # Restituer un éventuel crédit consommé et retirer les points gagnés.
        # Vente anonyme : ni compte client ni fidélité à reprendre.
        client = vente.client
        if client is not None:
            a_sauver = False
            if credit_rendu:
                client.solde_du = max(Decimal(client.solde_du) - credit_rendu, Decimal('0.00'))
                a_sauver = True
            points = client.points_pour_montant(vente.total)
            if points:
                client.points_fidelite = max(client.points_fidelite - points, 0)
                a_sauver = True
            if a_sauver:
                client.save()

        return vente


def _stock_de(produit):
    """Stock verrouillé d'un produit, ou None s'il n'a jamais été créé."""
    try:
        return Stock.objects.select_for_update().get(produit=produit)
    except Stock.DoesNotExist:
        return None


class RetourService:
    """
    Retours partiels : le client rend 1 bouteille sur 6.

    Le ticket d'origine n'est pas réécrit. Le stock est réintégré, la vente
    reste dans le chiffre d'affaires du jour, et le rapprochement en déduit le
    remboursement — c'est ce qui permet de rapprocher la caisse physique.
    """

    @staticmethod
    @transaction.atomic
    def enregistrer(vente_id, retours, motif='', utilisateur=None, mode_remboursement=None):
        """
        * ``retours`` : liste de ``{ligne_id, quantite, motif?}``.
        * Le motif est obligatoire : un retour sans justification est inexploitable.
        """
        try:
            vente = Vente.objects.select_for_update().get(id=vente_id)
        except Vente.DoesNotExist:
            raise ValidationError({"vente": "Vente introuvable."})

        if vente.statut == Vente.Statut.ANNULEE:
            raise ValidationError({"vente": "Impossible de retourner une vente annulée."})

        if not retours:
            raise ValidationError({"retours": "Indiquez au moins une ligne à retourner."})

        lignes = {l.id: l for l in LigneVente.objects.filter(vente=vente, pk__in=[
            r.get('ligne_id') for r in retours
        ])}
        manquantes = [r.get('ligne_id') for r in retours if r.get('ligne_id') not in lignes]
        if manquantes:
            raise ValidationError({
                "retours": f"Ces lignes n'appartiennent pas à la vente : {', '.join(map(str, manquantes))}."
            })

        # Le remboursement se fait par défaut dans le mode ayant servi à payer.
        if mode_remboursement is None:
            mode_remboursement = vente.mode_paiement
        if mode_remboursement not in dict(Vente.ModePaiement.choices):
            raise ValidationError({"mode_remboursement": f"Mode inconnu : {mode_remboursement}."})

        crees = []
        montant_total = Decimal('0.00')

        for entree in retours:
            ligne = lignes[entree['ligne_id']]
            try:
                quantite = int(entree.get('quantite') or 0)
            except (TypeError, ValueError):
                raise ValidationError({"retours": f"Quantité invalide pour « {ligne.produit.nom} »."})

            if quantite <= 0:
                raise ValidationError({"retours": f"Quantité invalide pour « {ligne.produit.nom} »."})

            restante = ligne.quantite_restante
            if quantite > restante:
                raise ValidationError({
                    "retours":
                        f"« {ligne.produit.nom} » : quantité retournable = {restante} "
                        f"(déjà {ligne.quantite_retournee} retourné(s) sur {ligne.quantite})."
                })

            motif_ligne = (entree.get('motif') or motif or '').strip()
            if not motif_ligne:
                raise ValidationError({
                    "retours": f"Le motif du retour de « {ligne.produit.nom} » est obligatoire."
                })

            # Remboursement au prorata de la remise dont a bénéficié la ligne :
            # le client ne récupère pas plus que ce qu'il a payé.
            prix_unitaire_net = (
                Decimal(ligne.sous_total) / ligne.quantite if ligne.quantite else Decimal('0')
            )
            montant = _money(prix_unitaire_net * quantite)

            stock = _stock_de(ligne.produit)
            if stock is None:
                raise ValidationError({
                    "stock": f"Aucun stock défini pour « {ligne.produit.nom} » : "
                             f"retour impossible afin de préserver l'intégrité des stocks."
                })

            quantite_bouteilles = quantite * max(int(ligne.contenance or 1), 1)
            stock.quantite += quantite_bouteilles
            stock.save()

            libelle_unite = f" ({ligne.produit.conditionnement_libelle})" if ligne.unite != Produit.UniteVente.BOUTEILLE else ""
            retour = RetourVente.objects.create(
                vente=vente,
                ligne=ligne,
                quantite=quantite,
                motif=motif_ligne[:255],
                mode_remboursement=mode_remboursement,
                montant_rembourse=montant,
                utilisateur=utilisateur or vente.utilisateur,
            )
            MouvementStock.objects.create(
                produit=ligne.produit,
                quantite=quantite_bouteilles,
                type_mouvement=MouvementStock.TypeMouvement.RETOUR,
                description=f"Retour {retour.reference_retour} — {vente.reference}{libelle_unite} : {motif_ligne[:120]}",
                reference_id=vente.reference,
                utilisateur=utilisateur or vente.utilisateur,
            )
            crees.append(retour)
            montant_total += montant

        vente.montant_retourne = _money(Decimal(vente.montant_retourne) + montant_total)
        vente.save(update_fields=['montant_retourne'])

        return crees, vente

    @staticmethod
    @transaction.atomic
    def annuler_retour(retour_id, utilisateur=None):
        """Annule un retour : le stock repart en sortie, la vente est de nouveau due."""
        try:
            retour = RetourVente.objects.select_for_update().select_related(
                'ligne__produit', 'vente'
            ).get(id=retour_id)
        except RetourVente.DoesNotExist:
            raise ValidationError({"retour": "Retour introuvable."})

        vente = Vente.objects.select_for_update().get(id=retour.vente_id)
        if vente.statut == Vente.Statut.ANNULEE:
            raise ValidationError({"retour": "La vente est annulée : retour sans objet."})

        stock = _stock_de(retour.ligne.produit)
        if stock is None:
            raise ValidationError({
                "stock": f"Aucun stock défini pour « {retour.ligne.produit.nom} »."
            })

        quantite_bouteilles = retour.quantite * max(int(retour.ligne.contenance or 1), 1)
        if stock.quantite < quantite_bouteilles:
            raise ValidationError({
                "stock": f"Stock insuffisant pour reprendre « {retour.ligne.produit.nom} » "
                         f"({stock.quantite} disponible, {quantite_bouteilles} nécessaire)."
            })

        stock.quantite -= quantite_bouteilles
        stock.save()
        MouvementStock.objects.create(
            produit=retour.ligne.produit,
            quantite=-quantite_bouteilles,
            type_mouvement=MouvementStock.TypeMouvement.SORTIE,
            description=f"Annulation retour {retour.reference_retour} ({vente.reference})",
            reference_id=vente.reference,
            utilisateur=utilisateur or retour.utilisateur,
        )

        vente.montant_retourne = max(
            _money(Decimal(vente.montant_retourne) - Decimal(retour.montant_rembourse)),
            Decimal('0.00'),
        )
        vente.save(update_fields=['montant_retourne'])
        retour.delete()
        return vente


class ReservationService:
    """
    Réservation avec acompte : « je réserve 12 bouteilles, je passe demain ».

    Aucun stock n'est réservé ni décrémenté tant que la réservation n'est pas
    soldée : c'est la vente déclenchée au retrait qui bouge le stock, le chiffre
    d'affaires et la fidélité. Le risque d'un oubli de pré-stockage est donc
    visible (la vente refusera si le stock a disparu entre-temps).
    """

    @staticmethod
    def _lignes_normalisees(lignes_data, type_client=None):
        if not lignes_data:
            raise ValidationError({"lignes": "La commande doit contenir au moins une ligne."})

        vus = set()
        lignes = []
        for entree in lignes_data:
            produit_id = entree.get('produit_id')
            try:
                quantite = int(entree.get('quantite') or 0)
            except (TypeError, ValueError):
                raise ValidationError({"lignes": "Quantité invalide."})
            if not produit_id or quantite <= 0:
                raise ValidationError({"lignes": "Produit et quantité valides obligatoires."})
            if produit_id in vus:
                raise ValidationError({"lignes": "Chaque produit ne peut apparaître qu'une seule fois."})
            vus.add(produit_id)
            try:
                produit = Produit.objects.select_for_update().get(id=produit_id)
            except Produit.DoesNotExist:
                raise ValidationError({"lignes": f"Produit {produit_id} introuvable."})
            unite, contenance, prix = VenteService._resolve_conditionnement(
                produit, entree.get('unite'), type_client=type_client,
            )
            lignes.append({
                'produit': produit, 'quantite': quantite, 'unite': unite,
                'contenance': contenance, 'prix_unitaire': prix,
            })
        return lignes

    @staticmethod
    def _remise_promotionnelle(lignes, type_client, taux_tva, tva_incluse):
        """
        Total des remises automatiques des campagnes en cours (aucun code à saisir).

        Le calcul est celui de `VenteService.creer_vente` : la réservation
        annonce donc le montant réellement dû, identique au prix affiché sur
        le site et à la somme encaissée au retrait. Les lignes, elles, gardent
        le tarif de base — c'est ce tarif que l'encaissement verrouille avant
        d'appliquer les mêmes campagnes.
        """
        total = Decimal('0')
        for ligne in lignes:
            contenance = ligne['contenance'] or 1
            quantite_bouteilles = ligne['quantite'] * contenance
            prix_bouteille = ligne['prix_unitaire'] / contenance
            candidats = VenteService.promotions_candidats(
                ligne['produit'], type_client=type_client,
                quantite=quantite_bouteilles,
            )
            _, _, promo = VenteService.calculer_remise_produit(
                ligne['produit'], prix_bouteille, quantite=quantite_bouteilles,
                type_client=type_client, promos=candidats,
            )
            if promo is None:
                continue
            remise_base = remise_promotion(
                promo, prix_bouteille, quantite_bouteilles,
            ) * contenance
            total += _base_vers_ttc(remise_base, taux_tva, tva_incluse)
        return total

    @staticmethod
    @transaction.atomic
    def creer(client_id, lignes_data, utilisateur, acompte=0, mode_acompte=None,
              date_expiration=None, note='', forcer_disponibilite=True,
              source=None, mode_reception=Reservation.ModeReception.RETRAIT,
              adresse_livraison='', compte_client=None):
        try:
            client = Client.objects.select_for_update().get(id=client_id)
        except Client.DoesNotExist:
            raise ValidationError({"client": "Client introuvable."})

        lignes = ReservationService._lignes_normalisees(
            lignes_data, type_client=client.type_client,
        )
        taux_tva, tva_incluse, _ = _regles_facture(timezone.localdate())
        if mode_reception not in dict(Reservation.ModeReception.choices):
            raise ValidationError({'mode_reception': 'Mode de réception invalide.'})
        adresse_livraison = (adresse_livraison or '').strip()
        if mode_reception == Reservation.ModeReception.LIVRAISON and not adresse_livraison:
            raise ValidationError({'adresse_livraison': 'Une adresse est obligatoire pour une livraison.'})
        brut_total = sum((
            _base_vers_ttc(l['prix_unitaire'], taux_tva, tva_incluse) * l['quantite']
            for l in lignes
        ), Decimal('0'))
        remises = ReservationService._remise_promotionnelle(
            lignes, client.type_client, taux_tva, tva_incluse,
        )
        montant_total = _money(max(brut_total - remises, Decimal('0')))

        # La réservation engage le caissier : on refuse d'engager plus que le
        # stock réellement disponible après les autres réservations actives.
        if forcer_disponibilite:
            reservations_actives = (
                LigneReservation.objects.filter(
                    produit_id__in=[ligne['produit'].pk for ligne in lignes],
                    reservation__statut__in=(Reservation.Statut.EN_ATTENTE, Reservation.Statut.ACOMPTE),
                )
                .filter(
                    Q(reservation__date_expiration__isnull=True)
                    | Q(reservation__date_expiration__gte=timezone.localdate())
                )
                .values('produit_id')
                .annotate(quantite=Sum(F('quantite') * F('contenance')))
            )
            quantites_reservees = {
                ligne['produit_id']: ligne['quantite'] for ligne in reservations_actives
            }
            # Chargement groupé des stocks sous verrou : une seule requête au
            # lieu d'une requête par ligne de commande.
            stocks = {
                s.produit_id: s
                for s in Stock.objects.filter(
                    produit_id__in=[l['produit'].pk for l in lignes],
                ).select_for_update()
            }
            for l in lignes:
                stock = stocks.get(l['produit'].pk)
                if stock is None:
                    raise ValidationError({
                        "stock": f"Aucun stock défini pour « {l['produit'].nom} »."
                    })
                besoin = l['quantite'] * l['contenance']
                disponible = stock.quantite - quantites_reservees.get(l['produit'].pk, 0)
                if disponible < besoin:
                    raise ValidationError({
                        "stock": f"Stock insuffisant pour commander {besoin} × "
                                 f"« {l['produit'].nom} » ({disponible} disponible après commandes)."
                    })

        if date_expiration is None:
            date_expiration = timezone.localdate() + timedelta(days=jours_validite_reservation())

        acompte = _money(_to_decimal(acompte))
        if acompte < 0:
            raise ValidationError({"acompte": "L'acompte ne peut pas être négatif."})
        if acompte > montant_total:
            raise ValidationError({
                "acompte": f"L'acompte ({acompte}) dépasse le montant de la commande ({montant_total})."
            })
        if acompte > 0 and not mode_acompte:
            raise ValidationError({"mode_acompte": "Indiquez le mode d'encaissement de l'acompte."})
        if mode_acompte and mode_acompte not in dict(Vente.ModePaiement.choices):
            raise ValidationError({"mode_acompte": f"Mode inconnu : {mode_acompte}."})

        source = source or Reservation.Source.INTERNE
        reservation = Reservation.objects.create(
            client=client,
            source=source,
            compte_client=compte_client,
            validation_statut=(
                Reservation.ValidationStatut.A_VALIDER
                if source == Reservation.Source.SITE else None
            ),
            montant_total=montant_total,
            taux_tva=taux_tva,
            tva_incluse=tva_incluse,
            montant_acompte=acompte,
            mode_reception=mode_reception,
            adresse_livraison=adresse_livraison,
            date_expiration=date_expiration,
            note=note.strip()[:255],
            utilisateur=utilisateur,
            statut=Reservation.Statut.ACOMPTE if acompte > 0 else Reservation.Statut.EN_ATTENTE,
        )
        for l in lignes:
            LigneReservation.objects.create(
                reservation=reservation,
                produit=l['produit'],
                quantite=l['quantite'],
                unite=l['unite'],
                contenance=l['contenance'],
                prix_unitaire=_base_vers_ttc(
                    l['prix_unitaire'], taux_tva, tva_incluse,
                ),
            )

        if acompte > 0:
            ReservationService._enregistrer_acompte(reservation, acompte, mode_acompte, utilisateur)

        return reservation

    @staticmethod
    @transaction.atomic
    def valider(reservation_id, utilisateur):
        """Accepte une commande du site sans l'encaisser ni modifier le stock."""
        try:
            reservation = Reservation.objects.select_for_update().get(id=reservation_id)
        except Reservation.DoesNotExist:
            raise ValidationError({'reservation': 'Commande introuvable.'})

        if reservation.source != Reservation.Source.SITE:
            raise ValidationError({'reservation': 'Seules les commandes du site nécessitent une validation.'})
        if reservation.validation_statut != Reservation.ValidationStatut.A_VALIDER:
            raise ValidationError({'validation_statut': 'Cette commande a déjà été traitée.'})
        if reservation.statut not in (Reservation.Statut.EN_ATTENTE, Reservation.Statut.ACOMPTE):
            raise ValidationError({'reservation': 'Cette commande n’est plus active.'})
        if reservation.date_expiration and reservation.date_expiration < timezone.localdate():
            raise ValidationError({'reservation': 'Cette commande a expiré.'})

        reservation.validation_statut = Reservation.ValidationStatut.VALIDEE
        reservation.validation_par = utilisateur
        reservation.validation_le = timezone.now()
        reservation.motif_refus = ''
        reservation.save(update_fields=[
            'validation_statut', 'validation_par', 'validation_le', 'motif_refus', 'updated_at',
        ])
        # La facture part au client une fois la commande acceptée. L'échec de
        # l'e-mail ne doit jamais faire échouer la validation elle-même : si le
        # destinataire manque, un simple avertissement est noté en console.
        try:
            envoyer_facture_commande(reservation)
        except Exception:  # noqa: BLE001
            logger.exception('Échec de l’envoi de la facture de la commande %s', reservation.reference)
        return reservation

    @staticmethod
    @transaction.atomic
    def refuser(reservation_id, utilisateur, motif):
        """Refuse une commande du site et libère son stock réservé."""
        try:
            reservation = Reservation.objects.select_for_update().get(id=reservation_id)
        except Reservation.DoesNotExist:
            raise ValidationError({'reservation': 'Commande introuvable.'})

        if reservation.source != Reservation.Source.SITE:
            raise ValidationError({'reservation': 'Seules les commandes du site nécessitent une validation.'})
        if reservation.validation_statut != Reservation.ValidationStatut.A_VALIDER:
            raise ValidationError({'validation_statut': 'Cette commande a déjà été traitée.'})
        if reservation.statut not in (Reservation.Statut.EN_ATTENTE, Reservation.Statut.ACOMPTE):
            raise ValidationError({'reservation': 'Cette commande n’est plus active.'})
        if reservation.montant_acompte > 0:
            raise ValidationError({
                'reservation': 'Cette commande comporte un acompte : traitez son remboursement avant de la refuser.'
            })

        motif = (motif or '').strip()
        if len(motif) < 5:
            raise ValidationError({'motif': 'Expliquez le refus en 5 caractères minimum.'})

        reservation.validation_statut = Reservation.ValidationStatut.REFUSEE
        reservation.validation_par = utilisateur
        reservation.validation_le = timezone.now()
        reservation.motif_refus = motif[:255]
        reservation.statut = Reservation.Statut.ANNULEE
        reservation.save(update_fields=[
            'validation_statut', 'validation_par', 'validation_le', 'motif_refus',
            'statut', 'updated_at',
        ])
        return reservation

    @staticmethod
    @transaction.atomic
    def _enregistrer_acompte(reservation, montant, mode, utilisateur):
        """
        Trace l'acompte dans la caisse du jour.

        L'argent versé est physiquement dans le tiroir : il doit apparaître
        dans les encaissements de la journée. Il est donc écrit comme un encaissement rattaché à la
        réservation, et le crédit consenti est ajouté au solde dû du client
        pour que le plafond de crédit reste vrai.
        """
        if mode == Vente.ModePaiement.CREDIT:
            client = Client.objects.select_for_update().get(id=reservation.client_id)
            if client.max_credit <= 0:
                raise ValidationError({"mode_acompte": "Ce client n'est pas autorisé à acheter à crédit."})
            if Decimal(client.solde_du) + montant > Decimal(client.max_credit):
                raise ValidationError({
                    "mode_acompte": f"Plafond de crédit dépassé ({client.max_credit}). "
                                    f"Solde dû actuel : {client.solde_du}."
                })
            client.solde_du = _money(Decimal(client.solde_du) + montant)
            client.save(update_fields=['solde_du'])

        Paiement.objects.create(
            reservation=reservation, mode=mode, montant=montant,
            reference=f"RES {reservation.reference}",
        )

    @staticmethod
    @transaction.atomic
    def encaisser(reservation_id, mode_paiement, montant=None, utilisateur=None, session=None,
                  paiements=None):
        """
        Solde une réservation : crée la vraie vente (stock, CA, fidélité) et
        encaisse le solde restant. L'acompte déjà versé est reporté sur la
        vente pour qu'aucun euro ne soit compté deux fois.
        """
        try:
            reservation = Reservation.objects.select_for_update().get(id=reservation_id)
        except Reservation.DoesNotExist:
            raise ValidationError({"reservation": "Commande introuvable."})

        if reservation.statut in (Reservation.Statut.SOLDEE, Reservation.Statut.ANNULEE):
            raise ValidationError({
                "reservation": f"Commande déjà {reservation.get_statut_display().lower()}."
            })

        from apps.ventes.paiements import est_actif
        if paiements is None and not est_actif(mode_paiement):
            raise ValidationError({
                "mode_paiement": "Ce moyen de paiement n'est plus accepté (paramètres de la caisse)."
            })

        if reservation.date_expiration and reservation.date_expiration < timezone.localdate():
            if reservation.statut != Reservation.Statut.EXPIREE:
                reservation.statut = Reservation.Statut.EXPIREE
                reservation.save(update_fields=['statut'])
            raise ValidationError({
                "reservation": f"Commande expirée le {reservation.date_expiration:%d/%m/%Y}."
            })

        if (
            reservation.source == Reservation.Source.SITE
            and reservation.validation_statut != Reservation.ValidationStatut.VALIDEE
        ):
            raise ValidationError({
                'validation_statut': 'Un vendeur ou un administrateur doit valider cette commande avant encaissement.'
            })

        lignes = list(reservation.lignes.all())
        if not lignes:
            raise ValidationError({"reservation": "Cette commande n'a aucune ligne."})

        acompte = _money(Decimal(reservation.montant_acompte))
        solde_du = _money(Decimal(reservation.montant_total) - acompte)

        if paiements is None and montant is not None:
            montant = _money(_to_decimal(montant))
            if montant < solde_du:
                raise ValidationError({
                    "montant": f"Le solde restant à payer est de {solde_du}."
                })
            if montant > solde_du:
                raise ValidationError({
                    "montant": f"Le trop-perçu de {montant - solde_du} n'est pas un encaissement. "
                               f"Enregistrez {solde_du} et rendez la monnaie."
                })
            paiements = None  # la vente couvre exactement le solde

        vente = VenteService.creer_vente(
            client_id=reservation.client_id,
            mode_paiement=mode_paiement,
            lignes_data=[
                {'produit_id': l.produit_id, 'quantite': l.quantite, 'unite': l.unite}
                for l in lignes
            ],
            utilisateur=utilisateur or reservation.utilisateur,
            paiements=paiements,
            session=session,
            acompte_anticipe=acompte,
            tarifs_verrouilles={
                ligne.produit_id: ligne.prix_unitaire for ligne in lignes
            },
            tarifs_verrouilles_ttc=reservation.taux_tva is not None,
            taux_tva_facture=reservation.taux_tva,
            tva_incluse_facture=reservation.tva_incluse,
        )

        reservation.vente = vente
        reservation.statut = Reservation.Statut.SOLDEE
        reservation.save(update_fields=['vente', 'statut'])
        return vente, reservation

    @staticmethod
    @transaction.atomic
    def annuler(reservation_id):
        try:
            reservation = Reservation.objects.select_for_update().get(id=reservation_id)
        except Reservation.DoesNotExist:
            raise ValidationError({"reservation": "Commande introuvable."})
        if reservation.statut == Reservation.Statut.SOLDEE:
            raise ValidationError({
                "reservation": "Commande soldée : annulez la vente liée, pas la commande."
            })
        reservation.statut = Reservation.Statut.ANNULEE
        reservation.save(update_fields=['statut'])
        return reservation

    @staticmethod
    def expirer_les_retardes():
        """Bascule en EXPIREE les réservations dont la date de retrait est dépassée."""
        return Reservation.objects.filter(
            statut__in=[Reservation.Statut.EN_ATTENTE, Reservation.Statut.ACOMPTE],
            date_expiration__lt=timezone.localdate(),
        ).update(statut=Reservation.Statut.EXPIREE)


class ReglementService:
    """Encaissement d'un règlement client (rembourse le solde dû d'un compte)."""

    @staticmethod
    @transaction.atomic
    def enregistrer(client_id, montant, mode, utilisateur, reference_facture='', note=''):
        try:
            client = Client.objects.select_for_update().get(id=client_id)
        except Client.DoesNotExist:
            raise ValidationError({"client": "Client introuvable."})

        montant = Decimal(montant)
        if montant <= 0:
            raise ValidationError({"montant": "Le montant doit être strictement positif."})
        if montant > Decimal(client.solde_du):
            raise ValidationError({
                "montant": f"Le règlement dépasse le solde dû ({client.solde_du})."
            })

        reglement = ReglementClient.objects.create(
            client=client,
            montant=montant,
            mode=mode,
            reference_facture=reference_facture,
            note=note,
            utilisateur=utilisateur,
        )
        client.solde_du = max(Decimal(client.solde_du) - montant, Decimal('0.00'))
        client.save()
        return reglement

    @staticmethod
    @transaction.atomic
    def supprimer(reglement_id):
        """Supprime un règlement saisi par erreur et rétablit le solde dû du client."""
        try:
            reglement = ReglementClient.objects.select_for_update().select_related('client').get(id=reglement_id)
        except ReglementClient.DoesNotExist:
            raise ValidationError({"reglement": "Règlement introuvable."})
        client = reglement.client
        client.solde_du = Decimal(client.solde_du) + Decimal(reglement.montant)
        client.save()
        reglement.delete()
        return client


class CaisseService:
    """
    Session de caisse et clôture journalière.

    Deux notions distinctes, souvent confondues et qu'on sépare ici :

    * la **session** est le poste de travail : on l'ouvre avec un fond déclaré,
      on encaisse dessus, on la clôture en comptant les espèces ;
    * le rapprochement journalier consolide les paiements et remboursements
      pour archiver la clôture des sessions.

    Les chiffres proviennent des lignes d'encaissement (``Paiement``) et non
    du champ ``Vente.mode_paiement`` : c'est la seule façon d'être exact dès
    qu'une vente est réglée en plusieurs modes.
    """

    # ------------------------------------------------------------------
    # Session de caisse
    # ------------------------------------------------------------------
    @staticmethod
    def session_ouverte(utilisateur, jour=None):
        """Session de caisse en cours pour ce caissier (None s'il n'a pas ouvert)."""
        if utilisateur is None or not getattr(utilisateur, 'is_authenticated', False):
            return None
        jour = jour or timezone.localdate()
        return (
            SessionCaisse.objects.filter(
                date_ventes=jour,
                utilisateur=utilisateur,
                statut=SessionCaisse.Statut.OUVERTE,
            )
            .order_by('-date_ouverture')
            .first()
        )

    @staticmethod
    def session_requise_et_absente(utilisateur, jour=None):
        """
        Renvoie la session si l'encaissement est bloqué faute d'ouverture.
        `None` signifie : on peut encaisser.
        """
        if not session_caisse_requise():
            return None
        if CaisseService.session_ouverte(utilisateur, jour) is not None:
            return None
        return {'bloque': True, 'message': "Ouvrez votre caisse avant d'encaisser."}

    @staticmethod
    @transaction.atomic
    def ouvrir(jour, utilisateur, fonds_initial=0, note=''):
        """
        Ouvre la caisse du caissier pour la journée en déclarant le fond de
        caisse. Idempotent : rouvrir une caisse déjà ouverte renvoie la session
        existante au lieu d'en créer une seconde.
        """
        jour = jour or timezone.localdate()
        fonds_initial = _money(_to_decimal(fonds_initial))
        if fonds_initial < 0:
            raise ValidationError({"fonds_initial": "Le fond de caisse ne peut pas être négatif."})

        try:
            return SessionCaisse.objects.select_for_update().get(
                date_ventes=jour, utilisateur=utilisateur, statut=SessionCaisse.Statut.OUVERTE
            )
        except SessionCaisse.DoesNotExist:
            pass

        return SessionCaisse.objects.create(
            date_ventes=jour,
            statut=SessionCaisse.Statut.OUVERTE,
            utilisateur=utilisateur,
            date_ouverture=timezone.now(),
            fonds_de_caisse=fonds_initial,
            note=note.strip()[:255],
        )

    # ------------------------------------------------------------------
    # Rapport
    # ------------------------------------------------------------------
    @staticmethod
    def rapport_du_jour(jour):
        """
        Calcule en direct les statistiques des ventes PAYEE de la journée `jour`
        (date Python). Aucun état n'est modifié.

        Les encaissements sont lus sur ``Paiement`` (donc exacts en paiement
        mixte) et les retours sont soustraits pour donner le CA net, qui est la
        seule valeur comparable au comptage physique de la caisse.
        """
        ventes = Vente.objects.filter(statut=Vente.Statut.PAYEE, date_vente__date=jour)
        lignes = LigneVente.objects.filter(vente__in=ventes)

        paiements = Paiement.objects.filter(vente__in=ventes)
        par_mode = dict(
            paiements.values_list('mode').annotate(total=Sum('montant'))
        )
        # Filet de sécurité : une vente antérieure au suivi des encaissements
        # (import, script, reprise de données) n'a pas de Paiement. Sans ce
        # repli, le rapport afficherait 0 au lieu du montant réellement encaissé.
        ventes_hors_encaissements = ventes.exclude(paiements__isnull=False)
        par_mode_repli = dict(
            ventes_hors_encaissements.values_list('mode_paiement').annotate(total=Sum('total'))
        )
        for mode, montant in par_mode_repli.items():
            par_mode[mode] = par_mode.get(mode, Decimal('0')) + montant

        nb_par_mode = dict(
            ventes.values_list('mode_paiement').annotate(nb=Count('id'))
        )
        retours = RetourVente.objects.filter(vente__in=ventes)
        par_mode_rembourse = dict(
            retours.values_list('mode_remboursement').annotate(total=Sum('montant_rembourse'))
        )

        # Acomptes de réservation : de l'argent réellement versé, dans le tiroir
        # du jour, mais hors ventes. On les additionne au mode concerné pour que
        # le comptage des espèces tombe juste.
        acomptes_par_mode = dict(
            Paiement.objects.filter(
                reservation__isnull=False, vente__isnull=True, created_at__date=jour
            )
            .values_list('mode')
            .annotate(total=Sum('montant'))
        )
        acomptes_total = sum((Decimal(v) for v in acomptes_par_mode.values()), Decimal('0'))

        agrege_bouteilles = lignes.aggregate(
            bouteilles=Coalesce(Sum(F('quantite') * F('contenance')), 0, output_field=IntegerField())
        )['bouteilles']
        agrege_unites = lignes.aggregate(
            articles=Coalesce(Sum('quantite'), 0, output_field=IntegerField())
        )['articles']
        remise_totale = lignes.aggregate(
            remise=Coalesce(Sum('remise'), 0, output_field=DecimalField(max_digits=12, decimal_places=2))
        )['remise']
        remise_manuelle = lignes.aggregate(
            remise=Coalesce(Sum('remise_manuelle'), 0, output_field=DecimalField(max_digits=12, decimal_places=2))
        )['remise']
        ca_total = ventes.aggregate(
            total=Coalesce(Sum('total'), 0, output_field=DecimalField(max_digits=12, decimal_places=2))
        )['total']
        montant_rembourse = retours.aggregate(
            total=Coalesce(Sum('montant_rembourse'), 0, output_field=DecimalField(max_digits=12, decimal_places=2))
        )['total']

        def _brut(mode):
            return (
                Decimal(par_mode.get(mode, 0) or 0)
                + Decimal(acomptes_par_mode.get(mode, 0) or 0)
            )

        def _caisse(mode):
            return _money(_brut(mode))

        top_produits = (
            lignes.values('produit__nom', 'produit__millesime')
            .annotate(nb=Sum(F('quantite') * F('contenance')), ca=Sum('sous_total'))
            .order_by('-nb')[:6]
        )
        par_vendeur = (
            ventes.values('utilisateur__username')
            .annotate(nb=Count('id'), total=Sum('total'))
            .order_by('-total')
        )
        motifs_remise = (
            ventes.exclude(remise_manuelle_totale=0)
            .values('motif_remise', 'utilisateur__username')
            .annotate(nb=Count('id'), montant=Sum('remise_manuelle_totale'))
            .order_by('-montant')[:10]
        )
        reservations_du_jour = Reservation.objects.filter(date_creation__date=jour).count()

        return {
            'jour': jour,
            'ca_total': _money(Decimal(ca_total or 0)),
            'ca_especes': _caisse(Vente.ModePaiement.ESPECES),
            'ca_mobile_money': _caisse(Vente.ModePaiement.MOBILE_MONEY),
            'ca_carte': _caisse(Vente.ModePaiement.CARTE),
            'ca_credit': _caisse(Vente.ModePaiement.CREDIT),
            'acompte_caisses': _money(acomptes_total),
            'ca_rembourse': _money(Decimal(montant_rembourse or 0)),
            'ca_net': _money(Decimal(ca_total or 0) - Decimal(montant_rembourse or 0)),
            'rembourse_especes': _money(Decimal(par_mode_rembourse.get(Vente.ModePaiement.ESPECES, 0) or 0)),
            'rembourse_mobile_money': _money(Decimal(par_mode_rembourse.get(Vente.ModePaiement.MOBILE_MONEY, 0) or 0)),
            'rembourse_carte': _money(Decimal(par_mode_rembourse.get(Vente.ModePaiement.CARTE, 0) or 0)),
            'rembourse_credit': _money(Decimal(par_mode_rembourse.get(Vente.ModePaiement.CREDIT, 0) or 0)),
            # Net par moyen : ce que le poste a réellement gardé après les
            # remboursements. Un template ne doit pas recalculer de l'argent.
            'net_especes': _money(_brut(Vente.ModePaiement.ESPECES)
                                  - Decimal(par_mode_rembourse.get(Vente.ModePaiement.ESPECES, 0) or 0)),
            'net_mobile_money': _money(_brut(Vente.ModePaiement.MOBILE_MONEY)
                                      - Decimal(par_mode_rembourse.get(Vente.ModePaiement.MOBILE_MONEY, 0) or 0)),
            'net_carte': _money(_brut(Vente.ModePaiement.CARTE)
                                - Decimal(par_mode_rembourse.get(Vente.ModePaiement.CARTE, 0) or 0)),
            'net_credit': _money(_brut(Vente.ModePaiement.CREDIT)
                                 - Decimal(par_mode_rembourse.get(Vente.ModePaiement.CREDIT, 0) or 0)),
            'nb_par_mode': nb_par_mode,
            'nb_tickets': ventes.count(),
            'nb_articles': agrege_bouteilles,
            'nb_unites': agrege_unites,
            'nb_retours': retours.count(),
            'nb_reservations': reservations_du_jour,
            'remise_totale': _money(Decimal(remise_totale or 0)),
            'remise_manuelle_totale': _money(Decimal(remise_manuelle or 0)),
            'motifs_remise': motifs_remise,
            'top_produits': top_produits,
            'par_vendeur': par_vendeur,
        }

    @staticmethod
    def rapport_session(session):
        """Chiffre d'une session de caisse précise (post de travail)."""
        if session is None:
            return None
        ventes = Vente.objects.filter(session=session, statut=Vente.Statut.PAYEE)
        paiements = Paiement.objects.filter(vente__in=ventes)
        lignes = LigneVente.objects.filter(vente__in=ventes)
        par_mode = dict(paiements.values_list('mode').annotate(total=Sum('montant')))
        retours = RetourVente.objects.filter(vente__in=ventes)
        return {
            'session': session,
            'nb_tickets': ventes.count(),
            'ca_total': _money(ventes.aggregate(t=Coalesce(Sum('total'), 0, output_field=DecimalField(max_digits=12, decimal_places=2)))['t'] or 0),
            'ca_especes': _money(Decimal(par_mode.get(Vente.ModePaiement.ESPECES, 0) or 0)),
            'ca_mobile_money': _money(Decimal(par_mode.get(Vente.ModePaiement.MOBILE_MONEY, 0) or 0)),
            'ca_carte': _money(Decimal(par_mode.get(Vente.ModePaiement.CARTE, 0) or 0)),
            'ca_credit': _money(Decimal(par_mode.get(Vente.ModePaiement.CREDIT, 0) or 0)),
            'ca_rembourse': _money(retours.aggregate(t=Coalesce(Sum('montant_rembourse'), 0, output_field=DecimalField(max_digits=12, decimal_places=2)))['t'] or 0),
            'nb_articles': lignes.aggregate(a=Coalesce(Sum('quantite'), 0, output_field=IntegerField()))['a'],
            'remise_manuelle_totale': _money(lignes.aggregate(r=Coalesce(Sum('remise_manuelle'), 0, output_field=DecimalField(max_digits=12, decimal_places=2)))['r'] or 0),
        }

    # ------------------------------------------------------------------
    # Clôture
    # ------------------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def cloturer(jour, utilisateur, fonds_de_caisse=0, especes_reel=None, note=''):
        """
        Archive le rapport du jour et clôture le poste de `utilisateur`.

        Idempotent : une nouvelle clôture du même caissier réécrit la précédente,
        ce qui permet de corriger un comptage d'espèces saisi de travers.

        La clôture porte sur le poste de celui qui la déclenche. Les sessions des
        autres caissiers ne sont pas refermées à sa place : le fonds d'espèces
        leur appartient, et le comptage réel d'un tiers n'a aucun sens.
        `sessions_restantes` liste celles qui restent ouvertes pour que le
        responsable puisse les faire clôturer.
        """
        # `ouvrir` applique la même valeur par défaut : sans elle, un appel sans
        # date explicite filtrait sur `date_ventes=None` et levait une
        # IntegrityError sur la colonne NOT NULL — la clôture depuis la caisse
        # était alors inutilisable.
        jour = jour or timezone.localdate()
        rapport = CaisseService.rapport_du_jour(jour)
        fonds_de_caisse = _money(_to_decimal(fonds_de_caisse))
        especes_reel = _money(_to_decimal(especes_reel, str(rapport['ca_especes']))) \
            if especes_reel is not None else _money(Decimal(rapport['ca_especes']))
        attendu = fonds_de_caisse + _money(Decimal(rapport['ca_especes']))
        ecart = _money(especes_reel - attendu)
        maintenant = timezone.now()

        def _champs():
            return {
                'date_cloture': maintenant,
                'ca_especes': rapport['ca_especes'],
                'ca_mobile_money': rapport['ca_mobile_money'],
                'ca_carte': rapport['ca_carte'],
                'ca_credit': rapport['ca_credit'],
                'ca_total': rapport['ca_total'],
                'ca_rembourse': rapport['ca_rembourse'],
                'ca_net': rapport['ca_net'],
                'nb_tickets': rapport['nb_tickets'],
                'nb_articles': rapport['nb_articles'],
                'nb_retours': rapport['nb_retours'],
                'remise_totale': rapport['remise_totale'],
                'remise_manuelle_totale': rapport['remise_manuelle_totale'],
                'fonds_de_caisse': fonds_de_caisse,
                'especes_reel': especes_reel,
                'ecart': ecart,
                'note': note,
            }

        # Un caissier a au plus un poste par jour : on réutilise son poste ouvert
        # s'il en a un, sinon on archive la clôture sur une nouvelle ligne.
        poste = SessionCaisse.objects.filter(
            date_ventes=jour,
            utilisateur=utilisateur,
            statut=SessionCaisse.Statut.OUVERTE,
        ).first()

        if poste is not None:
            for champ, valeur in _champs().items():
                setattr(poste, champ, valeur)
            poste.statut = SessionCaisse.Statut.FERMEE
            poste.save()
            session = poste
        else:
            session, _ = SessionCaisse.objects.update_or_create(
                date_ventes=jour,
                utilisateur=utilisateur,
                statut=SessionCaisse.Statut.FERMEE,
                defaults=_champs(),
            )

        session.sessions_restantes = list(
            SessionCaisse.objects.filter(
                date_ventes=jour, statut=SessionCaisse.Statut.OUVERTE,
            ).select_related('utilisateur')
        )
        return session
