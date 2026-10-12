from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from apps.accounts.permissions import CanManageVentes, IsAdminOrReadOnly
from apps.promotions.filters import PromotionFilter
from apps.promotions.models import Promotion
from apps.promotions.serializers import PromotionDetailSerializer, PromotionSerializer
from apps.promotions.services import (
    chevauchements,
    historique_promotion,
    repartition_par_cible,
    repartition_par_type,
    statistiques_promotion,
)
from apps.produits.models import Produit


def _lire_entiers(param):
    """Transforme '1,2,3' en liste d'entiers (vide si non parseable)."""
    try:
        return [int(x) for x in str(param).split(',') if x.strip()]
    except (TypeError, ValueError):
        return []


class PromotionViewSet(viewsets.ModelViewSet):
    queryset = Promotion.objects.prefetch_related('produits', 'categories').all()
    permission_classes = [IsAdminOrReadOnly]
    filterset_class = PromotionFilter
    search_fields = ['nom', 'description', 'code', 'produits__nom', 'categories__nom']
    ordering_fields = ['date_debut', 'date_fin', 'valeur', 'priorite', 'nb_utilisations']
    ordering = ['-created_at']

    def get_permissions(self):
        # Le catalogue public affiche les campagnes en cours (badge de prix) :
        # la lecture doit pouvoir se faire sans compte, comme sur les produits.
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action in ['retrieve', 'list']:
            return PromotionDetailSerializer
        return PromotionSerializer

    @action(detail=True, methods=['get'], url_path='statistiques')
    def statistiques(self, request, pk=None):
        """
        GET /api/promotions/{id}/statistiques/

        Synthèse de la promotion (ventes, articles, remise totale, CA encaissé,
        panier moyen, taux de remise) et répartition des lignes remisées par
        mécanique de réduction et par segment de client.
        """
        promo = self.get_object()
        return Response({
            'promotion': {
                'id': promo.id,
                'nom': promo.nom,
                'type': promo.type_promotion,
                'regle': promo.regle_texte,
                'creneau': promo.creneau_texte,
                'cible': promo.get_type_cible_display(),
                'code': promo.code,
                'periode': {'debut': promo.date_debut, 'fin': promo.date_fin},
            },
            'global': statistiques_promotion(promo),
            'par_type': repartition_par_type(),
            'par_cible': repartition_par_cible(),
        })

    @action(detail=True, methods=['get'], url_path='historique')
    def historique(self, request, pk=None):
        """
        GET /api/promotions/{id}/historique/

        Dernières ventes payées ayant appliqué la promotion, avec le détail des
        lignes concernées (produit, quantité, remise accordée).
        """
        promo = self.get_object()
        lignes = historique_promotion(promo, limite=50)
        return Response({
            'count': len(lignes),
            'resultats': [
                {
                    'vente': ligne.vente.reference,
                    'date': ligne.vente.date_vente,
                    'client': ligne.vente.nom_client,
                    'type_client': ligne.vente.client.type_client if ligne.vente.client_id else None,
                    'produit': ligne.produit.nom,
                    'quantite': ligne.quantite,
                    'prix_unitaire': ligne.prix_unitaire,
                    'remise': ligne.remise,
                    'sous_total': ligne.sous_total,
                }
                for ligne in lignes
            ],
        })


