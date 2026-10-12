from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from apps.clients.models import Client, ReglementClient
from apps.clients.serializers import ClientSerializer, ReglementClientSerializer
from apps.accounts.permissions import CanManageClients
from apps.ventes.services import ReglementService

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    permission_classes = [CanManageClients]


class ReglementViewSet(viewsets.ModelViewSet):
    """Règlements clients : réduit le solde dû du client."""
    queryset = ReglementClient.objects.select_related('client', 'utilisateur').all()
    serializer_class = ReglementClientSerializer
    permission_classes = [CanManageClients]
    http_method_names = ['get', 'post', 'delete']

    def create(self, request, *args, **kwargs):
        serializer = ReglementClientSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Erreur lors de l'enregistrement du règlement.",
                "errors": serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)
        try:
            reglement = ReglementService.enregistrer(
                client_id=serializer.validated_data['client'].pk,
                montant=serializer.validated_data['montant'],
                mode=serializer.validated_data.get('mode', ReglementClient.Mode.ESPECES),
                utilisateur=request.user,
                reference_facture=serializer.validated_data.get('reference_facture', ''),
                note=serializer.validated_data.get('note', ''),
            )
            return Response({
                "success": True,
                "message": "Règlement enregistré.",
                "data": ReglementClientSerializer(reglement).data,
            }, status=status.HTTP_201_CREATED)
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Erreur lors de l'enregistrement du règlement.",
                "errors": e.detail,
            }, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, *args, **kwargs):
        """Supprime un règlement tout en rétablissant le solde dû du client."""
        try:
            ReglementService.supprimer(kwargs['pk'])
            return Response({
                "success": True,
                "message": "Règlement supprimé, solde du client rétabli.",
            }, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({
                "success": False,
                "message": "Suppression impossible.",
                "errors": e.detail,
            }, status=status.HTTP_400_BAD_REQUEST)