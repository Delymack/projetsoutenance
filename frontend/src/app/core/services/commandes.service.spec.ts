import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { CommandesService } from './commandes.service';

describe('CommandesService — ventes backend', () => {
  let service: CommandesService;
  let http: HttpTestingController;

  beforeEach(() => {
    environment.useMock = false;
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(CommandesService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    localStorage.clear();
    http.verify();
  });

  it('charge et mappe les ventes validées depuis /ventes/', async () => {
    const operation = service.rafraichir();
    const request = http.expectOne(`${environment.apiUrl}/ventes/?ordering=-date_vente`);
    expect(request.request.method).toBe('GET');
    request.flush({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: 7,
          reference: 'FAC-AB12CD34',
          date_vente: '2026-10-07T10:00:00Z',
          total: '90000.00',
          statut: 'PAYEE',
          lignes: [
            {
              id: 1,
              produit: { id: 42, nom: 'Vin de test' },
              quantite: 2,
              prix_unitaire: '45000.00',
              remise: '0.00',
              sous_total: '90000.00',
            },
          ],
        },
      ],
    });
    await operation;

    expect(service.commandes().length).toBe(1);
    expect(service.commandes()[0].reference).toBe('FAC-AB12CD34');
    expect(service.commandes()[0].statut).toBe('enPreparation');
    expect(service.commandes()[0].lignes[0].vinId).toBe('42');
    expect(service.total(service.commandes()[0])).toBe(90000);
  });

  it('rafraîchit la réservation du site par référence, sans compte ni jeton', async () => {
    localStorage.setItem('lb.commandes', JSON.stringify([
      {
        reference: 'RES-AB12CD34',
        date: '2026-10-08T08:00:00Z',
        lignes: [{ vinId: '21', quantite: 2, prixUnitaire: 45600, remisePct: 0 }],
        fraisLivraison: 0,
        statut: 'enPreparation',
        points: 0,
        totalBackend: 77520,
      },
    ]));

    const operation = service.rafraichir();

    const suivi = http.expectOne(`${environment.apiUrl}/reservations/suivi/RES-AB12CD34/`);
    expect(suivi.request.method).toBe('GET');
    suivi.flush({
      success: true,
      data: {
        reference: 'RES-AB12CD34',
        statut: 'SOLDEE',
        montant_total: '77520.00',
        date_creation: '2026-10-08T08:00:00Z',
        lignes: [{ produit_id: 21, quantite: 2, prix_unitaire: '45600.00' }],
      },
    });
    const ventes = http.expectOne(`${environment.apiUrl}/ventes/?ordering=-date_vente`);
    ventes.flush({ count: 0, next: null, previous: null, results: [] });

    await operation;

    const commande = service.commandes()[0];
    expect(commande.reference).toBe('RES-AB12CD34');
    expect(commande.statut).toBe('livree');
    expect(commande.lignes[0].vinId).toBe('21');
    expect(service.total(commande)).toBe(77520);
  });

  it('conserve la réservation locale si le suivi échoue', async () => {
    localStorage.setItem('lb.commandes', JSON.stringify([
      {
        reference: 'RES-AB12CD34',
        date: '2026-10-08T08:00:00Z',
        lignes: [{ vinId: '21', quantite: 2, prixUnitaire: 45600, remisePct: 0 }],
        fraisLivraison: 0,
        statut: 'enPreparation',
        points: 0,
        totalBackend: 77520,
      },
    ]));

    const operation = service.rafraichir();

    const suivi = http.expectOne(`${environment.apiUrl}/reservations/suivi/RES-AB12CD34/`);
    suivi.flush(
      { success: false, message: 'Réservation introuvable.' },
      { status: 404, statusText: 'Not Found' },
    );
    const ventes = http.expectOne(`${environment.apiUrl}/ventes/?ordering=-date_vente`);
    ventes.flush({ count: 0, next: null, previous: null, results: [] });

    await operation;

    expect(service.commandes().length).toBe(1);
    expect(service.commandes()[0].statut).toBe('enPreparation');
  });

  it('reste silencieux quand la caisse n’est pas accessible (401/403)', async () => {
    const operation = service.rafraichir();

    const ventes = http.expectOne(`${environment.apiUrl}/ventes/?ordering=-date_vente`);
    ventes.flush({ detail: 'Authentification requise.' }, { status: 401, statusText: 'Unauthorized' });

    await operation;

    expect(service.commandes().length).toBe(0);
  });
});
