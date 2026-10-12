import logging
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import redirect
from django.views.generic import TemplateView
from django.utils import timezone

from apps.ventes.models import SessionCaisse
from apps.ventes.services import CaisseService

logger = logging.getLogger(__name__)


def _jour_requete(request):
    jour = request.GET.get('date') or request.POST.get('date')
    try:
        from datetime import datetime
        return datetime.strptime(jour, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return timezone.localdate()


class ZReportView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """Z-Report : chiffre de la journée, calculé en direct, archivage des clôtures."""
    template_name = "admin/zreport.html"

    def test_func(self):
        # Réservé au super-administrateur : un gestionnaire qui a le
        # back-office ne doit pas le voir (la page est masquée, pas interdite).
        return bool(self.request.user and self.request.user.is_superuser)

    def handle_no_permission(self):
        raise Http404

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        jour = _jour_requete(self.request)
        rapport = CaisseService.rapport_du_jour(jour)
        session = SessionCaisse.objects.filter(date_ventes=jour).first()
        fonds = Decimal(session.fonds_de_caisse) if session else Decimal(settings.SOCIETE.get('fonds_caisse', 0))
        context.update({
            'jour': jour,
            'rapport': rapport,
            'session': session,
            'fonds_de_caisse': fonds,
            'attendu_en_caisse': fonds + Decimal(rapport['ca_especes']),
            'date_param': jour.strftime('%Y-%m-%d'),
        })
        return context

    def post(self, request):
        jour = _jour_requete(request)
        try:
            fonds = request.POST.get('fonds_de_caisse') or 0
            especes_reel = request.POST.get('especes_reel') or None
            note = request.POST.get('note', '')
            session = CaisseService.cloturer(
                jour=jour,
                utilisateur=request.user,
                fonds_de_caisse=fonds,
                especes_reel=especes_reel,
                note=note,
            )
            messages.success(request, f"Clôture archivée : {session.ca_total} au total, écart de {session.ecart}.")
        except Exception as e:
            logger.exception("Échec de la clôture du Z-Report : %s", e)
            messages.error(request, f"Clôture impossible : {e}")
        return redirect(f"{request.path}?date={jour:%Y-%m-%d}")