class SimulerVentePromoView(viewsets.ViewSet):
    """
    POST /api/promotions/simuler/

    Simule le prix final de lignes de vente sans rien enregistrer : c'est le
    calcul exact appliqué par la caisse, exposé au frontend pour l'aperçu du
    ticket (quantité, segment de client).

    Corps attendu :
    {"client": 1, "lignes": [{"produit_id": 1, "quantite": 3}]}
    """

    permission_classes = [CanManageVentes]

    def list(self, request):
        from apps.clients.models import Client
        from apps.ventes.services import (
            VenteService, _base_vers_ttc, _regles_facture,
        )

        data = request.data if request.data else request.query_params
        code_promo = str(data.get('code_promo') or '').strip()
        if code_promo:
            return Response(
                {'erreur': 'Les codes promotionnels sont désactivés. Les promotions s’appliquent automatiquement.'},
                status=400,
            )

        client_id = data.get('client')
        lignes_in = data.get('lignes') or []

        type_client = None
        if client_id:
            client = Client.objects.filter(id=client_id).first()
            if client is None:
                return Response({'erreur': 'Client introuvable.'}, status=404)
            type_client = client.type_client
        if not lignes_in:
            return Response({'erreur': 'La simulation doit contenir au moins une ligne.'}, status=400)

        taux_tva, tva_incluse, _ = _regles_facture(timezone.localdate())
        total = Decimal('0')
        remise_totale = Decimal('0')
        lignes = []
        for ligne in lignes_in:
            produit = Produit.objects.filter(id=ligne.get('produit_id')).first()
            if produit is None:
                return Response({'erreur': f"Produit {ligne.get('produit_id')} introuvable."}, status=404)
            try:
                quantite = int(ligne.get('quantite') or 0)
                remise_manuelle = Decimal(str(ligne.get('remise_manuelle') or '0'))
            except (TypeError, ValueError, ArithmeticError):
                return Response({'erreur': 'Quantité ou remise invalide.'}, status=400)
            if quantite <= 0:
                return Response({'erreur': 'Quantité invalide.'}, status=400)
            if not produit.statut:
                return Response({'erreur': f'Le produit « {produit.nom} » n’est pas disponible.'}, status=400)
            if not remise_manuelle.is_finite() or remise_manuelle < 0:
                return Response({'erreur': 'La remise manuelle ne peut pas être négative.'}, status=400)

            unite, contenance, prix = VenteService._resolve_conditionnement(
                produit, ligne.get('unite'), type_client=type_client,
            )
            prix_ttc = _base_vers_ttc(prix, taux_tva, tva_incluse)
            quantite_bouteilles = quantite * contenance
            prix_bouteille = prix / contenance
            candidats = VenteService.promotions_candidats(
                produit, type_client=type_client, quantite=quantite_bouteilles,
            )
            _, _, promo = VenteService.calculer_remise_produit(
                produit, prix_bouteille, quantite=quantite_bouteilles,
                type_client=type_client, promos=candidats,
            )
            remise_promo_base = Decimal('0')
            if promo is not None:
                from apps.promotions.services import remise_promotion
                remise_promo_base = (remise_promotion(
                    promo, prix_bouteille, quantite_bouteilles,
                ) * contenance).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            remise_promo = _base_vers_ttc(
                remise_promo_base, taux_tva, tva_incluse,
            )

            brut_ligne = prix_ttc * quantite
            remise_manuelle = remise_manuelle.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if remise_manuelle + remise_promo > brut_ligne:
                return Response({'erreur': f'La remise dépasse le montant de la ligne « {produit.nom} ».'}, status=400)
            remise = remise_promo + remise_manuelle
            prix_ligne = (brut_ligne - remise).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            total += prix_ligne
            remise_totale += remise
            lignes.append({
                'produit_id': produit.pk,
                'produit': produit.nom,
                'quantite': quantite,
                'unite': unite,
                'prix_unitaire': prix_ttc,
                'brut_ligne': brut_ligne,
                'remise': remise,
                'prix_ligne': prix_ligne,
                'promotion': promo.nom if promo else None,
                'code': promo.code if promo else '',
            })

        return Response({
            'lignes': lignes,
            'total': total,
            'remise_totale': remise_totale,
            'type_client': type_client,
        })


class ApercuPrixPromotionView(viewsets.ViewSet):
    """
    GET/POST /api/promotions/apercu-prix/

    Aperçu dynamique du prix final d'un vin ciblé :
    prix unitaire initial, remise unitaire/totale, prix final,
    et validation de toutes les conditions (quantité min, segment, créneau, code).
    """

    permission_classes = [IsAdminOrReadOnly]

    def list(self, request):
        return self._traiter(request.query_params)

    def create(self, request):
        return self._traiter(request.data)

    def _traiter(self, data):
        from apps.promotions.services import calculer_apercu_prix
        produit_id = data.get('produit_id')
        if not produit_id:
            return Response({'erreur': 'Le paramètre produit_id est requis.'}, status=400)

        produit = Produit.objects.filter(id=produit_id).first()
        if not produit:
            return Response({'erreur': f"Produit {produit_id} introuvable."}, status=404)

        try:
            quantite = int(data.get('quantite', 1) or 1)
        except (ValueError, TypeError):
            quantite = 1

        type_client = data.get('type_client') or None
        code = (data.get('code') or '').strip().upper()

        promotion_id = data.get('promotion_id')
        if promotion_id:
            promo = Promotion.objects.filter(id=promotion_id).first()
            if not promo:
                return Response({'erreur': f"Promotion {promotion_id} introuvable."}, status=404)
        else:
            # Construction temporaire pour aperçu avant enregistrement
            type_promo = data.get('type_promotion') or Promotion.TypePromotion.POURCENTAGE
            try:
                valeur = Decimal(str(data.get('valeur', 0) or 0))
            except Exception:
                valeur = Decimal('0')
            try:
                prix_promo = Decimal(str(data.get('prix_promotionnel', 0) or 0)) if data.get('prix_promotionnel') else None
            except Exception:
                prix_promo = None
            try:
                qte_ach = int(data.get('quantite_achetee', 2) or 2)
                qte_off = int(data.get('quantite_offerte', 1) or 1)
            except Exception:
                qte_ach, qte_off = 2, 1
            try:
                qte_min = int(data.get('quantite_min', 1) or 1)
            except Exception:
                qte_min = 1
            type_cible = data.get('type_cible') or Promotion.TypeCible.TOUS

            from django.utils import timezone
            from datetime import timedelta
            promo = Promotion(
                nom="Aperçu",
                type_promotion=type_promo,
                valeur=valeur,
                prix_promotionnel=prix_promo,
                quantite_achetee=qte_ach,
                quantite_offerte=qte_off,
                quantite_min=qte_min,
                type_cible=type_cible,
                code=code,
                date_debut=timezone.now() - timedelta(days=1),
                date_fin=timezone.now() + timedelta(days=30),
                statut=True,
            )

        res = calculer_apercu_prix(promo, produit, quantite=quantite, type_client=type_client, code=code)
        res['devise'] = settings.SOCIETE.get('devise', 'Ar')
        return Response(res)


