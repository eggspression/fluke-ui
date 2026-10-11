import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AuthService } from './auth.service';
import { ApiService } from './api.service';

@Component({ template: '' })
class EmptyPage {}

describe('authentication and API requests', () => {
  let http: HttpTestingController;
  let auth: AuthService;
  let api: ApiService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([
        { path: 'login', component: EmptyPage },
      ])],
    });
    http = TestBed.inject(HttpTestingController);
    auth = TestBed.inject(AuthService);
    api = TestBed.inject(ApiService);
  });

  afterEach(() => http.verify());

  it('keeps the login token only in memory and clears it on logout', () => {
    auth.login('alice@example.com', 'password').subscribe();
    http.expectOne('http://127.0.0.1:8000/api/v1/auth/login').flush({
      access_token: 'test-token', token_type: 'bearer', expires_at: '2026-10-10T12:00:00Z',
      user: { id: 'alice-id', email: 'alice@example.com' },
    });
    expect(auth.token()).toBe('test-token');
    expect(auth.user()?.email).toBe('alice@example.com');
    expect(localStorage.getItem('fluke-token')).toBeNull();
    auth.logout();
    expect(auth.token()).toBeNull();
    expect(auth.user()).toBeNull();
  });

  it('sends the bearer token and clears it when the API returns 401', () => {
    auth.login('alice@example.com', 'password').subscribe();
    http.expectOne('http://127.0.0.1:8000/api/v1/auth/login').flush({
      access_token: 'test-token', token_type: 'bearer', expires_at: '2026-10-10T12:00:00Z',
      user: { id: 'alice-id', email: 'alice@example.com' },
    });
    api.listExperiments().subscribe({ error: () => undefined });
    const request = http.expectOne('http://127.0.0.1:8000/api/v1/experiments');
    expect(request.request.headers.get('Authorization')).toBe('Bearer test-token');
    request.flush({ detail: 'Invalid or expired credentials' }, { status: 401, statusText: 'Unauthorized' });
    expect(auth.token()).toBeNull();
  });
});
