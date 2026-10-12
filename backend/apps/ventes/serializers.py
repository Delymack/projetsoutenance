from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from apps.ventes.models import (
    Vente, LigneVente, Paiement, RetourVente, Reservation, LigneReservation, SessionCaisse,
)
from apps.produits.models import Produit
from apps.clients.models import Client
from apps.clients.serializers import ClientSerializer
from apps.accounts.serializers import UserSerializer
from apps.produits.serializers import ProduitSerializer
from apps.promotions.serializers import PromotionDetailSerializer
from apps.ventes.politiques import devise, plafond_remise, session_caisse_requise
from apps.ventes.factures import url_publique


class PaiementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Paiement
        fields = ['id', 'mode', 'montant', 'reference', 'created_at']
        read_only_fields = ['id', 'created_at']


class RetourVenteSerializer(serializers.ModelSerializer):
    produit_nom = serializers.CharField(source='ligne.produit.nom', read_only=True)

    class Meta:
        model = RetourVente
        fields = [
            'id', 'ligne', 'produit_nom', 'quantite', 'motif', 'mode_remboursement',
            'montant_rembourse', 'reference', 'utilisateur', 'date_retour',
        ]
        read_only_fields = [
            'id', 'produit_nom', 'montant_rembourse', 'utilisateur', 'date_retour',
        ]


class LigneVenteSerializer(serializers.ModelSerializer):
    produit_id = serializers.PrimaryKeyRelatedField(
        queryset=Produit.objects.all(), source='produit'
    )
    unite = serializers.CharField(required=False, default=Produit.UniteVente.BOUTEILLE)
    # Remise saisie au comptoir. Le plafond réel (rôle + brut de la ligne) est
    # appliqué par le service métier, qui refuse la vente si elle est dépassée.
    remise_manuelle = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, default=Decimal('0.00')
    )

    class Meta:
        model = LigneVente
        fields = [
            'id', 'produit_id', 'quantite', 'unite', 'prix_unitaire', 'remise',
            'remise_manuelle', 'sous_total',
        ]
        read_only_fields = ['id', 'prix_unitaire', 'remise', 'sous_total']

    def validate(self, attrs):
        produit = attrs.get('produit')
        quantite = attrs.get('quantite')

        if produit is not None and not produit.statut:
            raise serializers.ValidationError({
                'produit': f'Le produit "{produit.nom}" n\'est pas disponible pour la vente.'
            })

        if quantite is not None and quantite <= 0:
            raise serializers.ValidationError({
                'quantite': 'La quantité doit être supérieure à 0.'
            })

        if attrs.get('remise_manuelle', Decimal('0.00')) < 0:
            raise serializers.ValidationError({
                'remise_manuelle': 'La remise manuelle ne peut pas être négative.'
            })

        return attrs


class VenteSerializer(serializers.ModelSerializer):
    lignes = LigneVenteSerializer(many=True)
    utilisateur_id = serializers.PrimaryKeyRelatedField(read_only=True, source='utilisateur')
    # Encaissements multiples : 3 000 espèces + 2 000 Mvola.
    paiements = PaiementSerializer(many=True, required=False)
    motif_remise = serializers.CharField(required=False, allow_blank=True, max_length=255)
    session_id = serializers.PrimaryKeyRelatedField(
        queryset=SessionCaisse.objects.all(), source='session', required=False, allow_null=True
    )
    # Vente de client de passage : « client » peut être absent. Le nom libre
    # saisi au comptoir sert alors à faire figurer l'acheteur sur le ticket.
    client = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(), required=False, allow_null=True
    )
    client_libelle = serializers.CharField(required=False, allow_blank=True, max_length=150)
    # Référence d'un règlement simple (opérateur mobile money, chèque).
    reference_paiement = serializers.CharField(
        required=False, allow_blank=True, max_length=100, write_only=True
    )

    class Meta:
        model = Vente
        fields = [
            'id', 'reference', 'client', 'client_libelle', 'utilisateur_id', 'session_id',
            'date_vente', 'date_echeance', 'total', 'mode_paiement', 'statut',
            'remise_manuelle_totale', 'motif_remise', 'montant_retourne', 'acompte_anticipe',
            'lignes', 'paiements', 'reference_paiement', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'reference', 'date_vente', 'date_echeance', 'total', 'remise_manuelle_totale',
            'montant_retourne', 'acompte_anticipe', 'created_at', 'updated_at',
        ]

    def validate_lignes(self, lignes):
        if not lignes:
            raise serializers.ValidationError('La vente doit contenir au moins une ligne.')

        produits_vus = set()
        for ligne in lignes:
            produit = ligne.get('produit')
            if produit is None:
                continue

            if produit.pk in produits_vus:
                raise serializers.ValidationError('Chaque produit ne peut apparaître qu\'une seule fois dans une vente.')
            produits_vus.add(produit.pk)

        return lignes

    def validate(self, attrs):
        """Contrôle de l'enveloppe avant d'atteindre le service métier."""
        # Le champ code_promo a été retiré du modèle : on refuse toute tentative
        # de le renseigner, avec un message explicite côté caisse.
        code_promo = str(self.initial_data.get('code_promo') or '').strip()
        if code_promo:
            raise serializers.ValidationError({
                'code_promo': 'Les codes promotionnels sont désactivés. Les promotions s’appliquent automatiquement.'
            })
        motif = (attrs.get('motif_remise') or '').strip()
        if not motif:
            attrs['motif_remise'] = ''

        paiements = attrs.get('paiements')
        if paiements:
            modes = {p['mode'] for p in paiements}
            if len(modes) > 1 and attrs.get('mode_paiement'):
                attrs.pop('mode_paiement')
        # Vente anonyme : le nom libre ne sert que là, et le ticket le lit.
        if attrs.get('client'):
            attrs['client_libelle'] = ''
        return attrs


