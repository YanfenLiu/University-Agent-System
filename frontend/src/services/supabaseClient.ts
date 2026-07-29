import { createClient, type SupabaseClient } from '@supabase/supabase-js';

/* ===== 环境变量集中读取 ===== */

export function getSupabaseUrl(): string {
  return import.meta.env.VITE_SUPABASE_URL ?? '';
}

export function getSupabaseAnonKey(): string {
  return import.meta.env.VITE_SUPABASE_ANON_KEY ?? '';
}

/** 检查环境变量是否已正确配置 */
export function isSupabaseConfigured(): boolean {
  const url = getSupabaseUrl();
  const key = getSupabaseAnonKey();
  const configured = !!(url && key && url !== 'your_supabase_url_here' && key !== 'your_supabase_anon_key_here');
  console.log('[Supabase/Client] URL存在:', !!url, '| Key存在:', !!key, '| 已配置:', configured);
  return configured;
}

let supabaseInstance: SupabaseClient | null = null;

/**
 * 获取 Supabase 客户端单例。
 * 若环境变量未配置，返回 null，上层可回退到本地 JSON 数据。
 */
export function getSupabaseClient(): SupabaseClient | null {
  if (supabaseInstance) return supabaseInstance;

  if (!isSupabaseConfigured()) {
    if (import.meta.env.DEV) {
      console.warn(
        '[Supabase] 未配置 VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY，请检查 .env 文件。',
      );
    }
    return null;
  }

  supabaseInstance = createClient(getSupabaseUrl(), getSupabaseAnonKey(), {
    auth: { persistSession: false },
  });

  return supabaseInstance;
}

/** Supabase competitions 表行类型（与数据库结构对应） */
export interface SupabaseCompetitionRow {
  id: number;
  title: string;
  url: string;
  source?: string;
  publish_date?: string;
  description?: string;
  organizer?: string;
  organizer_list?: string[];
  co_organizers?: string[];
  supporters?: string[];
  regist_start?: string;
  regist_end?: string;
  contest_start?: string;
  contest_end?: string;
  category?: string;
  level?: string;
  attachments?: string[];
  raw_text?: string;
  collected_at?: string;
  updated_at?: string;
}
