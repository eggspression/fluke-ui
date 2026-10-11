import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ApiService } from './api.service';
import { requestMessage } from './errors';
import { Experiment } from './models';

@Component({
  selector: 'app-experiment-list',
  imports: [DatePipe, RouterLink],
  template: `
    <header class="page-header"><div><h1>Experiments</h1><p>Saved MNIST CPU configurations</p></div>
      <a class="button" routerLink="/experiments/new">New experiment</a></header>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    @if (experiments().length) {
      <div class="card table-wrap"><table><thead><tr><th>Name</th><th>Algorithm</th><th>Clients</th><th>Rounds</th><th>Created</th></tr></thead><tbody>
        @for (item of experiments(); track item.id) {
          <tr><td><a [routerLink]="['/experiments', item.id]">{{ item.name }}</a></td>
            <td>{{ item.config.algorithm }}</td><td>{{ item.config.n_clients }}</td>
            <td>{{ item.config.n_rounds }}</td><td>{{ item.created_at | date:'medium' }}</td></tr>
        }
      </tbody></table></div>
    } @else if (!error()) { <p class="card">No experiments yet. Create one to begin.</p> }
  `,
})
export class ExperimentListComponent implements OnInit {
  private readonly api = inject(ApiService);
  readonly experiments = signal<Experiment[]>([]);
  readonly error = signal('');

  ngOnInit(): void {
    this.api.listExperiments().subscribe({
      next: (items) => this.experiments.set(items),
      error: (error: HttpErrorResponse) => this.error.set(requestMessage(error)),
    });
  }
}