class VenteDetailSerializer(VenteSerializer):
    client = ClientSerializer(read_only=True)
    utilisateur = UserSerializer(read_only=True)
    session = serializers.SerializerMethodField()
    ticket_url = serializers.SerializerMethodField()
    whatsapp_url = serializers.SerializerMethodField()
    net_a_encaiser = serializers.SerializerMethodField()
    details_tva = serializers.SerializerMethodField()

    class LigneVenteDetailSerializer(serializers.ModelSerializer):
        produit = ProduitSerializer(read_only=True)
        promotion = PromotionDetailSerializer(read_only=True)

        class Meta:
            model = LigneVente
            fields = [
                'id', 'produit', 'quantite', 'unite', 'contenance', 'prix_unitaire',
                'remise', 'remise_manuelle', 'remise_promotion', 'sous_total',
                'quantite_bouteilles', 'quantite_retournee', 'quantite_restante',
                'promotion',
            ]

    lignes = LigneVenteDetailSerializer(many=True, read_only=True)
    paiements = PaiementSerializer(many=True, read_only=True)
    retours = RetourVenteSerializer(many=True, read_only=True)

    class Meta(VenteSerializer.Meta):
        fields = VenteSerializer.Meta.fields + [
            'utilisateur', 'session', 'net_a_encaiser', 'details_tva', 'retours',
            'ticket_url', 'whatsapp_url',
        ]

    def get_session(self, obj):
        if not obj.session_id:
            return None
        return {
            'id': obj.session.id,
            'statut': obj.session.statut,
            'date_ventes': obj.session.date_ventes,
            'fonds_de_caisse': str(obj.session.fonds_de_caisse),
        }

    def get_net_a_encaiser(self, obj):
        return str(obj.net_a_encaiser)

    def get_details_tva(self, obj):
        return obj.details_tva

    def get_ticket_url(self, obj):
        return f"/admin/ventes/vente/{obj.id}/facture/?format=ticket80"

    def get_whatsapp_url(self, obj):
        return build_whatsapp_url(obj, request=self.context.get('request'))

    @staticmethod
    def whatsapp_texte(vente, lien=None):
        return build_whatsapp_texte(vente, lien)


def build_whatsapp_texte(vente, lien=None):
    """
    Message de ticket prêt à envoyer par WhatsApp.

    Le client repart avec la trace de son achat sur son téléphone : c'est le
    canal réellement utilisé par la clientèle, bien plus qu'un e-mail.
    """
    s = settings.SOCIETE
    lignes = [
        f"*{s.get('nom', 'Boutique')}*",
        f"Reçu {vente.reference} — {vente.date_vente:%d/%m/%Y à %H:%M}",
        "",
    ]
    for ligne in vente.lignes.select_related('produit').all():
        unite = "" if ligne.unite == Produit.UniteVente.BOUTEILLE else f" ({ligne.unite.lower()})"
        lignes.append(f"• {ligne.quantite} × {ligne.produit.nom}{unite} : {ligne.sous_total}")
    lignes.append("")
    lignes.append(f"Total : *{vente.total} {s.get('devise', 'Ar')}*")
    details_tva = vente.details_tva
    if details_tva and details_tva['active']:
        lignes.append(
            f"{details_tva['libelle']} incluse : {details_tva['tva']} "
            f"{s.get('devise', 'Ar')}"
        )
    if vente.date_echeance:
        lignes.append(f"Échéance : {vente.date_echeance:%d/%m/%Y}")
    if vente.montant_retourne:
        lignes.append(f"Retours : -{vente.montant_retourne} {s.get('devise', 'Ar')}")
    lignes.append(f"Paiement : {vente.get_mode_paiement_display()}")
    lignes.append("Merci de votre visite !")
    if lien:
        lignes.append("")
        lignes.append(f"Vérifier le ticket : {lien}")
    return "\n".join(lignes)


