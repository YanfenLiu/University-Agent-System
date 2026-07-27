import { getSupabaseClient, type SupabaseCompetitionRow } from './supabaseClient';
import type { Competition, CompetitionDifficulty } from './competitions';

const CACHE_KEY = 'supabase_competitions_cache_v3';
// 如果需要手动刷新缓存，在 Console 执行: localStorage.removeItem('supabase_competitions_cache_v3')

/**
 * 从 Supabase 获取全部竞赛数据，并转换为前端的 Competition 类型。
 * 如果 Supabase 未配置，返回 null。
 */
export async function fetchCompetitionsFromSupabase(): Promise<Competition[] | null> {
  // 尝试从缓存读取
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    if (cached) {
      const parsed: Competition[] = JSON.parse(cached);
      if (Array.isArray(parsed) && parsed.length > 0) {
        console.log('[Supabase/Service] 📦 从缓存加载', parsed.length, '条');
        return parsed;
      }
    }
  } catch { /* 忽略缓存错误 */ }

  const client = getSupabaseClient();
  if (!client) {
    console.warn('[Supabase/Service] Supabase 客户端不可用');
    return null;
  }

  try {
    console.log('[Supabase/Service] 🔍 正在查询 competitions 表...');

    // 热身查询：唤醒 Supabase 冷启动连接
    console.log('[Supabase/Service] 🌡️ 预热连接...');
    const warmupController = new AbortController();
    const warmupTimer = setTimeout(() => warmupController.abort(), 20000);
    await client
      .from('competitions')
      .select('id', { count: 'exact', head: true })
      .abortSignal(warmupController.signal);
    clearTimeout(warmupTimer);
    console.log('[Supabase/Service] 🌡️ 预热完成，开始加载数据...');

    // 主查询：一次性加载全部（仅必要字段，不加 count 以减小负载）
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000);

    const { data, error } = await client
      .from('competitions')
      .select('id, title, url, source, description, organizer, regist_end, contest_end, category, level')
      .order('collected_at', { ascending: false })
      .abortSignal(controller.signal);

      clearTimeout(timeoutId);

    if (error) {
      console.error('[Supabase/Service] ❌ 查询失败:', error.message);
      return null;
    }

    console.log('[Supabase/Service] ✅ 查询成功, 行数:', data?.length ?? 0);

    if (!data || data.length === 0) {
      console.warn('[Supabase/Service] competitions 表为空');
      return [];
    }

    const mapped = data.map(mapRowToCompetition);
    console.log('[Supabase/Service] ✅ 映射完成, 返回', mapped.length, '条');

    // 写入 sessionStorage 缓存，后续刷新秒加载
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(mapped));
    } catch { /* 忽略 */ }

    return mapped;
  } catch (error) {
    console.error('[Supabase/Service] 获取竞赛数据失败:', error);
    return null;
  }
}

/**
 * 将数据库行映射为前端的 Competition 类型
 */
function mapRowToCompetition(row: SupabaseCompetitionRow): Competition {
  // 根据 level 字段映射为 difficulty
  const difficulty = mapDifficulty(row.level);

  // 截止时间优先取 regist_end，其次 contest_end
  const deadline = row.regist_end || row.contest_end || '待核实';

  // 标签：从 category 和 source 推导
  const tags = buildTags(row);

  // 简介：优先 description，否则从 raw_text 截取
  const summary = row.description
    ? row.description
    : row.raw_text
      ? extractBrief(row.raw_text, 120)
      : '';

  // status：根据时间推断
  const status = inferStatus(row.regist_end, row.contest_end);

  return {
    id: row.id,
    name: row.title,
    summary,
    difficulty,
    deadline,
    officialUrl: row.url,
    reason: '', // 数据库不存推荐理由，由 AI 后端生成
    tags,
    status,
    organizer: row.organizer || undefined,
  };
}

/**
 * level → difficulty 映射
 *   国际级/国家级 → 挑战
 *   省级          → 进阶
 *   校级/无       → 入门
 */
function mapDifficulty(level: string): CompetitionDifficulty {
  if (!level) return '入门';
  if (level.includes('国际') || level.includes('国家')) return '挑战';
  if (level.includes('省')) return '进阶';
  return '入门';
}

/**
 * 从 category 和 title 构建标签
 */
function buildTags(row: SupabaseCompetitionRow): string[] {
  const tags: string[] = [];

  // 从 category 解析
  if (row.category) {
    const parts = row.category.split(/[,，、/]/).map(s => s.trim()).filter(Boolean);
    tags.push(...parts);
  }

  // 添加来源标签
  if (row.source) {
    const sourceLabel = sourceToLabel(row.source);
    if (sourceLabel && !tags.includes(sourceLabel)) {
      tags.push(sourceLabel);
    }
  }

  // 默认至少一个标签
  if (tags.length === 0) {
    tags.push('竞赛');
  }

  return tags;
}

/**
 * 来源代码 → 可读标签
 */
function sourceToLabel(source: string): string {
  const map: Record<string, string> = {
    saikr: '赛氪',
    datafountain: 'DataFountain',
    kaggle: 'Kaggle',
    tianchi: '天池',
  };
  return map[source] || source;
}

/**
 * 根据截止日期推断状态
 */
function inferStatus(registEnd: string, contestEnd: string): '报名中' | '热门' | '推荐' {
  const now = new Date();
  const deadline = registEnd || contestEnd;
  if (!deadline) return '推荐';

  try {
    const d = new Date(deadline);
    if (isNaN(d.getTime())) return '推荐';
    // 如果截止日期在未来 30 天内 → 热门
    const diffDays = (d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
    if (diffDays > 0 && diffDays <= 30) return '热门';
    if (diffDays > 30) return '报名中';
    return '推荐';
  } catch {
    return '推荐';
  }
}

/**
 * 从原始文本中提取简介
 */
function extractBrief(rawText: string, maxLen: number): string {
  try {
    const parsed = JSON.parse(rawText);
    if (parsed.description) return parsed.description.slice(0, maxLen);
    if (parsed.summary) return parsed.summary.slice(0, maxLen);
    return '';
  } catch {
    return rawText.slice(0, maxLen);
  }
}