class ChevauchementsView(viewsets.ViewSet):
    """
    GET /api/promotions/chevauchements/

    Aide du formulaire admin : liste les promotions dont la période se
    superpose à [debut, fin] et qui partagent au moins un produit.

    Paramètres : produits=1,2,3&debut=AAAA-MM-JJTHH:MM&fin=AAAA-MM-JJTHH:MM
    &type=POURCENTAGE|MONTANT_FIXE|PRIX_PROMO|LOT&valeur=10
    &prix_promotionnel=&quantite_achetee=2&quantite_offerte=1&exclude=id
    """

    permission_classes = [IsAdminUser]

    def list(self, request):
        produits_ids = _lire_entiers(request.query_params.get('produits', ''))
        debut = request.query_params.get('debut')
        fin = request.query_params.get('fin')
        date_debut = parse_datetime(debut) if debut else None
        date_fin = parse_datetime(fin) if fin else None
        # Le formulaire admin envoie une heure locale sans fuseau : on la rend
        # « aware » pour éviter les warnings et les comparaisons mixtes avec
        # les datetimes enregistrés (toujours en UTC en base).
        if date_debut and timezone.is_naive(date_debut):
            date_debut = timezone.make_aware(date_debut)
        if date_fin and timezone.is_naive(date_fin):
            date_fin = timezone.make_aware(date_fin)
        if not produits_ids or not date_debut or not date_fin:
            return Response(
                {'erreur': 'Paramètres incomplets : produits, debut et fin requis.'},
                status=400,
            )
        if date_fin < date_debut:
            return Response({'erreur': 'La date de fin précède la date de début.'}, status=400)

        type_promotion = request.query_params.get('type') or Promotion.TypePromotion.POURCENTAGE
        try:
            valeur = Decimal(request.query_params.get('valeur', '0') or '0')
        except InvalidOperation:
            return Response({'erreur': 'Valeur de remise invalide.'}, status=400)

        prix_promotionnel = request.query_params.get('prix_promotionnel') or None
        if prix_promotionnel is not None:
            try:
                prix_promotionnel = Decimal(prix_promotionnel)
            except InvalidOperation:
                return Response({'erreur': 'Prix promotionnel invalide.'}, status=400)
        try:
            quantite_achetee = int(request.query_params.get('quantite_achetee', 2) or 2)
            quantite_offerte = int(request.query_params.get('quantite_offerte', 1) or 1)
        except (TypeError, ValueError):
            return Response({'erreur': 'Quantités de lot invalides.'}, status=400)

        tentatives = _lire_entiers(request.query_params.get('exclude', '') or '')
        exclure_id = tentatives[0] if tentatives else None

        produits = Produit.objects.filter(id__in=produits_ids)
        conflits = chevauchements(
            produits, date_debut, date_fin, type_promotion, valeur,
            prix_promotionnel=prix_promotionnel,
            quantite_achetee=quantite_achetee, quantite_offerte=quantite_offerte,
            exclure_id=exclure_id,
        )
        devise = settings.SOCIETE.get('devise', 'Ar')
        for conflit in conflits:
            conflit['remise_label'] = (
                f"-{conflit['valeur']} %"
                if conflit['type_promotion'] == Promotion.TypePromotion.POURCENTAGE
                else conflit['regle_texte'].replace('Ar', devise)
            )
            conflit['periode'] = (
                f"du {conflit['date_debut']:%d/%m/%Y %H:%M} "
                f"au {conflit['date_fin']:%d/%m/%Y %H:%M}"
            )
        return Response({'conflits': conflits})


class PrixProduitsView(viewsets.ViewSet):
    """
    GET /api/promotions/prix-produits/?ids=1,2,3&categories=1,2

    Prix de vente des produits pour l'aperçu de remise du formulaire admin.
    ``categories`` permet d'étendre l'aperçu à tous les vins des catégories
    ciblées, comme le fait réellement la promotion.
    """

    permission_classes = [IsAdminUser]

    def list(self, request):
        ids = _lire_entiers(request.query_params.get('ids', ''))
        categories = _lire_entiers(request.query_params.get('categories', ''))

        produits = Produit.objects.filter(id__in=ids)
        if categories:
            produits = produits | Produit.objects.filter(categorie__in=categories)
        produits = produits.distinct().values('id', 'nom', 'prix_vente', 'categorie__nom')
        return Response({'produits': list(produits)})
