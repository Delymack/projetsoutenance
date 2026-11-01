from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.ventes.models import MessageClient


class ContactMessageThrottle(AnonRateThrottle):
    scope = 'contact_message'


class ContactMessageSerializer(serializers.Serializer):
    nom = serializers.CharField(max_length=150)
    telephone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    sujet = serializers.CharField(max_length=150)
    message = serializers.CharField(max_length=3000)

    def validate(self, attrs):
        attrs['nom'] = attrs['nom'].strip()
        attrs['telephone'] = attrs.get('telephone', '').strip()
        attrs['email'] = attrs.get('email', '').strip()
        attrs['sujet'] = attrs['sujet'].strip()
        attrs['message'] = attrs['message'].strip()
        if not attrs['nom'] or not attrs['sujet'] or not attrs['message']:
            raise serializers.ValidationError('Le nom, le sujet et le message sont obligatoires.')
        if not attrs['telephone'] and not attrs['email']:
            raise serializers.ValidationError({
                'contact': 'Indiquez un téléphone ou un email pour recevoir une réponse.'
            })
        return attrs


class ContactMessageDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageClient
        fields = ['id', 'nom', 'sujet', 'message', 'cree_le', 'reponse', 'repondu_le', 'statut']
        read_only_fields = fields


class ContactMessageView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ContactMessageThrottle]

    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsAuthenticated()]
        return super().get_permissions()

    def get(self, request):
        from apps.accounts.models import User

        if request.user.role != User.Role.CLIENT:
            return Response(
                {'success': False, 'message': 'Cette boîte de réception est réservée aux clients.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        messages = MessageClient.objects.filter(compte_client=request.user).order_by('-cree_le')
        return Response({
            'success': True,
            'data': ContactMessageDetailSerializer(messages, many=True).data,
        })

    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Vérifiez les informations de votre message.',
                'errors': serializer.errors,
            }, status=status.HTTP_400_BAD_REQUEST)

        from apps.accounts.models import User

        compte_client = (
            request.user
            if request.user.is_authenticated and request.user.role == User.Role.CLIENT
            else None
        )
        message = MessageClient.objects.create(
            **serializer.validated_data,
            compte_client=compte_client,
        )
        return Response({
            'success': True,
            'message': 'Votre message a bien été reçu.',
            'data': {
                'id': message.pk,
                'statut': message.statut,
                'cree_le': message.cree_le,
                'reponse': message.reponse,
                'repondu_le': message.repondu_le,
            },
        }, status=status.HTTP_201_CREATED)
