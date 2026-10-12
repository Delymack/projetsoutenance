from rest_framework import serializers
from apps.categories.serializers import CategorieSerializer
from apps.promotions.models import Promotion, PromotionProduit
from apps.produits.serializers import ProduitSerializer

class PromotionProduitSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromotionProduit
        fields = ['id', 'promotion', 'produit']


class PromotionSerializer(serializers.ModelSerializer):
    est_active = serializers.ReadOnlyField()
    regle_texte = serializers.ReadOnlyField()
    creneau_texte = serializers.ReadOnlyField()
    produits_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=ProduitSerializer.Meta.model.objects.all(),
        source='produits',
        write_only=True,
        required=False
    )
    categories_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CategorieSerializer.Meta.model.objects.all(),
        source='categories',
        write_only=True,
        required=False,
    )

    class Meta:
        model = Promotion
        fields = [
            'id', 'nom', 'description', 'type_promotion', 'valeur',
            'prix_promotionnel', 'quantite_achetee', 'quantite_offerte',
            'date_debut', 'date_fin', 'statut', 'est_active',
            'quantite_min', 'type_cible', 'code', 'limite_utilisation',
            'nb_utilisations', 'heure_debut', 'heure_fin', 'jours_semaine',
            'priorite', 'regle_texte', 'creneau_texte',
            'produits_ids', 'categories_ids', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'created_at', 'updated_at', 'est_active', 'regle_texte',
            'creneau_texte', 'nb_utilisations',
        ]

    def validate_code(self, value):
        if not value:
            return value
        value = value.strip().upper()
        qs = Promotion.objects.filter(code=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Ce code promo est déjà utilisé.')
        return value

    def validate(self, attrs):
        type_promotion = attrs.get('type_promotion', getattr(self.instance, 'type_promotion', None))
        valeur = attrs.get('valeur', getattr(self.instance, 'valeur', None))
        date_debut = attrs.get('date_debut', getattr(self.instance, 'date_debut', None))
        date_fin = attrs.get('date_fin', getattr(self.instance, 'date_fin', None))
        prix_promo = attrs.get(
            'prix_promotionnel', getattr(self.instance, 'prix_promotionnel', None)
        )
        quantite_achetee = attrs.get(
            'quantite_achetee', getattr(self.instance, 'quantite_achetee', 2)
        )
        quantite_offerte = attrs.get(
            'quantite_offerte', getattr(self.instance, 'quantite_offerte', 1)
        )
        heure_debut = attrs.get('heure_debut', getattr(self.instance, 'heure_debut', None))
        heure_fin = attrs.get('heure_fin', getattr(self.instance, 'heure_fin', None))
        jours = attrs.get('jours_semaine', getattr(self.instance, 'jours_semaine', ''))

        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError({
                'date_fin': 'La date de fin doit être postérieure ou égale à la date de début.'
            })

        if type_promotion in Promotion.TYPES_SUR_VALEUR:
            if valeur is not None and valeur <= 0:
                raise serializers.ValidationError({
                    'valeur': 'La valeur de la remise doit être strictement positive.'
                })
            if (
                valeur is not None
                and type_promotion == Promotion.TypePromotion.POURCENTAGE
                and valeur > 100
            ):
                raise serializers.ValidationError({
                    'valeur': 'Un pourcentage de remise ne peut pas dépasser 100 %.'
                })
        elif type_promotion == Promotion.TypePromotion.PRIX_PROMO:
            if prix_promo is None:
                raise serializers.ValidationError({
                    'prix_promotionnel': 'Le prix promotionnel est obligatoire pour ce type de remise.'
                })
            if prix_promo <= 0:
                raise serializers.ValidationError({
                    'prix_promotionnel': 'Le prix promotionnel doit être strictement positif.'
                })
        elif type_promotion == Promotion.TypePromotion.LOT:
            if quantite_achetee < 1:
                raise serializers.ValidationError({
                    'quantite_achetee': 'La quantité achetée doit être au moins de 1.'
                })
            if quantite_offerte < 1:
                raise serializers.ValidationError({
                    'quantite_offerte': 'La quantité offerte doit être au moins de 1.'
                })

        if heure_debut and not heure_fin:
            raise serializers.ValidationError({
                'heure_fin': "Renseignez l'heure de fin du créneau happy hour."
            })
        if heure_fin and not heure_debut:
            raise serializers.ValidationError({
                'heure_debut': "Renseignez l'heure de début du créneau happy hour."
            })
        if jours:
            invalides = [j for j in str(jours).split(',') if j.strip() not in '1234567']
            if invalides:
                raise serializers.ValidationError({
                    'jours_semaine': "Jours invalides : utilisez les numéros 1 (lundi) à 7 (dimanche)."
                })

        return attrs


class PromotionDetailSerializer(PromotionSerializer):
    produits = ProduitSerializer(many=True, read_only=True)
    categories = CategorieSerializer(many=True, read_only=True)

    class Meta(PromotionSerializer.Meta):
        fields = PromotionSerializer.Meta.fields + ['produits', 'categories']
