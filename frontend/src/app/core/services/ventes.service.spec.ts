import { TestBed } from '@angular/core/testing';

import { VentesService } from './ventes.service';

describe('VentesService — agrégats du dashboard et des rapports', () => {
  let service: VentesService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(VentesService);
  });

  it('produit une matrice complète : 7 jours × 24 heures', () => {
    const matrice = service.matrice();

    expect(matrice.length).toBe(7 * 24);
    expect(matrice.filter((case_) => case_.ventes > 0).length).toBeGreaterThan(0);
    expect(Math.max(...matrice.map((case_) => case_.ventes))).toBe(service.picVentes());
  });

  it('donne un pic de ventes et un meilleur moment cohérents', () => {
    const moment = service.meilleurMoment();

    expect(moment.ventes).toBeGreaterThan(0);
    expect(moment.jour).toBeGreaterThanOrEqual(0);
    expect(moment.jour).toBeLessThanOrEqual(6);
    expect(moment.heure).toBeGreaterThanOrEqual(0);
    expect(moment.heure).toBeLessThan(24);
  });

  it('agrège le chiffre d’affaires par période croissante', () => {
    const parJour = service.caParPeriode('jour');
    const parSemaine = service.caParPeriode('semaine');
    const parMois = service.caParPeriode('mois');

    expect(parJour.length).toBe(7);
    expect(parSemaine.length).toBe(8);
    expect(parMois.length).toBe(12);
    for (const serie of [...parJour, ...parSemaine, ...parMois]) {
      expect(serie.value).toBeGreaterThanOrEqual(0);
    }
  });

  it('classe le top des vins par volume décroissant', () => {
    const top = service.topVins();

    expect(top.length).toBeGreaterThan(0);
    const valeurs = top.map((vin) => vin.value);
    expect(valeurs).toEqual([...valeurs].sort((a, b) => b - a));
  });

  it('produit des indicateurs cohérents entre eux', () => {
    const indicateurs = service.indicateurs('semaine');

    expect(indicateurs.ca).toBeGreaterThan(0);
    expect(indicateurs.tickets).toBeGreaterThan(0);
    expect(indicateurs.bouteilles).toBeGreaterThan(0);
    expect(indicateurs.panierMoyen).toBeGreaterThan(0);
    expect(Number.isFinite(indicateurs.evolutionCa)).toBeTrue();
  });

  it('renvoie des lignes d’efficacité de promotion exploitables', () => {
    const lignes = service.efficacitePromos();

    expect(lignes.length).toBeGreaterThan(0);
    for (const ligne of lignes) {
      expect(ligne.id).toBeTruthy();
      expect(ligne.ventes).toBeGreaterThanOrEqual(0);
      expect(ligne.volume).toBeGreaterThanOrEqual(0);
    }
  });
});