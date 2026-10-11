import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from './auth.service';
import { requestMessage } from './errors';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule],
  template: `
    <section class="card narrow">
      <h1>Sign in</h1>
      <p>Use the account created by your operator.</p>
      <form [formGroup]="form" (ngSubmit)="submit()">
        <label>Email <input type="email" formControlName="email" autocomplete="username"></label>
        <label>Password <input type="password" formControlName="password" autocomplete="current-password"></label>
        @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
        <button type="submit" [disabled]="busy()">{{ busy() ? 'Signing in…' : 'Sign in' }}</button>
      </form>
    </section>
  `,
})
export class LoginComponent {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly error = signal('');
  readonly busy = signal(false);
  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error.set('Enter your email and password.');
      return;
    }
    this.error.set('');
    this.busy.set(true);
    const { email, password } = this.form.getRawValue();
    this.auth.login(email, password).subscribe({
      next: () => void this.router.navigateByUrl('/experiments'),
      error: (error: HttpErrorResponse) => {
        this.error.set(error.status === 401 ? 'Invalid email or password.' : requestMessage(error));
        this.busy.set(false);
      },
    });
  }
}