def _telephone_whatsapp(client):
    """
    Normalise un numéro de téléphone pour wa.me (chiffres, indicatif pays).

    wa.me n'accepte que l'international « nu » : ni indicatif de pays, ni
    préfixe national. Un numéro togolais saisi « 034 00 00 000 » doit devenir
    22834000000 — un lien construit sur le numéro brut est un lien mort, le
    client tape dessus et rien ne s'ouvre. `telephone` n'étant pas formaté en
    base, la normalisation se fait ici plutôt que sur le formulaire.
    """
    brut = ''.join(c for c in (getattr(client, 'telephone', '') or '') if c.isdigit())
    if not brut:
        return ''
    if brut.startswith('00'):
        # Préfixe international déjà saisi : on ne rajoute pas 228.
        return brut[2:]
    if brut.startswith('0'):
        # Préfixe national (indicatif d'appel) : à retirer avant l'indicatif pays.
        brut = brut[1:]
    if len(brut) <= 9:
        return f'228{brut}'
    return brut



_url_publique = url_publique


def build_whatsapp_url(vente, request=None):
    """Lien wa.me pré-rempli vers le ticket WhatsApp du client."""
    from urllib.parse import quote

    # Vente anonyme : pas de numéro à qui écrire, donc pas de lien.
    telephone = _telephone_whatsapp(vente.client) if vente.client_id else ''
    if not telephone:
        return ''
    # `ticket80` et non `ticket` : c'est le seul format que la facture connaît,
    # et c'est le seul qui tienne dans un échange par messagerie.
    lien = f"{_url_publique(request)}/admin/ventes/vente/{vente.id}/facture/?format=ticket80"
    return f"https://wa.me/{telephone}?text={quote(build_whatsapp_texte(vente, lien))}"


class LigneReservationSerializer(serializers.ModelSerializer):
    produit_id = serializers.PrimaryKeyRelatedField(queryset=Produit.objects.all(), source='produit')
    # Nom du produit : l'historique client affiche des libellés, pas des ids.
    produit_nom = serializers.CharField(source='produit.nom', read_only=True)

    class Meta:
        model = LigneReservation
        fields = ['id', 'produit_id', 'produit_nom', 'quantite', 'unite', 'contenance', 'prix_unitaire']
        read_only_fields = ['id', 'produit_nom', 'contenance', 'prix_unitaire']


class ReservationSerializer(serializers.ModelSerializer):
    client = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all())
    lignes = LigneReservationSerializer(many=True)
    solde_du = serializers.SerializerMethodField()

    class Meta:
        model = Reservation
        fields = [
            'id', 'reference', 'source', 'client', 'statut', 'mode_reception', 'adresse_livraison',
            'montant_total', 'montant_acompte', 'taux_tva', 'tva_incluse',
            'solde_du', 'date_expiration', 'note', 'utilisateur', 'vente', 'lignes',
            'validation_statut', 'validation_par', 'validation_le', 'motif_refus',
            'date_creation', 'updated_at',
        ]
        read_only_fields = [
            'id', 'reference', 'source', 'statut', 'mode_reception', 'adresse_livraison',
            'montant_total', 'montant_acompte', 'taux_tva', 'tva_incluse',
            'utilisateur', 'vente', 'validation_statut', 'validation_par', 'validation_le',
            'motif_refus', 'date_creation', 'updated_at',
        ]

    def get_solde_du(self, obj):
        return str(obj.solde_du)


class ReservationDetailSerializer(ReservationSerializer):
    client = ClientSerializer(read_only=True)
    lignes = LigneReservationSerializer(many=True, read_only=True)
    # Lien public signé vers la facture de la commande, vide tant qu'elle n'est
    # pas validée par l'équipe. Le frontend l'affiche en « Voir la facture ».
    facture_url = serializers.SerializerMethodField()

    class Meta(ReservationSerializer.Meta):
        fields = list(ReservationSerializer.Meta.fields) + ['facture_url']

    def get_facture_url(self, obj):
        from apps.ventes.factures import facture_accessible, facture_url as url_facture

        if not facture_accessible(obj):
            return ''
        return url_facture(self.context.get('request'), obj)


