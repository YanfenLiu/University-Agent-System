import type { Competition } from './competitions';
import { mapRowToCompetition, type SupabaseCompetitionRow } from './competitionMapper';
import { request } from './apiClient';

let cached: Competition[] | null = null;
let lastFetchTime = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 分钟后自动刷新

/**
 * 加载竞赛数据：优先返回缓存，缓存过期时静默刷新。
 * 调用方应处理 loading 状态。
 */
export async function fetchCompetitions(): Promise<Competition[]> {
  const now = Date.now();

  // 缓存未过期，直接返回
  if (cached && now - lastFetchTime < CACHE_TTL) {
    return cached;
  }

  return refreshCompetitions();
}

/**
 * 强制从后端重新拉取，刷新缓存。
 */
export async function refreshCompetitions(): Promise<Competition[]> {
  const pageSize = 500;
  const first = await request<CompetitionPage>('/api/competitions?page=1&page_size=500');
  const rows = [...first.items];
  const pages = Math.ceil(first.total / pageSize);

  for (let page = 2; page <= pages; page += 1) {
    const result = await request<CompetitionPage>(
      `/api/competitions?page=${page}&page_size=${pageSize}`,
    );
    rows.push(...result.items);
  }

  cached = rows.map(mapRowToCompetition);
  lastFetchTime = Date.now();
  return cached;
}

interface CompetitionPage {
  success: boolean;
  items: SupabaseCompetitionRow[];
  total: number;
  page: number;
  page_size: number;
  source: 'supabase';
}
