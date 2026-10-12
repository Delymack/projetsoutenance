import { TestBed } from '@angular/core/testing';
import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.resetTestingModule();
  });

  it('bascule entre clair et sombre et applique data-theme', () => {
    const service = TestBed.inject(ThemeService);
    expect(document.documentElement.getAttribute('data-theme')).toBe('clair');

    service.basculer();
    // `appliquer()` est déclenché par un effect() : il ne s'exécute qu'au
    // prochain cycle de détection de changement, il faut donc le forcer.
    TestBed.flushEffects();
    expect(service.theme()).toBe('sombre');
    expect(document.documentElement.getAttribute('data-theme')).toBe('sombre');

    service.basculer();
    TestBed.flushEffects();
    expect(service.theme()).toBe('clair');
    expect(document.documentElement.getAttribute('data-theme')).toBe('clair');
  });

  it('persiste le thème dans localStorage', () => {
    const service = TestBed.inject(ThemeService);
    service.definir('sombre');
    expect(localStorage.getItem('lb.theme')).toBe('sombre');
  });

  it('expose estSombre de façon cohérente', () => {
    const service = TestBed.inject(ThemeService);
    expect(service.estSombre()).toBeFalse();
    service.definir('sombre');
    expect(service.estSombre()).toBeTrue();
  });
});
