import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { PanierLigne } from '../models/product.model';
import { MOCK_VINS } from '../data/mock-vins';
import { environment } from '../../../environments/environment';
import { ReservationsService } from './reservations.service';

describe('ReservationsService', () => {
  let service: ReservationsService;
  let http: HttpTestingController;

  beforeEach(() => {
    environment.useMock = false;
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(ReservationsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('enregistre une réservation web sans créer une vente ni envoyer un code promo', async () => {
    const panier: PanierLigne[] = [
      { vin: { ...MOCK_VINS[0], id: '42' }, quantite: 2, prixUnitaire: 45000, remisePct: 0 },
    ];
    const operation = service.creerDepuisSite({
      nom: 'Martin',
      prenom: 'Mila',
      telephone: '0340000000',
      email: 'mila@example.test',
      mode_reception: 'RETRAIT',
      adresse_livraison: '',
      note: '',
    }, panier);

    const request = http.expectOne(`${environment.apiUrl}/reservations/site/`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      nom: 'Martin',
      prenom: 'Mila',
      telephone: '0340000000',
      email: 'mila@example.test',
      mode_reception: 'RETRAIT',
      adresse_livraison: '',
      note: '',
      lignes: [{ produit_id: 42, quantite: 2, unite: 'BOUTEILLE' }],
    });
    request.flush({
      success: true,
      data: { reference: 'RES-AB12CD34', statut: 'EN_ATTENTE', montant_total: '90000.00' },
    });

    await expectAsync(operation).toBeResolvedTo({
      reference: 'RES-AB12CD34',
      statut: 'EN_ATTENTE',
      montant_total: '90000.00',
    });
  });

  it('expose le suivi d’une réservation par sa référence', async () => {
    const operation = service.suivi('RES-AB12CD34');

    const request = http.expectOne(`${environment.apiUrl}/reservations/suivi/RES-AB12CD34/`);
    expect(request.request.method).toBe('GET');
    request.flush({
      success: true,
      data: { reference: 'RES-AB12CD34', statut: 'SOLDEE', montant_total: '77520.00' },
    });

    await expectAsync(operation).toBeResolvedTo({
      reference: 'RES-AB12CD34',
      statut: 'SOLDEE',
      montant_total: '77520.00',
    });
  });

  it('refuse une référence inconnue comme le backend', async () => {
    const operation = service.suivi('RES-INCONNUE');

    const request = http.expectOne(`${environment.apiUrl}/reservations/suivi/RES-INCONNUE/`);
    request.flush({ success: false, message: 'Réservation introuvable.' },
      { status: 404, statusText: 'Not Found' });

    await expectAsync(operation).toBeRejected();
  });

  it('formate les erreurs de validation 400 du backend', async () => {
    const panier: PanierLigne[] = [
      { vin: { ...MOCK_VINS[0], id: '42' }, quantite: 2, prixUnitaire: 45000, remisePct: 0 },
    ];
    const operation = service.creerDepuisSite({
      nom: 'Martin',
      prenom: 'Mila',
      telephone: '0340000000',
      email: 'mila@example.test',
      mode_reception: 'LIVRAISON',
      adresse_livraison: '',
      note: '',
    }, panier);

    const request = http.expectOne(`${environment.apiUrl}/reservations/site/`);
    request.flush(
      {
        success: false,
        message: 'Vérifiez les coordonnées et les articles sélectionnés.',
        errors: { adresse_livraison: ['Une adresse est obligatoire pour une livraison.'] },
      },
      { status: 400, statusText: 'Bad Request' },
    );

    await expectAsync(operation).toBeRejectedWithError(/adresse_livraison/);
  });
});
