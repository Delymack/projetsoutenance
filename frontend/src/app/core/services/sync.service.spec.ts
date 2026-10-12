import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { MOCK_VINS } from '../data/mock-vins';
import { environment } from '../../../environments/environment';
import { SyncService } from './sync.service';

describe('SyncService', () => {
  let service: SyncService;
  let http: HttpTestingController;

  beforeEach(() => {
    environment.useMock = false;
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(SyncService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('envoie une vente au backend sans transmettre de code promo', async () => {
    const operation = service.enregistrerVente(
      [{ vin: { ...MOCK_VINS[0], id: '42' }, quantite: 2, prixUnitaire: 45000, remisePct: 0 }],
      'ESPECES',
    );

    const request = http.expectOne(`${environment.apiUrl}/ventes/`);
    expect(request.request.method).toBe('POST');
    const corps = request.request.body as Record<string, unknown>;
    // La vente est transmise sans code promo : seuls le mode de paiement et
    // les lignes (id produit, quantité) comptent pour le backend.
    expect(corps['code_promo']).toBeUndefined();
    expect(corps).toEqual(
      jasmine.objectContaining({
        mode_paiement: 'ESPECES',
        lignes: [{ produit_id: 42, quantite: 2, unite: 'BOUTEILLE' }],
      }),
    );
    expect(corps['client_libelle']).toBe('');
    expect(corps['horodatage']).toEqual(jasmine.any(String));

    const vente = {
      id: 7,
      reference: 'FAC-AB12CD34',
      date_vente: '2026-10-07T10:00:00Z',
      total: '90000.00',
      statut: 'PAYEE',
      lignes: [],
    };
    request.flush({ success: true, data: vente });
    await expectAsync(operation).toBeResolvedTo(vente);
  });

  it('refuse les identifiants qui ne sont pas des clés numériques backend', async () => {
    const operation = service.enregistrerVente(
      [{ vin: MOCK_VINS[0], quantite: 1, prixUnitaire: 45000, remisePct: 0 }],
    );

    await expectAsync(operation).toBeRejectedWithError(/Identifiant produit invalide/);
    http.expectNone(`${environment.apiUrl}/ventes/`);
  });
});
