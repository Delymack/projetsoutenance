from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import admin

from apps.ventes.models import Vente
from apps.ventes.paiements import modes_actifs

#: Icône par moyen de paiement, alignée sur la charte du back-office.
ICONES_PAIEMENT = {
    'ESPECES': 'fa-money-bill-wave',
    'MVOLA': 'fa-mobile-screen',
    'ORANGE_MONEY': 'fa-mobile-screen',
    'AIRTEL_MONEY': 'fa-mobile-screen',
    'MOBILE_MONEY': 'fa-mobile-screen',
    'CHEQUE': 'fa-file-signature',
    'CARTE': 'fa-credit-card',
    'CREDIT': 'fa-book',
}


class POSView(LoginRequiredMixin, TemplateView):
    template_name = "admin/pos.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(admin.site.each_context(self.request))
        # Les moyens proposés viennent des paramètres : la caisse suit le
        # paramétrage, pas une liste figée dans le gabarit.
        context['modes_paiement'] = modes_actifs()
        context['icone_paiement'] = lambda code: ICONES_PAIEMENT.get(code, 'fa-money-bill')
        return context
