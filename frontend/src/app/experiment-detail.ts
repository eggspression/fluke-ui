import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { forkJoin } from 'rxjs';
import { ApiService } from './api.service';
import { requestMessage } from './errors';
import { Experiment, Run } from './models';

@Component({
  selector: 'app-experiment-detail',
  imports: [DatePipe, RouterLink],
  template: `
    <a routerLink="/experiments">← Experiments</a>
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    @if (experiment(); as item) {
      <header class="page-header"><div><h1>{{ item.name }}</h1><p>{{ item.config.algorithm }} · MNIST · CPU</p></div>
        <div class="actions">
          @if (!runs().length) { <a class="button secondary" [routerLink]="['/experiments', item.id, 'edit']">Edit</a> }
          <button [disabled]="launching()" (click)="launch()">{{ launching() ? 'Launching…' : 'Launch run' }}</button>
        </div></header>
      <section class="card"><h2>Configuration</h2><dl class="facts">
        <div><dt>Clients</dt><dd>{{ item.config.n_clients }}</dd></div>
        <div><dt>Rounds</dt><dd>{{ item.config.n_rounds }}</dd></div>
        <div><dt>Local epochs</dt><dd>{{ item.config.local_epochs }}</dd></div>
        @if (item.config.mu !== undefined) { <div><dt>FedProx μ</dt><dd>{{ item.config.mu }}</dd></div> }
      </dl></section>
      <section><h2>Run history</h2>
        @if (runs().length) {
          <div class="card table-wrap"><table><thead><tr><th>Queued</th><th>Status</th><th>Run</th></tr></thead><tbody>
            @for (run of runs(); track run.id) {
              <tr><td>{{ run.created_at | date:'medium' }}</td><td><span class="status">{{ run.status }}</span></td>
                <td><a [routerLink]="['/runs', run.id]">View run</a></td></tr>
            }
          </tbody></table></div>
        } @else { <p class="card">No runs yet. Launch one to see its status and results.</p> }
      </section>
    }
  `,
})
export class ExperimentDetailComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly id = this.route.snapshot.paramMap.get('id')!;
  readonly experiment = signal<Experiment | null>(null);
  readonly runs = signal<Run[]>([]);
  readonly error = signal('');
  readonly launching = signal(false);

  ngOnInit(): void {
    forkJoin({ experiment: this.api.getExperiment(this.id), runs: this.api.listRuns(this.id) }).subscribe({
      next: ({ experiment, runs }) => { this.experiment.set(experiment); this.runs.set(runs); },
      error: (error: HttpErrorResponse) => this.error.set(requestMessage(error)),
    });
  }

  launch(): void {
    this.error.set('');
    this.launching.set(true);
    this.api.launchRun(this.id).subscribe({
      next: (run) => void this.router.navigate(['/runs', run.id]),
      error: (error: HttpErrorResponse) => {
        this.error.set(requestMessage(error));
        this.launching.set(false);
      },
    });
  }
}
