import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { vi } from 'vitest';
import { RunDetailComponent } from './run-detail';

describe('run detail polling', () => {
  it('shows final accuracy and stops polling once completed', () => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      imports: [RunDetailComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: 'r1' }) } } }],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(RunDetailComponent);
    fixture.detectChanges();
    vi.advanceTimersByTime(1);
    const active = {
      id: 'r1', experiment_id: 'e1', config: { algorithm: 'fedavg', n_clients: 2, n_rounds: 2, local_epochs: 1 },
      status: 'RUNNING', result: null, failure_message: null,
      created_at: '', updated_at: '', started_at: '', finished_at: null,
    };
    http.expectOne('http://127.0.0.1:8000/api/v1/runs/r1').flush(active);
    http.expectOne('http://127.0.0.1:8000/api/v1/runs/r1/logs').flush({ text: 'Round 1\n' });
    vi.advanceTimersByTime(2000);
    http.expectOne('http://127.0.0.1:8000/api/v1/runs/r1').flush({ ...active, status: 'COMPLETED',
      result: { algorithm: 'fedavg', rounds: [{ round: 1, accuracy: 0.25 }, { round: 2, accuracy: 0.5 }] } });
    http.expectOne('http://127.0.0.1:8000/api/v1/runs/r1/logs').flush({ text: 'Training completed\n' });
    fixture.detectChanges();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('50%');
    vi.advanceTimersByTime(4000);
    http.expectNone('http://127.0.0.1:8000/api/v1/runs/r1');
    fixture.destroy();
    http.verify();
    vi.useRealTimers();
  });

  it('shows a failed run reason and its log', () => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      imports: [RunDetailComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: 'r2' }) } } }],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(RunDetailComponent);
    fixture.detectChanges();
    vi.advanceTimersByTime(1);
    http.expectOne('http://127.0.0.1:8000/api/v1/runs/r2').flush({
      id: 'r2', experiment_id: 'e1', config: { algorithm: 'fedavg', n_clients: 2, n_rounds: 2, local_epochs: 1 },
      status: 'FAILED', result: null, failure_message: 'Runner exited with code 1',
      created_at: '', updated_at: '', started_at: '', finished_at: '',
    });
    http.expectOne('http://127.0.0.1:8000/api/v1/runs/r2/logs').flush({ text: 'Runner failed\n' });
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent || '';
    expect(text).toContain('Runner exited with code 1');
    expect(text).toContain('Runner failed');
    fixture.destroy();
    http.verify();
    vi.useRealTimers();
  });
});
