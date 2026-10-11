import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';
import { AuthService } from './auth.service';
import { Experiment, ExperimentFormValue, Run } from './models';

const baseUrl = 'http://127.0.0.1:8000/api/v1';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  private options() {
    return { headers: new HttpHeaders({ Authorization: `Bearer ${this.auth.token()}` }) };
  }

  private handleError(error: HttpErrorResponse) {
    if (error.status === 401) {
      this.auth.logout();
      void this.router.navigateByUrl('/login');
    }
    return throwError(() => error);
  }

  listExperiments() {
    return this.http.get<Experiment[]>(`${baseUrl}/experiments`, this.options()).pipe(
      catchError((error: HttpErrorResponse) => this.handleError(error)),
    );
  }

  getExperiment(id: string) {
    return this.http.get<Experiment>(`${baseUrl}/experiments/${id}`, this.options()).pipe(
      catchError((error: HttpErrorResponse) => this.handleError(error)),
    );
  }

  saveExperiment(form: ExperimentFormValue, id?: string) {
    const url = id ? `${baseUrl}/experiments/${id}` : `${baseUrl}/experiments`;
    const request = id
      ? this.http.patch<Experiment>(url, form, this.options())
      : this.http.post<Experiment>(url, form, this.options());
    return request.pipe(catchError((error: HttpErrorResponse) => this.handleError(error)));
  }

  listRuns(experimentId: string) {
    return this.http.get<Run[]>(`${baseUrl}/experiments/${experimentId}/runs`, this.options()).pipe(
      catchError((error: HttpErrorResponse) => this.handleError(error)),
    );
  }

  launchRun(experimentId: string) {
    return this.http.post<Run>(`${baseUrl}/experiments/${experimentId}/runs`, {}, this.options()).pipe(
      catchError((error: HttpErrorResponse) => this.handleError(error)),
    );
  }

  getRun(id: string) {
    return this.http.get<Run>(`${baseUrl}/runs/${id}`, this.options()).pipe(
      catchError((error: HttpErrorResponse) => this.handleError(error)),
    );
  }

  getRunLogs(id: string) {
    return this.http.get<{ text: string }>(`${baseUrl}/runs/${id}/logs`, this.options()).pipe(
      catchError((error: HttpErrorResponse) => this.handleError(error)),
    );
  }
}
