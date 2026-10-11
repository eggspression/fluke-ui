import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { ExperimentFormComponent } from './experiment-form';

@Component({ template: '' })
class EmptyPage {}

describe('experiment form', () => {
  it('sends only allowed FedAvg fields with defaults', () => {
    TestBed.configureTestingModule({
      imports: [ExperimentFormComponent],
      providers: [
        provideHttpClient(), provideHttpClientTesting(),
        provideRouter([{ path: 'experiments/:id', component: EmptyPage }]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({}) } } },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ExperimentFormComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    (element.querySelector('[formControlName="name"]') as HTMLInputElement).value = 'First proof';
    (element.querySelector('[formControlName="name"]') as HTMLInputElement).dispatchEvent(new Event('input'));
    (element.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'));
    const request = http.expectOne('http://127.0.0.1:8000/api/v1/experiments');
    expect(request.request.body).toEqual({
      name: 'First proof', algorithm: 'fedavg', n_clients: 4, n_rounds: 2, local_epochs: 1,
    });
    request.flush({ id: 'e1', name: 'First proof', config: request.request.body,
      created_at: '2026-10-10T12:00:00Z', updated_at: '2026-10-10T12:00:00Z' });
    http.verify();
  });

  it('shows server validation errors beside the offending field', () => {
    TestBed.configureTestingModule({
      imports: [ExperimentFormComponent],
      providers: [
        provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({}) } } },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ExperimentFormComponent);
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const name = element.querySelector('[formControlName="name"]') as HTMLInputElement;
    name.value = 'Bad'; name.dispatchEvent(new Event('input'));
    (element.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'));
    http.expectOne('http://127.0.0.1:8000/api/v1/experiments').flush(
      { detail: [{ loc: ['body', 'name'], msg: 'Name is invalid', type: 'value_error' }] },
      { status: 422, statusText: 'Unprocessable Entity' },
    );
    fixture.detectChanges();
    expect(element.textContent).toContain('Name is invalid');
    http.verify();
  });

  it('includes positive mu only for FedProx', () => {
    TestBed.configureTestingModule({
      imports: [ExperimentFormComponent],
      providers: [
        provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({}) } } },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ExperimentFormComponent);
    fixture.detectChanges();
    fixture.componentInstance.form.patchValue({ name: 'Prox proof', algorithm: 'fedprox', mu: 0.4 });
    fixture.componentInstance.submit();
    const request = http.expectOne('http://127.0.0.1:8000/api/v1/experiments');
    expect(request.request.body).toEqual({
      name: 'Prox proof', algorithm: 'fedprox', n_clients: 4, n_rounds: 2,
      local_epochs: 1, mu: 0.4,
    });
    request.flush({ detail: 'failed' }, { status: 500, statusText: 'Server Error' });
    http.verify();
  });

  it('saves FedAvg after switching away from an invalid FedProx mu', () => {
    TestBed.configureTestingModule({
      imports: [ExperimentFormComponent],
      providers: [
        provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({}) } } },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ExperimentFormComponent);
    fixture.detectChanges();
    fixture.componentInstance.form.patchValue({ name: 'Average proof', algorithm: 'fedprox', mu: 0 });
    fixture.componentInstance.form.controls.algorithm.setValue('fedavg');
    fixture.componentInstance.submit();
    const request = http.expectOne('http://127.0.0.1:8000/api/v1/experiments');
    expect(request.request.body).toEqual({
      name: 'Average proof', algorithm: 'fedavg', n_clients: 4, n_rounds: 2, local_epochs: 1,
    });
    request.flush({ detail: 'failed' }, { status: 500, statusText: 'Server Error' });
    http.verify();
  });

  it('shows the local error beside an invalid numeric input', () => {
    TestBed.configureTestingModule({
      imports: [ExperimentFormComponent],
      providers: [
        provideHttpClient(), provideHttpClientTesting(), provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({}) } } },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ExperimentFormComponent);
    fixture.detectChanges();
    fixture.componentInstance.form.patchValue({ name: 'Bad clients', n_clients: 11 });
    fixture.componentInstance.submit();
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('[formControlName="n_clients"]') as HTMLInputElement;
    expect(input.parentElement?.textContent).toContain('Enter a whole number from 2 to 10.');
    http.expectNone('http://127.0.0.1:8000/api/v1/experiments');
  });
});
