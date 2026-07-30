import type { Competition } from './competitions';
import { mapRowToCompetition, type SupabaseCompetitionRow } from './competitionMapper';
import { request } from './apiClient';

const CACHE_KEY = 'backend_competitions_cache_v1';
let cached: Competition[] | null = null;

/**
 * 页面首次加载优先使用上次从后端成功同步的浏览器缓存。
 * 没有缓存时才访问 Render/Supabase，避免每次刷新都等待网络。
 */
export async function fetchCompetitions(): Promise<Competition[]> {
  if (cached) return cached;

  const stored = readStoredCache();
  if (stored) {
    cached = stored;
    return stored;
  }

  return refreshCompetitions();
}

/**
 * 强制从 Render 后端重新读取 Supabase，并同步内存与浏览器缓存。
 * 未来“更新竞赛库”按钮应在后端更新完成后调用此函数。
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
  localStorage.setItem(
    CACHE_KEY,
    JSON.stringify({
      items: cached,
      updatedAt: new Date().toISOString(),
    }),
  );
  return cached;
}

function readStoredCache(): Competition[] | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { items?: Competition[] };
    return Array.isArray(parsed.items) ? parsed.items : null;
  } catch {
    localStorage.removeItem(CACHE_KEY);
    return null;
  }
}

interface CompetitionPage {
  success: boolean;
  items: SupabaseCompetitionRow[];
  total: number;
  page: number;
  page_size: number;
  source: 'supabase';
}
