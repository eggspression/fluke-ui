export interface User {
  id: string;
  email: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  user: User;
}

export interface RunConfig {
  algorithm: 'fedavg' | 'fedprox';
  n_clients: number;
  n_rounds: number;
  local_epochs: number;
  mu?: number;
}

export interface ExperimentFormValue extends RunConfig {
  name: string;
}

export interface Experiment {
  id: string;
  name: string;
  config: RunConfig;
  created_at: string;
  updated_at: string;
}

export interface Run {
  id: string;
  experiment_id: string;
  config: RunConfig;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  result: { algorithm: 'fedavg' | 'fedprox'; rounds: { round: number; accuracy: number }[] } | null;
  failure_message: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
}
