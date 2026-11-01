import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import AnonRateThrottle

from apps.clients.models import Client
from apps.accounts.models import User
from apps.ventes.models import Vente, LigneVente, Paiement, RetourVente, Reservation, SessionCaisse
from apps.ventes.serializers import (
    VenteSerializer, VenteDetailSerializer, ReservationSerializer,
    ReservationDetailSerializer, ReservationSuiviSerializer,
    ReservationSiteSerializer,
    SessionCaisseSerializer, ContexteCaisseSerializer,
)
from apps.accounts.permissions import CanManageVentes, IsAdmin
from apps.ventes.services import (
    CaisseService, ReservationService, RetourService, VenteService,
)
from apps.ventes.filters import VenteFilter

logger = logging.getLogger(__name__)


class ReservationSiteThrottle(AnonRateThrottle):
    scope = 'reservation_site'


class VenteViewSet(viewsets.ModelViewSet):
    queryset = Vente.objects.select_related('client', 'utilisateur').prefetch_related('lignes__produit').all()
    permission_classes = [CanManageVentes]
    # Une vente ne se modifie ni ne se supprime directement : l'annulation
    # (qui restaure le stock) passe uniquement par l'action dédiée `annuler`.
    http_method_names = ['get', 'post']
    filterset_class = VenteFilter
    search_fields = ['reference', 'client__nom', 'client__prenom']
    ordering_fields = ['date_vente', 'total', 'montant_retourne']
    ordering = ['-date_vente']

    def get_queryset(self):
        # Les encaissements, retours et totaux nets sont lus à chaque sérialisation
        # d'une vente : on les charge d'un coup.
        return super().get_queryset().select_related('session').prefetch_related(
            'paiements', 'retours', 'lignes__produit', 'lignes__promotion', 'lignes__retours',
        )

    def get_serializer_class(self):
        if self.action in ['retrieve', 'list']:
            return VenteDetailSerializer
        return VenteSerializer

    def get_permissions(self):
        # L'annulation restaure le stock : elle doit rester réservée aux admins,
        # même si les vendeurs sont autorisés à créer une vente par POST.
        if self.action in ('annuler', 'retour', 'annuler_retour'):
            return [IsAdmin()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        """
        Surcharge de la création pour utiliser VenteService et gérer la transaction.
        """
        input_serializer = VenteSerializer(data=request.data)
        if not input_serializer.is_valid():
            # Même enveloppe que pour les erreurs du service : cohérence de l'API.
            return Response({
                "success": False,
                "message": "Erreur lors de la création de la vente.",
                "errors": input_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        validated_data = input_serializer.validated_data
        # Client absent = vente de client de passage (nom libre facultatif).
        client = validated_data.get('client')
        client_id = client.pk if client else None
        mode_paiement = validated_data.get('mode_paiement', Vente.ModePaiement.ESPECES)
        lignes_data = [
            {
                'produit_id': ligne['produit'].pk,
                'quantite': ligne['quantite'],
                'unite': ligne.get('unite'),
                'remise_manuelle': ligne.get('remise_manuelle'),
            }
            for ligne in validated_data['lignes']
        ]

        # Caisse non ouverte : on refuse d'encaisser plutôt que de laisser
        # des ventes sans fonds déclaré derrière elles.
        blocage = CaisseService.session_requise_et_absente(request.user)
        if blocage:
            return Response({
                "success": False,
                "message": "Caisse fermée.",
                "errors": {"session": blocage['message']}
            }, status=status.HTTP_409_CONFLICT)

        try:
            vente = VenteService.creer_vente(
                client_id=client_id,
                mode_paiement=mode_paiement,
                lignes_data=lignes_data,
                utilisateur=request.user,
                paiements=validated_data.get('paiements') or None,
                motif_remise=validated_data.get('motif_remise', ''),
                session=validated_data.get('session') or CaisseService.session_ouverte(request.user),
                client_libelle=validated_data.get('client_libelle', ''),
                reference_paiement=validated_data.get('reference_paiement', ''),
            )
            serializer = VenteDetailSerializer(vente, context=self.get_serializer_context())
            return Response({
                "success": True,
                "message": "Vente créée avec succès.",
                "data": serializer.data
            }, status=status.HTTP_201_CREATED)
            
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Erreur lors de la création de la vente.",
                "errors": e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as e:
            logger.error("Violation d'intégrité lors de la création d'une vente : %s", e)
            return Response({
                "success": False,
                "message": "Conflit de données.",
                "errors": "Les données transmises entrent en conflit avec l'existant."
            }, status=status.HTTP_409_CONFLICT)
        except Exception as e:
            logger.exception("Erreur inattendue lors de la création d'une vente : %s", e)
            return Response({
                "success": False,
                "message": "Erreur serveur.",
                "errors": "Une erreur interne est survenue. Veuillez réessayer."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['post'], url_path='annuler')
    def annuler(self, request, pk=None):
        """
        Endpoint pour annuler une vente (nécessite d'être admin en principe).
        """
        try:
            vente = VenteService.annuler_vente(vente_id=pk, utilisateur=request.user)
            serializer = VenteDetailSerializer(vente, context=self.get_serializer_context())
            return Response({
                "success": True,
                "message": "Vente annulée avec succès.",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
            
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Erreur lors de l'annulation.",
                "errors": e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Erreur inattendue lors de l'annulation d'une vente : %s", e)
            return Response({
                "success": False,
                "message": "Erreur serveur.",
                "errors": "Une erreur interne est survenue. Veuillez réessayer."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['get', 'post'], url_path='retour')
    def retour(self, request, pk=None):
        """
        Retour / échange partiel.

        GET  : renvoie les lignes encore retournables (état de l'écran de retour).
        POST : enregistre le retour. Le ticket d'origine n'est pas réécrit, le
               stock est réintégré et le rapprochement de caisse déduit le remboursement.
        """
        vente = self.get_object()
        lignes = (
            LigneVente.objects.filter(vente=vente)
            .select_related('produit', 'produit__stock')
            .prefetch_related('retours')
        )
        if request.method == 'GET':
            return Response({
                'vente': VenteDetailSerializer(vente, context=self.get_serializer_context()).data,
                'retourne': vente.montant_retourne,
                'lignes': [
                    {
                        'ligne_id': l.id,
                        'produit_id': l.produit_id,
                        'nom': l.produit.nom,
                        'unite': l.unite,
                        'contenance': l.contenance,
                        'vendu': l.quantite,
                        'deja_retourne': l.quantite_retournee,
                        'retournable': l.quantite_restante,
                        'prix_unitaire': str(l.prix_unitaire),
                        'sous_total': str(l.sous_total),
                    }
                    for l in lignes
                ],
            })

        try:
            _, vente = RetourService.enregistrer(
                vente_id=pk,
                retours=request.data.get('retours') or [],
                motif=(request.data.get('motif') or '').strip(),
                utilisateur=request.user,
                mode_remboursement=request.data.get('mode_remboursement'),
            )
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Erreur lors du retour.",
                "errors": e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Erreur inattendue lors d'un retour de vente : %s", e)
            return Response({
                "success": False,
                "message": "Erreur serveur.",
                "errors": "Une erreur interne est survenue. Veuillez réessayer."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "success": True,
            "message": "Retour enregistré.",
            "data": VenteDetailSerializer(vente, context=self.get_serializer_context()).data,
        })

    @action(detail=True, methods=['post'], url_path='retours/annuler')
    def annuler_retour(self, request, pk=None):
        """Annule un retour : le stock repart en sortie et la vente est de nouveau due."""
        try:
            vente = RetourService.annuler_retour(
                retour_id=request.data.get('retour'), utilisateur=request.user
            )
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Erreur lors de l'annulation du retour.",
                "errors": e.detail
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "success": True,
            "message": "Retour annulé.",
            "data": VenteDetailSerializer(vente, context=self.get_serializer_context()).data,
        })


class ReservationViewSet(viewsets.ModelViewSet):
    """
    Réservations avec acompte : « je réserve 12 bouteilles, je passe demain ».
    """

    queryset = Reservation.objects.select_related('client', 'utilisateur', 'vente').prefetch_related('lignes__produit')
    serializer_class = ReservationSerializer
    permission_classes = [CanManageVentes]
    http_method_names = ['get', 'post']
    search_fields = ['reference', 'client__nom', 'client__prenom', 'note']
    ordering_fields = ['date_creation', 'montant_total', 'date_expiration']
    ordering = ['-date_creation']

    def get_serializer_class(self):
        return ReservationDetailSerializer if self.action in ('retrieve', 'list') else ReservationSerializer

    def get_permissions(self):
        if self.action == 'site':
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        from django.utils import timezone

        qs = super().get_queryset()
        if self.action != 'list':
            return qs

        statut = self.request.query_params.get('statut')
        if statut:
            return qs.filter(statut=statut)
        # Par défaut on ne remonte pas les réservations soldées : ce sont des
        # archives, pas du travail en cours.
        if self.request.query_params.get('inclure_soldees') != '1':
            qs = qs.exclude(statut=Reservation.Statut.SOLDEE)
        # File des réservations à servir aujourd'hui (caisse).
        if self.request.query_params.get('a_retirer') == '1':
            qs = qs.filter(
                statut__in=[Reservation.Statut.EN_ATTENTE, Reservation.Statut.ACOMPTE],
            ).filter(
                Q(date_expiration__isnull=True)
                | Q(date_expiration__gte=timezone.localdate())
            ).order_by('date_expiration', 'date_creation')
        return qs

    @action(
    detail=False,
    methods=['post'],
    url_path='site',
    permission_classes=[AllowAny],
    throttle_classes=[ReservationSiteThrottle],
    )
    def site(self, request):
        """Enregistre une réservation publique sans créer une vente ni encaisser."""
        serializer = ReservationSiteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Vérifiez les coordonnées et les articles sélectionnés.',
                'errors': serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            with transaction.atomic():
                client = Client.objects.filter(telephone=data['telephone']).order_by('id').first()
                if client is None:
                    client = Client.objects.create(
                        nom=data['nom'],
                        prenom=data['prenom'],
                        telephone=data['telephone'],
                        email=data.get('email', ''),
                        adresse=data.get('adresse_livraison', '').strip(),
                    )
                else:
                    champs = []
                    if not client.email and data.get('email'):
                        client.email = data['email']
                        champs.append('email')
                    if (
                        data['mode_reception'] == Reservation.ModeReception.LIVRAISON
                        and not client.adresse
                    ):
                        client.adresse = data['adresse_livraison'].strip()
                        champs.append('adresse')
                    if champs:
                        client.save(update_fields=champs)

                reservation = ReservationService.creer(
                    client_id=client.pk,
                    lignes_data=[
                        {
                            'produit_id': ligne['produit'].pk,
                            'quantite': ligne['quantite'],
                            'unite': ligne['unite'],
                        }
                        for ligne in data['lignes']
                    ],
                    utilisateur=None,
                    note=data.get('note', ''),
                    source=Reservation.Source.SITE,
                    mode_reception=data['mode_reception'],
                    adresse_livraison=data.get('adresse_livraison', '').strip(),
                    compte_client=(
                        request.user
                        if request.user.is_authenticated and request.user.role == User.Role.CLIENT
                        else None
                    ),
                )
        except ValidationError as exc:
            return Response({
                'success': False,
                'message': 'La commande n’a pas pu être enregistrée.',
                'errors': exc.detail,
            }, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as exc:
            logger.warning('Conflit lors de la réservation publique : %s', exc)
            return Response({
                'success': False,
                'message': 'Conflit de données.',
                'errors': 'Réessayez la commande.',
            }, status=status.HTTP_409_CONFLICT)
        except Exception:
            logger.exception('Erreur inattendue lors de la réservation publique.')
            return Response({
                'success': False,
                'message': 'Erreur serveur.',
                'errors': 'La commande n’a pas pu être enregistrée.',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'success': True,
            'message': 'Commande enregistrée. Le paiement sera effectué au retrait ou à la livraison.',
            'data': ReservationDetailSerializer(
                reservation, context=self.get_serializer_context()
            ).data,
        }, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=['get'],
        url_path='suivi/(?P<reference>[^/.]+)',
        permission_classes=[AllowAny],
        authentication_classes=[],
        throttle_classes=[ReservationSiteThrottle],
    )
    def suivi(self, request, reference):
        """Suivi public d'une commande passée sur le site, par sa référence.

        Le client du site n'a pas de compte : la référence sert de clé. Elle
        permet de retrouver l'état d'une commande (en attente, annulée,
        vendue) sans exiger de jeton, sans exposer la liste des réservations
        ni les données personnelles du client.
        """
        reservation = self.get_queryset().filter(reference__iexact=reference).first()
        if reservation is None:
            return Response({
                'success': False,
                'message': 'Commande introuvable.',
                'errors': {'reference': 'Aucune commande ne porte cette référence.'},
            }, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'success': True,
            'data': ReservationSuiviSerializer(
                reservation, context=self.get_serializer_context()
            ).data,
        })

    @action(
        detail=True,
        methods=['get'],
        url_path='facture',
        permission_classes=[AllowAny],
        authentication_classes=[],
    )
    def facture(self, request, pk=None):
        """Facture publique d'une commande validée, protégée par jeton signé.

        Le client du site n'a pas de compte : son lien est signé
        (``TimestampSigner``) pour être ouvrable sans authentification sans
        être devinable. Vérifiée dans le service, hors DRF, car la page n'est
        pas une réponse API mais un document HTML autonome.
        """
        from django.shortcuts import render

        from apps.parametres.tva import decomposition as _decomposition
        from apps.ventes.factures import (
            facture_accessible, url_publique, verifier_token,
        )

        try:
            reservation = self.queryset.select_related(
                'client', 'compte_client', 'validation_par',
            ).get(pk=pk)
        except Reservation.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Commande introuvable.',
                'errors': {'pk': 'Aucune commande ne porte cet identifiant.'},
            }, status=status.HTTP_404_NOT_FOUND)

        if not facture_accessible(reservation) or not verifier_token(
            reservation, request.query_params.get('t', ''),
        ):
            return Response({
                'success': False,
                'message': 'Lien de facture invalide ou expiré.',
                'errors': {'t': 'Le lien est invalide, ou la commande n’est plus consultable.'},
            }, status=status.HTTP_403_FORBIDDEN)

        return render(request, 'public/facture_reservation.html', {
            'reservation': reservation,
            'lignes': reservation.lignes.select_related('produit').all(),
            'detail_tva': _decomposition(
                reservation.montant_total, reservation.taux_tva, reservation.tva_incluse,
            ),
            'societe': getattr(settings, 'SOCIETE', {}) or {},
            'solde_a_payer': reservation.solde_du,
            'url_base': url_publique(request),
        })

    @action(
        detail=False,
        methods=['get'],
        url_path='mes-commandes',
        permission_classes=[IsAuthenticated],
    )
    def mes_commandes(self, request):
        """Commandes du compte client, avec compatibilité pour les anciennes réservations."""
        user = request.user
        criteres = Q(compte_client=user)
        anciens_contacts = Q()
        if user.email:
            anciens_contacts |= Q(client__email__iexact=user.email)
        contacts = {c for c in (user.telephone, user.username) if c}
        if contacts:
            anciens_contacts |= Q(client__telephone__in=contacts)

        if anciens_contacts:
            criteres |= Q(compte_client__isnull=True) & anciens_contacts

        reservations = (
            self.queryset.filter(criteres)
            .select_related('client', 'vente')
            .prefetch_related('lignes__produit')
            .order_by('-date_creation')
        )
        return Response({
            'success': True,
            'data': ReservationDetailSerializer(
                reservations, many=True, context=self.get_serializer_context()
            ).data,
        })

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Erreur lors de la création de la commande.",
                "errors": serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        try:
            reservation = ReservationService.creer(
                client_id=data['client'].pk,
                lignes_data=[
                    {'produit_id': l['produit'].pk, 'quantite': l['quantite'], 'unite': l.get('unite')}
                    for l in data['lignes']
                ],
                utilisateur=request.user,
                acompte=request.data.get('acompte', 0),
                mode_acompte=request.data.get('mode_acompte') or None,
                note=data.get('note', ''),
                date_expiration=data.get('date_expiration'),
                mode_reception=data.get('mode_reception', Reservation.ModeReception.RETRAIT),
                adresse_livraison=data.get('adresse_livraison', ''),
            )
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Erreur lors de la création de la commande.",
                "errors": e.detail,
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "success": True,
            "message": "Commande enregistrée.",
            "data": ReservationDetailSerializer(reservation, context=self.get_serializer_context()).data,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='valider')
    def valider(self, request, pk=None):
        """Accepte une commande du site, sans créer de vente ni encaissement."""
        try:
            reservation = ReservationService.valider(pk, request.user)
        except ValidationError as exc:
            return Response({
                'success': False,
                'message': 'La commande n’a pas pu être validée.',
                'errors': exc.detail,
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'success': True,
            'message': 'Commande validée. Elle peut maintenant être encaissée.',
            'data': ReservationDetailSerializer(
                reservation, context=self.get_serializer_context()
            ).data,
        })

    @action(detail=True, methods=['post'], url_path='refuser')
    def refuser(self, request, pk=None):
        """Refuse une commande du site, avec motif et libération de la réservation."""
        try:
            reservation = ReservationService.refuser(
                pk, request.user, request.data.get('motif', ''),
            )
        except ValidationError as exc:
            return Response({
                'success': False,
                'message': 'La commande n’a pas pu être refusée.',
                'errors': exc.detail,
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'success': True,
            'message': 'Commande refusée et réservation annulée.',
            'data': ReservationDetailSerializer(
                reservation, context=self.get_serializer_context()
            ).data,
        })

    @action(detail=True, methods=['post'], url_path='encaisser')
    def encaisser(self, request, pk=None):
        """Solde la réservation : la vente part, le stock bouge, le CA est réalisé."""
        blocage = CaisseService.session_requise_et_absente(request.user)
        if blocage:
            return Response({
                "success": False,
                "message": "Caisse fermée.",
                "errors": {"session": blocage['message']},
            }, status=status.HTTP_409_CONFLICT)
        try:
            vente, reservation = ReservationService.encaisser(
                reservation_id=pk,
                mode_paiement=request.data.get('mode_paiement', Vente.ModePaiement.ESPECES),
                montant=request.data.get('montant'),
                paiements=request.data.get('paiements') or None,
                utilisateur=request.user,
                session=CaisseService.session_ouverte(request.user),
            )
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Erreur lors de l'encaissement.",
                "errors": e.detail,
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "success": True,
            "message": "Commande soldée.",
            "data": VenteDetailSerializer(vente, context=self.get_serializer_context()).data,
            'reservation': ReservationDetailSerializer(reservation, context=self.get_serializer_context()).data,
        })

    @action(detail=True, methods=['post'], url_path='annuler')
    def annuler(self, request, pk=None):
        try:
            reservation = ReservationService.annuler(pk)
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Erreur lors de l'annulation.",
                "errors": e.detail,
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "success": True,
            "message": "Commande annulée.",
            "data": ReservationDetailSerializer(reservation, context=self.get_serializer_context()).data,
        })