class ReservationSiteLigneSerializer(serializers.Serializer):
    produit_id = serializers.PrimaryKeyRelatedField(
        queryset=Produit.objects.filter(statut=True),
        source='produit',
    )
    quantite = serializers.IntegerField(min_value=1)
    unite = serializers.ChoiceField(
        choices=Produit.UniteVente.choices,
        required=False,
        default=Produit.UniteVente.BOUTEILLE,
    )


class ReservationSiteSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=100)
    prenom = serializers.CharField(max_length=100)
    telephone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    mode_reception = serializers.ChoiceField(choices=Reservation.ModeReception.choices)
    adresse_livraison = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)
    lignes = ReservationSiteLigneSerializer(many=True, allow_empty=False)

    def validate_lignes(self, lignes):
        produits_vus = set()
        for ligne in lignes:
            produit_id = ligne['produit'].pk
            if produit_id in produits_vus:
                raise serializers.ValidationError(
                    'Chaque produit ne peut apparaître qu’une seule fois dans une commande.'
                )
            produits_vus.add(produit_id)
        return lignes

    def validate(self, attrs):
        if (
            attrs['mode_reception'] == Reservation.ModeReception.LIVRAISON
            and not attrs.get('adresse_livraison', '').strip()
        ):
            raise serializers.ValidationError({
                'adresse_livraison': 'Une adresse est obligatoire pour une livraison.'
            })
        attrs['telephone'] = attrs['telephone'].strip()
        attrs['nom'] = attrs['nom'].strip()
        attrs['prenom'] = attrs['prenom'].strip()
        if not attrs['telephone'] or not attrs['nom'] or not attrs['prenom']:
            raise serializers.ValidationError('Nom, prénom et téléphone sont obligatoires.')
        return attrs


class SessionCaisseSerializer(serializers.ModelSerializer):
    utilisateur = UserSerializer(read_only=True)
    attendu_en_caisse = serializers.SerializerMethodField()
    devise = serializers.SerializerMethodField()

    class Meta:
        model = SessionCaisse
        fields = [
            'id', 'date_ventes', 'statut', 'utilisateur', 'date_ouverture',
            'date_cloture', 'fonds_de_caisse', 'especes_reel', 'ecart',
            'attendu_en_caisse', 'ca_especes', 'ca_mobile_money', 'ca_carte',
            'ca_credit', 'ca_total', 'ca_rembourse', 'ca_net', 'nb_tickets',
            'nb_articles', 'nb_retours', 'remise_totale', 'remise_manuelle_totale',
            'note', 'devise',
        ]

    def get_attendu_en_caisse(self, obj):
        return str(obj.attendu_en_caisse)

    def get_devise(self, obj):
        return devise()


class ContexteCaisseSerializer(serializers.Serializer):
    """
    État du poste renvoyé à la caisse au chargement : session ouverte, droit à
    la remise manuelle, plafond du vendeur. Le JS n'a plus qu'à afficher.
    """
    session = SessionCaisseSerializer(read_only=True)
    session_requise = serializers.SerializerMethodField()
    peut_ouvrir = serializers.SerializerMethodField()
    peut_remettre = serializers.SerializerMethodField()
    plafond_remise_ligne = serializers.SerializerMethodField()
    remise_max_pct = serializers.SerializerMethodField()
    remise_motif_obligatoire = serializers.SerializerMethodField()
    devise = serializers.SerializerMethodField()
    conditions = serializers.SerializerMethodField()

    def get_session_requise(self, obj):
        return session_caisse_requise()

    def get_peut_ouvrir(self, obj):
        return obj['user'].has_management_access or obj['user'].is_superuser

    def get_remise_max_pct(self, obj):
        """Pourcentage maximal de remise manuelle accordable, ou None si illimité."""
        plafond = plafond_remise(obj['user'], Decimal('100'))
        return None if plafond is None else str(plafond)

    def get_peut_remettre(self, obj):
        # Aligné sur `plafond_remise` : un vendeur plafonné à 5 % peut bien
        # remiser, sa ligne n'est juste pas libre. Afficher « remise interdite »
        # au vendeur alors que le service accepte 5 % serait un faux refus.
        plafond = plafond_remise(obj['user'], Decimal('100'))
        return plafond is None or plafond > 0

    def get_remise_motif_obligatoire(self, obj):
        return True

    def get_plafond_remise_ligne(self, obj):
        # Montant de remise qu'un vendeur peut accorder sur une ligne de 10 000.
        plafond = plafond_remise(obj['user'], Decimal('10000'))
        return None if plafond is None else str(plafond)

    def get_devise(self, obj):
        return devise()

    def get_conditions(self, obj):
        return {
            'unites': dict(Produit.UniteVente.choices),
        }
