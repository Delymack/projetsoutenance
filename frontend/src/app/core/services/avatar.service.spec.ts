import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { AvatarService } from './avatar.service';

/**
 * Photo de profil.
 *
 * L'ordre des sources est ce qui compte : la photo choisie dans le navigateur
 * d'abord, celle du compte ensuite, les initiales en dernier recours.
 */
describe('AvatarService', () => {
  /** Compte connecté, relu depuis le stockage au démarrage du service. */
  const UTILISATEUR = {
    id: 'u-1',
    nom: 'Rakoto Béryl',
    email: 'beryl@lazani.betsileo',
    role: 'client',
    avatarUrl: 'https://exemple.test/photo.jpg',
  };

  const PHOTO_LOCALE = 'data:image/jpeg;base64,AAAA';

  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem('lb.utilisateur', JSON.stringify(UTILISATEUR));

    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
  });

  it('reprend la photo du compte quand aucune photo locale n’existe', () => {
    const avatar = TestBed.inject(AvatarService);

    expect(avatar.photo()).toBe(UTILISATEUR.avatarUrl);
    expect(avatar.personnalisee()).toBeFalse();
  });

  it('donne la priorité à la photo choisie dans le navigateur', () => {
    localStorage.setItem('lb.avatar.u-1', PHOTO_LOCALE);
    const avatar = TestBed.inject(AvatarService);

    expect(avatar.photo()).toBe(PHOTO_LOCALE);
    expect(avatar.personnalisee()).toBeTrue();
  });

  it('revient à la photo du compte après retrait', () => {
    localStorage.setItem('lb.avatar.u-1', PHOTO_LOCALE);
    const avatar = TestBed.inject(AvatarService);

    avatar.retirer();

    expect(avatar.photo()).toBe(UTILISATEUR.avatarUrl);
    expect(localStorage.getItem('lb.avatar.u-1')).toBeNull();
  });

  it('n’affiche aucune photo pour un visiteur anonyme', () => {
    localStorage.removeItem('lb.utilisateur');
    localStorage.setItem('lb.avatar.u-1', PHOTO_LOCALE);
    const avatar = TestBed.inject(AvatarService);

    expect(avatar.photo()).toBeNull();
  });
});