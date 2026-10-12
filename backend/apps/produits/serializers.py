from rest_framework import serializers
from apps.produits.models import Produit
from apps.categories.serializers import CategorieSerializer
from apps.stocks.models import Stock
from apps.clients.models import Client
from apps.promotions.services import (
    promotions_actives_qs,
    promotions_candidat_qs,
    meilleure_promotion,
)
from apps.parametres.services import get_config
from apps.parametres.tva import base_vers_ttc


class ProduitSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Produit
        fields = '__all__'
        read_only_fields = ['date_creation', 'updated_at']

    def get_image_url(self, obj):
        if obj.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class ProduitDetailSerializer(ProduitSerializer):
    categorie = CategorieSerializer(read_only=True)
    stock_quantite = serializers.SerializerMethodField()
    stock_etat = serializers.SerializerMethodField()
    promotion_active = serializers.SerializerMethodField()
    marge = serializers.SerializerMethodField()
    marge_pct = serializers.SerializerMethodField()
    # Conditionnement : la caisse a besoin du prix de l'unité réellement
    # vendue (bouteille, pack de 6, carton de 12) et de son équivalent au
    # verre unitaire pour comparer deux conditionnements.
    conditionnement_libelle = serializers.SerializerMethodField()
    bouteilles_par_unite = serializers.SerializerMethodField()
    prix_unitaire_vente = serializers.SerializerMethodField()
    prix_par_bouteille = serializers.SerializerMethodField()
    a_code_barre = serializers.SerializerMethodField()

    def get_conditionnement_libelle(self, obj):
        return str(obj.conditionnement_libelle)

    def get_bouteilles_par_unite(self, obj):
        return obj.bouteilles_par_unite

    def get_prix_unitaire_vente(self, obj):
        config = get_config()
        prix = obj.prix_unitaire_pour_client(self.context.get('type_client'))
        return str(base_vers_ttc(
            prix, config.get('ventes_tva') or 0,
            bool(config.get('ventes_tva_incluse')),
        ))

    def get_prix_par_bouteille(self, obj):
        config = get_config()
        prix_bouteille = obj.prix_bouteille_pour_client(
            self.context.get('type_client'),
        )
        return str(base_vers_ttc(
            prix_bouteille, config.get('ventes_tva') or 0,
            bool(config.get('ventes_tva_incluse')),
        ))

    def get_a_code_barre(self, obj):
        return bool(obj.code_barre)

    def get_stock_quantite(self, obj):
        try:
            return obj.stock.quantite
        except Stock.DoesNotExist:
            return 0

    def get_stock_etat(self, obj):
        try:
            return obj.stock.etat_stock
        except Stock.DoesNotExist:
            return 'RUPTURE'

    def get_promotion_active(self, obj):
        # Préchargé par le ViewSet (Prefetch -> to_attr) : zéro requête par objet.
        # Une promotion peut cibler le vin directement ou via sa catégorie.
        promos = getattr(obj, 'promotions_actives', None)
        if promos is None:
            # Repli : instance sérialisée hors du ViewSet (ex: imbriqué).
            promos = list(promotions_candidat_qs(obj))
        else:
            promos = list(promos) + list(
                getattr(obj, 'promotions_actives_categorie', None) or []
            )
        if not promos:
            return None
        # Même règle que VenteService.calculer_remise_produit :
        # parmi les promotions applicables, la plus avantageuse l'emporte.
        # Le catalogue peut recevoir le segment du client sélectionné en caisse.
        type_client = self.context.get('type_client') or Client.TypeClient.PARTICULIER
        prix_bouteille = obj.prix_bouteille_pour_client(type_client)
        meilleure, remise = meilleure_promotion(
            obj, prix_bouteille, quantite=1,
            type_client=type_client,
            promos=promos,
        )
        if meilleure is None:
            return None

        config = get_config()
        taux_tva = config.get('ventes_tva') or 0
        tva_incluse = bool(config.get('ventes_tva_incluse'))
        return {
            'nom': meilleure.nom,
            'type': meilleure.type_promotion,
            'valeur': meilleure.valeur,
            'remise_unitaire': base_vers_ttc(remise, taux_tva, tva_incluse),
            'prix_final': base_vers_ttc(
                prix_bouteille - remise, taux_tva, tva_incluse,
            ),
            'prix_promotionnel': meilleure.prix_promotionnel,
            'quantite_achetee': meilleure.quantite_achetee,
            'quantite_offerte': meilleure.quantite_offerte,
            'quantite_min': meilleure.quantite_min,
            'type_cible': meilleure.type_cible,
            'code': meilleure.code,
            'heure_debut': meilleure.heure_debut.strftime('%H:%M') if meilleure.heure_debut else None,
            'heure_fin': meilleure.heure_fin.strftime('%H:%M') if meilleure.heure_fin else None,
            'creneau_texte': meilleure.creneau_texte,
            'regle_texte': meilleure.regle_texte,
        }

    def get_marge(self, obj):
        return obj.marge_unitaire

    def get_marge_pct(self, obj):
        return obj.marge_pct
