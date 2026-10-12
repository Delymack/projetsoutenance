import { TestBed } from '@angular/core/testing';
import { TranslateService } from '@ngx-translate/core';

import { LangueService } from './langue.service';

describe('LangueService', () => {
  let translate: jasmine.SpyObj<TranslateService>;

  beforeEach(() => {
    localStorage.removeItem('lb.langue');
    document.documentElement.removeAttribute('lang');
    translate = jasmine.createSpyObj<TranslateService>('TranslateService', [
      'addLangs',
      'setDefaultLang',
      'use',
      'instant',
    ]);

    TestBed.configureTestingModule({
      providers: [
        LangueService,
        { provide: TranslateService, useValue: translate },
      ],
    });
  });

  it('utilise le français par défaut sans préférence enregistrée', () => {
    const service = TestBed.inject(LangueService);

    expect(service.langue()).toBe('fr');
    expect(translate.setDefaultLang).toHaveBeenCalledWith('fr');
    expect(translate.use).toHaveBeenCalledWith('fr');
    expect(document.documentElement.getAttribute('lang')).toBe('fr');
  });

  it('restaure une langue prise en charge depuis localStorage', () => {
    localStorage.setItem('lb.langue', 'mg');

    const service = TestBed.inject(LangueService);

    expect(service.langue()).toBe('mg');
    expect(translate.use).toHaveBeenCalledWith('mg');
    expect(document.documentElement.getAttribute('lang')).toBe('mg');
  });

  it('ignore une préférence invalide et revient au français', () => {
    localStorage.setItem('lb.langue', 'de');

    const service = TestBed.inject(LangueService);

    expect(service.langue()).toBe('fr');
    expect(translate.use).toHaveBeenCalledWith('fr');
  });

  it('synchronise ngx-translate, document.lang et localStorage lors du changement', () => {
    const service = TestBed.inject(LangueService);

    service.changer('en');

    expect(service.langue()).toBe('en');
    expect(translate.use).toHaveBeenCalledWith('en');
    expect(document.documentElement.getAttribute('lang')).toBe('en');
    expect(localStorage.getItem('lb.langue')).toBe('en');
  });
});
