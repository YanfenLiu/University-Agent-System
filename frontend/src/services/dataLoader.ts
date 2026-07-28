import type { Competition } from './competitions';
import { fetchCompetitionsFromSupabase } from './supabaseService';
import { mapRowToCompetition } from './competitionMapper';
import type { SupabaseCompetitionRow } from './supabaseClient';

// 在 Vite 中可以直接 import JSON（会被编译进 bundle）
import competitionsData from '../data/competitions.json';

let cached: Competition[] | null = null;

/**
 * 获取竞赛数据，优先级：
 * 1. 本地静态 JSON（秒开）
 * 2. Supabase 在线数据（慢，但有更新）
 * 
 * 本地 JSON 加载到后，后台静默尝试更新 Supabase 数据。
 */
export async function fetchCompetitions(): Promise<Competition[]> {
  // 已经缓存过 → 直接返回
  if (cached) return cached;

  // 1. 尝试从本地 JSON 加载（同步，毫秒级）
  try {
    if (Array.isArray(competitionsData) && competitionsData.length > 0) {
      const local = (competitionsData as SupabaseCompetitionRow[]).map(mapRowToCompetition);
      console.log('[DataLoader] 📦 本地 JSON 加载', local.length, '条');
      cached = local;

      // 后台静默更新 Supabase（不阻塞 UI）
      fetchSupabaseInBackground();

      return local;
    }
  } catch (e) {
    console.warn('[DataLoader] 本地 JSON 加载失败:', e);
  }

  // 2. 降级到 Supabase
  console.log('[DataLoader] ⏳ 降级到 Supabase...');
  const supabaseData = await fetchCompetitionsFromSupabase();
  if (supabaseData && supabaseData.length > 0) {
    cached = supabaseData;
    return supabaseData;
  }

  return [];
}

/**
 * 后台静默更新 Supabase 数据
 */
async function fetchSupabaseInBackground() {
  try {
    const fresh = await fetchCompetitionsFromSupabase();
    if (fresh && fresh.length > 0) {
      cached = fresh;
      console.log('[DataLoader] 🔄 后台更新完成:', fresh.length, '条');
    }
  } catch {
    // 静默失败，继续用本地数据
  }
}
