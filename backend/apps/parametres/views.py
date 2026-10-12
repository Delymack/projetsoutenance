"""Console d'administration des paramètres + comptes + sauvegardes.

Une seule page, ``/admin/parametres/``, regroupe ce qui se configurait à
trois endroits : les paramètres, les comptes et la sauvegarde de la base. Les
onglets partagent la même URL et la même charte graphique ; un lien direct
vers un onglet passe par ``?onglet=``.
"""

import csv
import io
import json

from django.contrib import messages
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from apps.accounts.console import lister_utilisateurs
from apps.parametres import sauvegarde as service_sauvegarde
from apps.parametres.defaults import DEFAULTS
from apps.parametres.models import Sauvegarde
from apps.parametres.services import (
    build_sections, erreur_entries, export_dict, import_config, purge_journal, save_config,
)

#: Onglets qui n'ont pas de section de paramètres (ils ont leur propre panneau).
ONGLETS_SPECIAUX = ('utilisateurs', 'sauvegarde', 'journal')


def _client_ip(request):
    fwd = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _onglet_autorise(request):
    onglet = (request.GET.get('onglet') or request.POST.get('onglet') or '').strip().lower()
    if onglet in ONGLETS_SPECIAUX:
        return onglet
    return ''


def _peut_gerer(request):
    """Les paramètres et la base ne se configurent qu'entre/admin."""
    return bool(request.user.is_superuser or request.user.has_management_access)


@method_decorator(staff_member_required, name='dispatch')
class ParametresView(TemplateView):
    template_name = 'admin/parametres/index.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(admin.site.each_context(self.request))
        ctx['sections'] = build_sections()
        ctx['onglet'] = _onglet_autorise(self.request)
        ctx['utilisateurs'] = lister_utilisateurs(self.request)
        ctx['url_ajout_utilisateur'] = _url_ajout_utilisateur()
        sauvegardes, volume = service_sauvegarde.resume()
        ctx['sauvegardes'] = sauvegardes
        ctx['sauvegarde_volume'] = volume
        ctx['sauvegarde_autorisee'] = _peut_gerer(self.request)
        return ctx

    def post(self, request):
        # Les onglets Utilisateurs et Sauvegarde ont leurs propres actions.
        onglet = _onglet_autorise(request)
        if onglet == 'sauvegarde':
            return creer_sauvegarde(request)

        entries = {}
        for d in DEFAULTS:
            cle = d[1]
            if d[3] == 'BOOL':
                entries[cle] = '1' if request.POST.get(cle) else '0'
            elif d[3] == 'MULTI':
                # Une liste ne se déclare pas : son absence vaut « vide ».
                entries[cle] = request.POST.getlist(cle)
            elif cle in request.POST:
                entries[cle] = request.POST.get(cle).strip()

        if request.POST.get('purger') == '1':
            n = purge_journal()
            messages.success(request, f'Journal purgé ({n} entrée(s) supprimée(s)).')
            return redirect('parametres:index')

        if not _peut_gerer(request):
            messages.error(request, "Seuls un administrateur ou un gestionnaire peuvent modifier les paramètres.")
            return redirect('parametres:index')

        erreurs = erreur_entries(entries)
        if erreurs:
            for message in erreurs:
                messages.error(request, message)
            return redirect(f'{reverse_index()}?onglet=' + (onglet or 'ventes'))

        nb = save_config(entries, user=request.user, ip=_client_ip(request))
        if nb:
            messages.success(request, f'{nb} paramètre(s) enregistré(s).')
        else:
            messages.info(request, 'Aucune modification.')
        return redirect('parametres:index')


def reverse_index():
    from django.urls import reverse
    return reverse('parametres:index')


def _url_ajout_utilisateur():
    from django.urls import reverse
    try:
        return reverse('admin:accounts_user_add')
    except Exception:  # jeu de tests avec une URL d'admin surchargée
        return ''


@staff_member_required
def creer_sauvegarde(request):
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis.')
    if not _peut_gerer(request):
        messages.error(request, "Seuls un administrateur ou un gestionnaire peuvent sauvegarder la base.")
        return redirect(f'{reverse_index()}?onglet=sauvegarde')
    ligne = service_sauvegarde.creer(utilisateur=request.user)
    if ligne.statut == Sauvegarde.Statut.REUSSIE:
        messages.success(
            request,
            f'Sauvegarde créée : {ligne.get_format_display()}, {ligne.taille_lisible}, '
            f'{ligne.nb_lignes} ligne(s).',
        )
    else:
        messages.error(request, f'Sauvegarde impossible : {ligne.erreur}')
    return redirect(f'{reverse_index()}?onglet=sauvegarde')


@staff_member_required
def telecharger_sauvegarde(request, pk):
    ligne = get_object_or_404(Sauvegarde, pk=pk)
    fichier = service_sauvegarde.chemin(ligne)
    if fichier is None:
        raise Http404('Fichier de sauvegarde introuvable.')
    nom = fichier.name.rsplit('/', 1)[-1]
    return FileResponse(open(fichier, 'rb'), as_attachment=True, filename=nom)


@staff_member_required
def supprimer_sauvegarde(request, pk):
    ligne = get_object_or_404(Sauvegarde, pk=pk)
    if request.method != 'POST':
        return HttpResponseBadRequest('POST requis.')
    if not _peut_gerer(request):
        messages.error(request, "Droits insuffisants pour supprimer une sauvegarde.")
    else:
        fichier = service_sauvegarde.chemin(ligne)
        if fichier:
            fichier.unlink(missing_ok=True)
        ligne.fichier.delete(save=False)
        ligne.delete()
        messages.success(request, 'Sauvegarde supprimée.')
    return redirect(f'{reverse_index()}?onglet=sauvegarde')


@staff_member_required
def exporter(request):
    fmt = request.GET.get('format', 'csv').lower()
    data = export_dict()
    if fmt == 'json':
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        response = HttpResponse(payload, content_type='application/json; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="parametres-wineadmin.json"'
        return response

    out = io.StringIO()
    writer = csv.writer(out, delimiter=';')
    writer.writerow(['section', 'cle', 'libelle', 'valeur'])
    for d in DEFAULTS:
        writer.writerow([d[0], d[1], d[2], data.get(d[1], '')])
    response = HttpResponse(out.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="parametres-wineadmin.csv"'
    return response


@staff_member_required
def importer(request):
    if request.method != 'POST' or not request.FILES.get('fichier'):
        return HttpResponseBadRequest('Fichier requis.')
    try:
        payload = json.loads(request.FILES['fichier'].read().decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return HttpResponseBadRequest('JSON invalide.')
    try:
        nb = import_config(payload, user=request.user, ip=_client_ip(request))
    except ValueError as exc:
        return HttpResponseBadRequest(str(exc))
    messages.success(request, f'Import terminé : {nb} valeur(s) appliquée(s).')
    return redirect('parametres:index')


@staff_member_required
def imprimeur(request):
    return render(request, 'admin/parametres/impression.html', {'sections': build_sections()})