class SessionCaisseViewSet(viewsets.ViewSet):
    """
    Poste de caisse : ouverture avec fonds déclaré, état de la session, clôture.
    """

    permission_classes = [CanManageVentes]

    def _serializer(self):
        return SessionCaisseSerializer

    @action(detail=False, methods=['get'], url_path='etat')
    def etat(self, request):
        """État de la session en cours : la caisse s'ouvre sur ce seul appel."""
        session = CaisseService.session_ouverte(request.user)
        return Response(ContexteCaisseSerializer(
            {'user': request.user, 'session': session}
        ).data)

    @action(detail=False, methods=['post'], url_path='ouvrir')
    def ouvrir(self, request):
        try:
            session = CaisseService.ouvrir(
                jour=None,
                utilisateur=request.user,
                fonds_initial=request.data.get('fonds_initial', 0),
                note=request.data.get('note', ''),
            )
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Ouverture impossible.",
                "errors": e.detail,
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "success": True,
            "message": "Caisse ouverte.",
            "session": SessionCaisseSerializer(session).data,
            "contexte": ContexteCaisseSerializer(
                {'user': request.user, 'session': session}
            ).data,
        })

    @action(detail=False, methods=['get'], url_path='rapport')
    def rapport(self, request):
        """Chiffre de la session en cours, mis à jour en continu pendant la journée."""
        session = CaisseService.session_ouverte(request.user)
        rapport = CaisseService.rapport_session(session)
        if rapport is None:
            return Response({'session': None, 'rapport': None})
        return Response({
            'session': SessionCaisseSerializer(session).data,
            'rapport': {
                'nb_tickets': rapport['nb_tickets'],
                'nb_articles': rapport['nb_articles'],
                'ca_total': str(rapport['ca_total']),
                'ca_especes': str(rapport['ca_especes']),
                'ca_mobile_money': str(rapport['ca_mobile_money']),
                'ca_carte': str(rapport['ca_carte']),
                'ca_credit': str(rapport['ca_credit']),
                'ca_rembourse': str(rapport['ca_rembourse']),
                'ca_net': str(rapport['ca_total'] - rapport['ca_rembourse']),
                'remise_manuelle_totale': str(rapport['remise_manuelle_totale']),
                'attendu_en_caisse': str(session.attendu_en_caisse + rapport['ca_especes']),
            },
        })

    @action(detail=False, methods=['post'], url_path='cloturer')
    def cloturer(self, request):
        """
        Clôture de poste depuis la caisse elle-même.

        Le caissier compte sa caisse et saisit le total réel : c'est le seul
        moyen d'obtenir un écart fiable, puisque personne d'autre ne peut
        manipuler le tiroir. Une vente laissée en attente côté navigateur n'est
        pas un problème ici : le stock n'est décrémenté qu'à la validation.
        """
        try:
            session = CaisseService.cloturer(
                jour=request.data.get('date') or None,
                utilisateur=request.user,
                fonds_de_caisse=request.data.get('fonds_de_caisse', 0),
                especes_reel=request.data.get('especes_reel'),
                note=(request.data.get('note') or '').strip(),
            )
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Clôture impossible.",
                "errors": e.detail,
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Erreur inattendue lors de la clôture de session : %s", e)
            return Response({
                "success": False,
                "message": "Erreur serveur.",
                "errors": "Une erreur interne est survenue. Veuillez réessayer.",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        restants = getattr(session, 'sessions_restantes', [])
        message = f"Clôture enregistrée : {session.ca_total} de CA, écart de {session.ecart}."
        if restants:
            noms = ', '.join(str(p.utilisateur.username) for p in restants)
            message += f" Postes encore ouverts : {noms}."
        return Response({
            "success": True,
            "message": message,
            "session": SessionCaisseSerializer(session).data,
            "sessions_restantes": [
                {'id': p.id, 'utilisateur': p.utilisateur.username} for p in restants
            ],
        })
