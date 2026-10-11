import { HttpClient } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { tap } from 'rxjs';
import { LoginResponse, User } from './models';

const baseUrl = 'http://127.0.0.1:8000/api/v1';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  readonly token = signal<string | null>(null);
  readonly user = signal<User | null>(null);

  login(email: string, password: string) {
    return this.http.post<LoginResponse>(`${baseUrl}/auth/login`, { email, password }).pipe(
      tap((response) => {
        this.token.set(response.access_token);
        this.user.set(response.user);
      }),
    );
  }

  logout(): void {
    this.token.set(null);
    this.user.set(null);
  }
}
