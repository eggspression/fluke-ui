import { DatePipe, PercentPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, OnInit, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { forkJoin, switchMap, takeWhile, timer } from 'rxjs';
import { ApiService } from './api.service';
import { requestMessage } from './errors';
import { Run } from './models';

@Component({
  selector: 'app-run-detail',
  imports: [DatePipe, PercentPipe, RouterLink],
  template: `
    @if (run(); as item) {
      <a [routerLink]="['/experiments', item.experiment_id]">← Experiment</a>
      <header class="page-header"><div><h1>Run detail</h1><p>{{ item.config.algorithm }} · {{ item.config.n_rounds }} rounds</p></div>
        <span class="status large">{{ item.status }}</span></header>
      @if (item.status === 'QUEUED' || item.status === 'RUNNING') { <p>Refreshing about every two seconds.</p> }
      @if (item.status === 'FAILED') { <p class="error" role="alert">{{ item.failure_message || 'Run failed. Inspect the log below.' }}</p> }
      <section class="card"><h2>Run status</h2><dl class="facts">
        <div><dt>Queued</dt><dd>{{ item.created_at | date:'medium' }}</dd></div>
        @if (item.started_at) { <div><dt>Started</dt><dd>{{ item.started_at | date:'medium' }}</dd></div> }
        @if (item.finished_at) { <div><dt>Finished</dt><dd>{{ item.finished_at | date:'medium' }}</dd></div> }
      </dl></section>
      @if (item.result?.rounds?.length) {
        <section><h2>Global accuracy by round</h2><div class="card table-wrap"><table>
          <thead><tr><th>Round</th><th>Accuracy</th></tr></thead><tbody>
          @for (round of item.result!.rounds; track round.round) {
            <tr><td>{{ round.round }}</td><td>{{ round.accuracy | percent:'1.0-2' }}</td></tr>
          }
          </tbody></table></div></section>
      }
      <section><h2>Recent log</h2><pre class="log">{{ log() || 'No log output yet.' }}</pre></section>
    } @else if (!error()) { <p>Loading run…</p> }
    @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
  `,
})
export class RunDetailComponent implements OnInit {
  private readonly api = inject(ApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  readonly id = this.route.snapshot.paramMap.get('id')!;
  readonly run = signal<Run | null>(null);
  readonly log = signal('');
  readonly error = signal('');

  ngOnInit(): void {
    timer(0, 2000).pipe(
      switchMap(() => forkJoin({ run: this.api.getRun(this.id), log: this.api.getRunLogs(this.id) })),
      takeWhile(({ run }) => run.status === 'QUEUED' || run.status === 'RUNNING', true),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: ({ run, log }) => { this.run.set(run); this.log.set(log.text); },
      error: (error: HttpErrorResponse) => this.error.set(requestMessage(error)),
    });
  }
}
