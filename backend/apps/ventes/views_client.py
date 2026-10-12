import json
from datetime import timedelta

from django import forms
from django.conf import settings
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from rest_framework.exceptions import ValidationError

from apps.clients.models import Client
from apps.produits.models import Produit
from apps.ventes.models import MessageClient, Reservation
from apps.ventes.services import ReservationService


class CommandeClientForm(forms.Form):
    nom = forms.CharField(max_length=100)
    prenom = forms.CharField(max_length=100)
    telephone = forms.CharField(max_length=20)
    email = forms.EmailField(required=False)
    adresse = forms.CharField(required=False, max_length=1000)
    mode_reception = forms.ChoiceField(
        choices=Reservation.ModeReception.choices,
        initial=Reservation.ModeReception.RETRAIT,
    )
    date_expiration = forms.DateField(
        required=False,
        initial=lambda: timezone.localdate() + timedelta(days=7),
        widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
    )
    note = forms.CharField(required=False, max_length=255)
    lignes = forms.CharField(widget=forms.HiddenInput())

    def clean_date_expiration(self):
        date = self.cleaned_data.get('date_expiration')
        if date and date < timezone.localdate():
            raise forms.ValidationError('La date de retrait doit être aujourd’hui ou plus tard.')
        return date

    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get('mode_reception') == Reservation.ModeReception.LIVRAISON
            and not cleaned.get('adresse', '').strip()
        ):
            self.add_error('adresse', 'Une adresse est obligatoire pour une livraison.')
        return cleaned


class MessageClientForm(forms.Form):
    nom = forms.CharField(max_length=150)
    telephone = forms.CharField(max_length=30, required=False)
    email = forms.EmailField(required=False)
    sujet = forms.CharField(max_length=150)
    message = forms.CharField(max_length=3000, widget=forms.Textarea)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('telephone', '').strip() and not cleaned.get('email', '').strip():
            raise forms.ValidationError('Indiquez un téléphone ou un email pour recevoir une réponse.')
        return cleaned


def catalogue_public():
    return list(
        Produit.objects.filter(statut=True, stock__quantite__gt=0)
        .select_related('categorie', 'stock').order_by('nom')
    )


def _page_commande(request, form=None, erreur='', status=200):
    produits = catalogue_public()
    for produit in produits:
        produit.image_publique = produit.image.url if produit.image else ''
        produit.categorie_nom = produit.categorie.nom if produit.categorie_id else ''
    return render(request, 'public/commande_client.html', {
        'produits': produits,
        'form': form or CommandeClientForm(),
        'erreur': erreur,
        'confirmation': request.session.pop('commande_confirmation', None),
        'societe': settings.SOCIETE,
    }, status=status)


@csrf_protect
@require_http_methods(['GET', 'POST'])
def commande_client(request):
    if request.method == 'GET':
        return _page_commande(request)

    form = CommandeClientForm(request.POST)
    if not form.is_valid():
        return _page_commande(
            request, form, 'Vérifiez les coordonnées et les articles sélectionnés.', status=400,
        )

    try:
        lignes = json.loads(form.cleaned_data['lignes'])
        if not isinstance(lignes, list) or not lignes:
            raise ValueError
        lignes_data = []
        for ligne in lignes:
            produit_id = int(ligne['produit_id'])
            quantite = int(ligne['quantite'])
            if quantite < 1:
                raise ValueError
            lignes_data.append({'produit_id': produit_id, 'quantite': quantite, 'unite': 'BOUTEILLE'})
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _page_commande(
            request, form, 'Le panier est invalide. Recomposez votre commande.', status=400,
        )

    data = form.cleaned_data
    try:
        with transaction.atomic():
            client = Client.objects.filter(telephone=data['telephone'].strip()).order_by('id').first()
            if client is None:
                client = Client.objects.create(
                    nom=data['nom'].strip(),
                    prenom=data['prenom'].strip(),
                    telephone=data['telephone'].strip(),
                    email=data['email'].strip(),
                    adresse=data['adresse'].strip(),
                )
            else:
                champs = []
                if not client.email and data['email']:
                    client.email = data['email'].strip()
                    champs.append('email')
                if not client.adresse and data['adresse']:
                    client.adresse = data['adresse'].strip()
                    champs.append('adresse')
                if champs:
                    client.save(update_fields=champs)

            reservation = ReservationService.creer(
                client_id=client.pk,
                lignes_data=lignes_data,
                utilisateur=None,
                date_expiration=data['date_expiration'],
                note=data['note'].strip(),
                source=Reservation.Source.SITE,
                mode_reception=data['mode_reception'],
                adresse_livraison=data['adresse'].strip(),
            )
    except ValidationError as exc:
        detail = getattr(exc, 'detail', {})
        messages = [
            str(message)
            for value in detail.values()
            for message in (value if isinstance(value, (list, tuple)) else [value])
        ] if isinstance(detail, dict) else [str(detail)]
        return _page_commande(
            request, form, messages[0] if messages else 'La commande n’a pas pu être enregistrée.',
            status=400,
        )

    request.session['commande_confirmation'] = {
        'reference': reservation.reference,
        'montant': str(reservation.montant_total),
    }
    return redirect('commande-client')


@csrf_protect
@require_http_methods(['GET', 'POST'])
def contact_client(request):
    succes = request.session.pop('message_confirmation', False)
    form = MessageClientForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        MessageClient.objects.create(**form.cleaned_data)
        request.session['message_confirmation'] = True
        return redirect('contact-client')
    return render(request, 'public/contact_client.html', {
        'form': form,
        'succes': succes,
        'societe': settings.SOCIETE,
    })