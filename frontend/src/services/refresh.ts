import { request } from './apiClient';

export interface RefreshStartResponse {
  success: boolean;
  status: 'accepted' | 'already_running' | 'rate_limited';
  message: string;
  job_id?: number;
  retry_after_seconds?: number;
}

export async function startCompetitionRefresh(): Promise<RefreshStartResponse> {
  return request<RefreshStartResponse>('/api/competitions/refresh', {
    method: 'POST',
    body: {},
  });
}
