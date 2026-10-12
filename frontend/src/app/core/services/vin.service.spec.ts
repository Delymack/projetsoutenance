import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { fakeAsync, TestBed, tick } from '@angular/core/testing';

import { MOCK_DELAY_MS } from '../data/mock-vins';
import { environment } from '../../../environments/environment';
import { VinService } from './vin.service';

describe('VinService en mode mock', () => {
  let service: VinService;
  let http: HttpTestingController;
  const useMockInitial = environment.useMock;

  beforeEach(() => {
    environment.useMock = true;
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(VinService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    environment.useMock = useMockInitial;
  });

  it('filtre le catalogue par catégorie, budget et stock puis trie par prix', fakeAsync(() => {
    let ids: string[] = [];

    service
      .lister({ categorie: 'blanc', prixMax: 40_000, enStock: true, tri: 'prixAsc' })
      .subscribe((vins) => (ids = vins.map((vin) => vin.id)));

    tick(MOCK_DELAY_MS);

    expect(ids).toEqual(['v-010', 'v-002']);
  }));

  it('recherche dans les champs produit affichés au catalogue', fakeAsync(() => {
    let ids: string[] = [];

    service.lister({ recherche: 'Fianarantsoa' }).subscribe((vins) => (ids = vins.map((vin) => vin.id)));

    tick(MOCK_DELAY_MS);

    expect(ids.length).toBeGreaterThan(0);
    expect(ids).toContain('v-001');
  }));

  it('utilise les illustrations du catalogue comme repli sans remplacer les images backend', () => {
    environment.useMock = false;
    let images: string[] = [];

    service.listerTous().subscribe((vins) => (images = vins.map((vin) => vin.image)));

    const request = http.expectOne(`${environment.apiUrl}/produits/?statut=true`);
    request.flush({
      results: [
        { id: 12, nom: 'Cabernet Fianarantsoa', image_url: null, image: null, prix_vente: '60000' },
        { id: 11, nom: 'Sauvignon Blanc Vakio', image_url: '/media/sauvignon.jpg', image: null, prix_vente: '33000' },
        { id: 13, nom: 'Vin inédit', image_url: null, image: null, prix_vente: '25000' },
      ],
      next: null,
    });

    expect(images).toEqual([
      'assets/images/vins/v-011.svg',
      '/media/sauvignon.jpg',
      'assets/images/produits/produit-placeholder.png',
    ]);
  });
});
