import { TestBed } from '@angular/core/testing';
import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.resetTestingModule();
  });

  it('bascule entre clair et sombre et applique data-theme', () => {
    const service = TestBed.inject(ThemeService);
    // Sans préférence persistée, l'identité « Nuit & Or » impose le sombre.
    expect(document.documentElement.getAttribute('data-theme')).toBe('sombre');

    service.basculer();
    // `appliquer()` est déclenché par un effect() : il ne s'exécute qu'au
    // prochain cycle de détection de changement, il faut donc le forcer.
    TestBed.flushEffects();
    expect(service.theme()).toBe('clair');
    expect(document.documentElement.getAttribute('data-theme')).toBe('clair');

    service.basculer();
    TestBed.flushEffects();
    expect(service.theme()).toBe('sombre');
    expect(document.documentElement.getAttribute('data-theme')).toBe('sombre');
  });

  it('persiste le thème dans localStorage', () => {
    const service = TestBed.inject(ThemeService);
    service.definir('sombre');
    expect(localStorage.getItem('lb.theme')).toBe('sombre');
  });

  it('expose estSombre de façon cohérente', () => {
    const service = TestBed.inject(ThemeService);
    // Défaut « Nuit & Or » : sombre tant que l'utilisateur n'a rien choisi.
    expect(service.estSombre()).toBeTrue();
    service.definir('clair');
    expect(service.estSombre()).toBeFalse();
  });
});
