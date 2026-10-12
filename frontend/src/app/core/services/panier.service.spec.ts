import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { MOCK_VINS } from '../data/mock-vins';
import { AuthService } from './auth.service';
import { PanierService } from './panier.service';

/** panier : calculs et gestion des lignes. */
describe('PanierService', () => {
  let service: PanierService;
  let auth: AuthService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideRouter([])],
    });
    service = TestBed.inject(PanierService);
    auth = TestBed.inject(AuthService);
    auth.connexionDemo('client');
  });

  it('crée un service avec un panier vide', () => {
    expect(service.estVide()).toBeTrue();
    expect(service.total()).toBe(0);
  });

  it('ajoute un vin et incrémente la quantité si déjà présent', () => {
    const vin = MOCK_VINS[0];
    service.ajouter(vin);
    service.ajouter(vin);
    expect(service.lignes().length).toBe(1);
    expect(service.lignes()[0].quantite).toBe(2);
  });

  it('applique le prix promotionnel à une ligne déjà présente', () => {
    const vin = MOCK_VINS[0];
    const prixPromo = Math.round(vin.prix * 0.9);
    service.ajouter(vin);
    service.ajouter({ ...vin, prix: prixPromo }, 1, prixPromo);

    expect(service.lignes().length).toBe(1);
    expect(service.lignes()[0].quantite).toBe(2);
    expect(service.lignes()[0].prixUnitaire).toBe(prixPromo);
    expect(service.sousTotal()).toBe(prixPromo * 2);
  });

  it('ne vend jamais au-delà du stock disponible', () => {
    const vin = MOCK_VINS[0];
    service.ajouter(vin, 999);
    expect(service.lignes()[0].quantite).toBe(vin.stock);
  });

  it('ignore un vin en rupture de stock', () => {
    const vin = { ...MOCK_VINS[0], stock: 0 };
    service.ajouter(vin);
    expect(service.estVide()).toBeTrue();
  });

  it('retire une ligne', () => {
    service.ajouter(MOCK_VINS[0]);
    service.retirer(MOCK_VINS[0].id);
    expect(service.estVide()).toBeTrue();
  });

  it('calcule le sous-total et le total', () => {
    const vin = MOCK_VINS[0];
    service.ajouter(vin, 2);
    expect(service.sousTotal()).toBe(90_000);
    // Aucun frais ajouté localement : le total vient des lignes du panier.
    expect(service.total()).toBe(90_000);
  });

  it('vide le panier', () => {
    service.ajouter(MOCK_VINS[0]);
    service.vider();
    expect(service.estVide()).toBeTrue();
  });
});

/** inscription obligatoire avant l'ajout au panier. */
describe('PanierService — compte obligatoire', () => {
  let service: PanierService;
  let auth: AuthService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideRouter([])],
    });
    service = TestBed.inject(PanierService);
    auth = TestBed.inject(AuthService);
  });

  it("refuse l'ajout d'un visiteur non inscrit", () => {
    const accepte = service.ajouter(MOCK_VINS[0]);

    expect(accepte).toBeFalse();
    expect(service.estVide()).toBeTrue();
    expect(service.ajoutBloque()?.id).toBe(MOCK_VINS[0].id);
  });

  it('met le vin en attente puis le rejoue une fois le compte créé', () => {
    service.ajouter(MOCK_VINS[0]);
    expect(service.ajoutEnAttente()?.id).toBe(MOCK_VINS[0].id);

    auth.connexionDemo('client');
    service.rejouerAjoutEnAttente();

    expect(service.lignes().length).toBe(1);
    expect(service.lignes()[0].vin.id).toBe(MOCK_VINS[0].id);
    expect(service.ajoutEnAttente()).toBeNull();
  });

  it("accepte l'ajout direct d'un client connecté", () => {
    auth.connexionDemo('client');

    expect(service.ajouter(MOCK_VINS[1])).toBeTrue();
    expect(service.ajoutBloque()).toBeNull();
    expect(service.lignes().length).toBe(1);
  });
});
