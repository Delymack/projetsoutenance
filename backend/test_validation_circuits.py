import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import Client
from apps.ventes.models import Reservation
from apps.ventes.services import ReservationService

def format_exc(exc):
    d = getattr(exc, 'detail', None)
    if isinstance(d, dict):
        return ' | '.join(f'{k}: {v}' for k, v in d.items())
    return str(exc)

def main():
    c = Client()
    User = get_user_model()
    admin = User.objects.filter(is_staff=True, is_superuser=True).first()
    if not admin:
        print('FAIL: admin manquant')
        return 1
    print('Admin:', admin.username)
    ok = c.login(username=admin.username, password='admin')
    print('Login admin:', 'OK' if ok else 'KO')
    if not ok:
        return 1

    cl = reverse('admin:ventes_reservation_changelist')
    r = c.get(cl)
    print('Changelist HTTP:', r.status_code, 'OK' if r.status_code == 200 else 'KO')

    for name in ['admin:ventes_reservation_change', 'admin:ventes_reservation_valider', 'admin:ventes_reservation_encaisser']:
        try:
            print('URL', name, '->', reverse(name, args=[999]), 'OK')
        except Exception as e:
            print('URL', name, 'KO', e)

    candidates = list(Reservation.objects.filter(source=Reservation.Source.SITE))
    rsv = next((x for x in candidates if x.validation_statut == Reservation.ValidationStatut.A_VALIDER), None)
    if not rsv:
        print('Pas de commande SITE en attente de validation.')
        return 0
    print('Commande SITE:', rsv.reference, 'statut=', rsv.statut)

    print('[4] Tentative d encaissement sans validation :')
    try:
        ReservationService.encaisser(rsv.id, mode_paiement=rsv.vente.mode_paiement if getattr(rsv, 'vente', None) else None, utilisateur=admin)
        print('  Attention: encaissement effectue sans erreur.')
    except Exception as e:
        print('  Exception lue :', format_exc(e))

    print('[5] Validation :')
    try:
        ReservationService.valider(rsv.id, utilisateur=admin)
        rsv.refresh_from_db()
        print('  Validation OK ->', rsv.validation_statut, 'par', rsv.validation_par, 'le', rsv.validation_le)
    except Exception as e:
        print('  VALIDATION KO :', e)
        rsv.refresh_from_db()
        print('  Apres echec:', rsv.validation_statut)
        return 1

    print('[6] Encaissement VALIDEE :')
    try:
        res = ReservationService.encaisser(rsv.id, mode_paiement=rsv.vente.mode_paiement if getattr(rsv, 'vente', None) else None, utilisateur=admin)
        print('  Encaissement OK ->', res)
    except Exception as e:
        print('  ENCASSANT KO :', format_exc(e))
        return 1

    rsv.refresh_from_db()
    print('[7] Etat final : statut=', rsv.statut, 'validation_statut=', rsv.validation_statut)
    if rsv.statut != Reservation.Statut.SOLDEE:
        print('FAIL: statut attendu', Reservation.Statut.SOLDEE, 'obtenu', rsv.statut)
        return 1
    print('RESULTAT: OK -> Circuit Valider -> Encaisser fonctionne.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
