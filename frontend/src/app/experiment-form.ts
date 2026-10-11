import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from './api.service';
import { fieldMessages, requestMessage } from './errors';
import { ExperimentFormValue } from './models';

@Component({
  selector: 'app-experiment-form',
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <section class="card form-card">
      <a routerLink="/experiments">← Experiments</a>
      <h1>{{ id ? 'Edit experiment' : 'New experiment' }}</h1>
      <p>MNIST, IID, MNIST_2NN, and CPU are fixed for this demo.</p>
      <form [formGroup]="form" (ngSubmit)="submit()">
        <label>Name <input formControlName="name" maxlength="120"></label>
        @if (form.controls.name.touched && form.controls.name.invalid) { <small class="error">Enter a name (up to 120 characters).</small> }
        @if (fieldErrors()['name']) { <small class="error">{{ fieldErrors()['name'] }}</small> }
        <label>Algorithm <select formControlName="algorithm"><option value="fedavg">FedAvg</option><option value="fedprox">FedProx</option></select></label>
        @if (fieldErrors()['algorithm']) { <small class="error">{{ fieldErrors()['algorithm'] }}</small> }
        <div class="form-grid">
          <label>Clients (2–10) <input type="number" min="2" max="10" step="1" formControlName="n_clients" [attr.aria-invalid]="form.controls.n_clients.touched && form.controls.n_clients.invalid">
            @if (form.controls.n_clients.touched && form.controls.n_clients.invalid) { <small class="error">Enter a whole number from 2 to 10.</small> }
            @if (fieldErrors()['n_clients']) { <small class="error">{{ fieldErrors()['n_clients'] }}</small> }
          </label>
          <label>Rounds (1–5) <input type="number" min="1" max="5" step="1" formControlName="n_rounds" [attr.aria-invalid]="form.controls.n_rounds.touched && form.controls.n_rounds.invalid">
            @if (form.controls.n_rounds.touched && form.controls.n_rounds.invalid) { <small class="error">Enter a whole number from 1 to 5.</small> }
            @if (fieldErrors()['n_rounds']) { <small class="error">{{ fieldErrors()['n_rounds'] }}</small> }
          </label>
          <label>Local epochs (1–3) <input type="number" min="1" max="3" step="1" formControlName="local_epochs" [attr.aria-invalid]="form.controls.local_epochs.touched && form.controls.local_epochs.invalid">
            @if (form.controls.local_epochs.touched && form.controls.local_epochs.invalid) { <small class="error">Enter a whole number from 1 to 3.</small> }
            @if (fieldErrors()['local_epochs']) { <small class="error">{{ fieldErrors()['local_epochs'] }}</small> }
          </label>
          @if (form.controls.algorithm.value === 'fedprox') {
            <label>FedProx μ (positive) <input type="number" min="0.000001" step="any" formControlName="mu" [attr.aria-invalid]="form.controls.mu.touched && form.controls.mu.invalid">
              @if (form.controls.mu.touched && form.controls.mu.invalid) { <small class="error">Enter a positive μ value.</small> }
              @if (fieldErrors()['mu']) { <small class="error">{{ fieldErrors()['mu'] }}</small> }
            </label>
          }
        </div>
        @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
        <button type="submit" [disabled]="busy()">{{ busy() ? 'Saving…' : 'Save experiment' }}</button>
      </form>
    </section>
  `,
})
export class ExperimentFormComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly id = this.route.snapshot.paramMap.get('id');
  readonly error = signal('');
  readonly fieldErrors = signal<Record<string, string>>({});
  readonly busy = signal(false);
  readonly form = this.fb.nonNullable.group({
    name: ['', [Validators.required, Validators.maxLength(120)]],
    algorithm: ['fedavg' as 'fedavg' | 'fedprox', Validators.required],
    n_clients: [4, [Validators.required, Validators.min(2), Validators.max(10), Validators.pattern(/^\d+$/)]],
    n_rounds: [2, [Validators.required, Validators.min(1), Validators.max(5), Validators.pattern(/^\d+$/)]],
    local_epochs: [1, [Validators.required, Validators.min(1), Validators.max(3), Validators.pattern(/^\d+$/)]],
    mu: [0.3, [Validators.required, Validators.min(0.000001)]],
  });

  ngOnInit(): void {
    const mu = this.form.controls.mu;
    this.form.controls.algorithm.valueChanges.subscribe((algorithm) => {
      if (algorithm === 'fedprox') mu.enable({ emitEvent: false });
      else mu.disable({ emitEvent: false });
    });
    mu.disable({ emitEvent: false });
    if (!this.id) return;
    this.api.getExperiment(this.id).subscribe({
      next: (item) => this.form.patchValue({ ...item.config, name: item.name, mu: item.config.mu ?? 0.3 }),
      error: (error: HttpErrorResponse) => this.error.set(requestMessage(error)),
    });
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.error.set('Correct the highlighted values before saving.');
      return;
    }
    this.error.set('');
    this.fieldErrors.set({});
    const values = this.form.getRawValue();
    const payload: ExperimentFormValue = {
      name: values.name.trim(), algorithm: values.algorithm,
      n_clients: values.n_clients, n_rounds: values.n_rounds, local_epochs: values.local_epochs,
      ...(values.algorithm === 'fedprox' ? { mu: values.mu } : {}),
    };
    this.busy.set(true);
    this.api.saveExperiment(payload, this.id ?? undefined).subscribe({
      next: (item) => void this.router.navigate(['/experiments', item.id]),
      error: (error: HttpErrorResponse) => {
        this.fieldErrors.set(fieldMessages(error));
        this.error.set(requestMessage(error));
        this.busy.set(false);
      },
    });
  }
}
