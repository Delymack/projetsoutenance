import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';

describe('AuthService session persistence', () => {
  let service: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    service = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    localStorage.clear();
  });

  it('stores the refresh token after signup and renews access without logging out', async () => {
    const signup = service.signupVerify('client@example.test', '123456');
    http.expectOne(`${environment.apiUrl}/auth/signup/verify/`).flush({
      message: 'Compte créé.',
      access: 'access-short-lived',
      refresh: 'refresh-long-lived',
      user: {
        id: 12,
        username: 'client',
        email: 'client@example.test',
        first_name: 'Miora',
        last_name: 'Client',
        role: 'CLIENT',
      },
    });
    await signup;

    expect(service.connecte()).toBeTrue();
    expect(localStorage.getItem('lb.refresh')).toBe('refresh-long-lived');

    const renewal = service.renouvelerToken();
    const request = http.expectOne(`${environment.apiUrl}/auth/refresh/`);
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ refresh: 'refresh-long-lived' });
    request.flush({ access: 'access-renewed' });

    await expectAsync(renewal).toBeResolvedTo('access-renewed');
    expect(service.connecte()).toBeTrue();
    expect(service.token).toBe('access-renewed');
    expect(localStorage.getItem('lb.refresh')).toBe('refresh-long-lived');
  });

  it('clears access and refresh tokens only when the user logs out', () => {
    localStorage.setItem('lb.token', 'access');
    localStorage.setItem('lb.refresh', 'refresh');
    localStorage.setItem('lb.utilisateur', JSON.stringify({
      id: '12', nom: 'Miora Client', email: 'client@example.test', role: 'client', token: 'access',
    }));
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    service = TestBed.inject(AuthService);

    service.deconnexion();

    expect(localStorage.getItem('lb.token')).toBeNull();
    expect(localStorage.getItem('lb.refresh')).toBeNull();
    expect(localStorage.getItem('lb.utilisateur')).toBeNull();
  });
});