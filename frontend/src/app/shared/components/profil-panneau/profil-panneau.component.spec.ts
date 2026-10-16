import { LOCALE_ID } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { registerLocaleData } from '@angular/common';
import localeFr from '@angular/common/locales/fr';
import { Observable, of } from 'rxjs';
import { provideRouter } from '@angular/router';
import { TranslateLoader, provideTranslateService } from '@ngx-translate/core';
import { AuthService } from '../../../core/services/auth.service';
import { CommandesService } from '../../../core/services/commandes.service';
import { ProfilPanneauComponent } from './profil-panneau.component';

/** Chargeur vide : les libellés ne sont pas l'objet de ces tests, les données le sont. */
class ChargeurVide implements TranslateLoader {
  getTranslation(): Observable<Record<string, unknown>> {
    return of({});
  }
}

/**
 * Panneau de compte (coin haut droit).
 *
 * Les tests portent sur ce que le client voit vraiment : son identité, son
 * solde de fidélité, sa dernière commande, et les adresses des raccourcis —
 * c'est par elles que le panneau ouvre la bonne section du profil.
 */
describe('ProfilPanneauComponent', () => {
  let composant: ProfilPanneauComponent;
  let fixture: ComponentFixture<ProfilPanneauComponent>;
  let auth: AuthService;

  /** Historique minimal : une commande livrée, la plus récente. */
  const COMMANDES = [
    {
      reference: 'CMD-9001',
      date: '2026-10-02T08:30:00.000Z',
      lignes: [{ vinId: 'v-001', quantite: 2, prixUnitaire: 42000, remisePct: 0 }],
      fraisLivraison: 0,
      statut: 'livree',
    },
  ];

  beforeEach(async () => {
    registerLocaleData(localeFr);
    localStorage.clear();
    localStorage.setItem('lb.commandes', JSON.stringify(COMMANDES));

    await TestBed.configureTestingModule({
      imports: [ProfilPanneauComponent],
      providers: [
        provideRouter([{ path: '', component: ProfilPanneauComponent }]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideTranslateService({
          loader: { provide: TranslateLoader, useClass: ChargeurVide },
          defaultLanguage: 'fr',
        }),
        { provide: LOCALE_ID, useValue: 'fr-FR' },
      ],
    }).compileComponents();

    auth = TestBed.inject(AuthService);
    auth.connexionDemo('client');

    fixture = TestBed.createComponent(ProfilPanneauComponent);
    composant = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('montre le client connecté, ses initiales et son rôle', () => {
    const texte = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(texte).toContain('Client Démo');
    expect(texte).toContain('client@lazani.betsileo');
    expect(texte).toContain('CD');
    expect(composant.role()).toBe('client');
  });

  it('affiche la dernière commande enregistrée', () => {
    const texte = (
      fixture.nativeElement.querySelector('.compte__commande')?.textContent ?? ''
    ).replace(/\s/g, '');

    expect(texte).toContain('CMD-9001');
    expect(texte).toContain('84000');
  });

  it('pointe chaque raccourci vers la section du profil correspondante', () => {
    const adresses = [...fixture.nativeElement.querySelectorAll('.compte__lien')].map(
      (lien: Element) => lien.getAttribute('href'),
    );

    expect(adresses).toContain('/profil');
    expect(adresses).toContain('/historique');
    expect(adresses).toContain('/profil?section=messages');
    expect(adresses).toContain('/profil?section=adresses');
  });

  it('ne déconnecte pas sans confirmation', () => {
    fixture.nativeElement.querySelector('.compte__sortie').click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('.compte__confirmation')).toBeTruthy();
    expect(auth.connecte()).toBeTrue();

    composant.seDeconnecter();

    expect(auth.connecte()).toBeFalse();
  });
});