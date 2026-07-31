import { request } from './apiClient';

export interface RefreshStartResponse {
  success: boolean;
  status: 'accepted' | 'already_running' | 'rate_limited';
  message: string;
  job_id?: number;
  retry_after_seconds?: number;
}

export interface RefreshJob {
  id: number;
  status: 'queued' | 'dispatched' | 'running' | 'completed' | 'partial' | 'failed';
  items_new?: number;
  items_changed?: number;
  items_deleted?: number;
  error_message?: string | null;
}

export interface RefreshStatusResponse {
  success: boolean;
  job: RefreshJob | null;
}

export async function startCompetitionRefresh(): Promise<RefreshStartResponse> {
  return request<RefreshStartResponse>('/api/competitions/refresh', {
    method: 'POST',
    body: {},
  });
}

export async function getCompetitionRefreshStatus(): Promise<RefreshStatusResponse> {
  return request<RefreshStatusResponse>('/api/competitions/refresh/status');
}
