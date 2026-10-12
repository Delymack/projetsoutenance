import { provideHttpClient } from '@angular/common/http';
import { fakeAsync, TestBed, tick } from '@angular/core/testing';

import { MOCK_DELAY_MS } from '../data/mock-vins';
import { environment } from '../../../environments/environment';
import { VinService } from './vin.service';

describe('VinService en mode mock', () => {
  let service: VinService;
  const useMockInitial = environment.useMock;

  beforeEach(() => {
    environment.useMock = true;
    TestBed.configureTestingModule({ providers: [provideHttpClient()] });
    service = TestBed.inject(VinService);
  });

  afterEach(() => {
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
});
