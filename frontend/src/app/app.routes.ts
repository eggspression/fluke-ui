import { inject } from '@angular/core';
import { Router, Routes } from '@angular/router';
import { AuthService } from './auth.service';
import { ExperimentDetailComponent } from './experiment-detail';
import { ExperimentFormComponent } from './experiment-form';
import { ExperimentListComponent } from './experiment-list';
import { LoginComponent } from './login';
import { RunDetailComponent } from './run-detail';

const signedIn = () => inject(AuthService).token() ? true : inject(Router).parseUrl('/login');

export const routes: Routes = [
  { path: 'login', component: LoginComponent },
  { path: 'experiments', component: ExperimentListComponent, canActivate: [signedIn] },
  { path: 'experiments/new', component: ExperimentFormComponent, canActivate: [signedIn] },
  { path: 'experiments/:id/edit', component: ExperimentFormComponent, canActivate: [signedIn] },
  { path: 'experiments/:id', component: ExperimentDetailComponent, canActivate: [signedIn] },
  { path: 'runs/:id', component: RunDetailComponent, canActivate: [signedIn] },
  { path: '', pathMatch: 'full', redirectTo: 'experiments' },
  { path: '**', redirectTo: 'experiments' },
];
