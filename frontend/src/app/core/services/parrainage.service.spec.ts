import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { MOCK_VINS } from '../data/mock-vins';
import { AuthService } from './auth.service';
import { PanierService } from './panier.service';
import { ParrainageService } from './parrainage.service';

/** parrainage, code de remise et invitations. */
describe('ParrainageService', () => {
  let service: ParrainageService;
  let panier: PanierService;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideRouter([])],
    });
    service = TestBed.inject(ParrainageService);
    panier = TestBed.inject(PanierService);
    TestBed.inject(AuthService).connexionDemo('client');
  });

  it('génère un code de 8 caractères et le réutilise', () => {
    expect(service.code().length).toBe(8);
    const stocke = localStorage.getItem('lb.codeParrainage');
    expect(stocke).toBe(service.code());
  });

  it('expose un lien d\'invitation contenant le code', () => {
    expect(service.lienInvitation()).toContain(`code=${service.code()}`);
  });

  it('propose deux filleuls de démonstration', () => {
    expect(service.filleuls().length).toBe(2);
    expect(service.recompensesObtenues()).toBe(1000);
  });

  it('ajoute une invitation en tête de liste', () => {
    service.inviter('Rado', 'rado@example.mg', 'sms');
    expect(service.filleuls().length).toBe(3);
    expect(service.filleuls()[0].nom).toBe('Rado');
    expect(service.enAttente()).toBe(2);
  });

  it('retombe sur le contact si aucun nom n\'est fourni', () => {
    const filleul = service.inviter('   ', 'tojo@example.mg', 'email');
    expect(filleul.nom).toBe('tojo@example.mg');
  });

  it('fait progresser le statut puis retire le filleul', () => {
    const filleul = service.inviter('Voahangy', 'voa@example.mg', 'email');
    service.changerStatut(filleul.id, 'recompense');
    expect(service.recompensesObtenues()).toBe(2000);
    service.retirer(filleul.id);
    expect(service.filleuls().length).toBe(2);
  });

  it('mémorise le code de parrainage sans toucher aux montants du panier', () => {
    panier.ajouter(MOCK_VINS[0]);
    const totalAvant = panier.total();
    service.utiliserCode('abcd2345');
    expect(service.codeUtilise).toBe('ABCD2345');
    // Les totaux appartiennent au backend : le code ne les modifie pas ici.
    expect(panier.total()).toBe(totalAvant);
  });

  it('ignore le code du client lui-même', () => {
    service.utiliserCode(service.code());
    expect(service.codeUtilise).toBeNull();
  });
});