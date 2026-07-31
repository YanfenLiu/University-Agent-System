import type { Competition, CompetitionDifficulty } from './competitions';

export interface SupabaseCompetitionRow {
  id: number;
  title: string;
  url: string;
  source?: string;
  description?: string;
  summary?: string;
  organizer?: string;
  regist_end?: string;
  contest_end?: string;
  category?: string;
  level?: string;
  collected_at?: string;
  updated_at?: string;
}

/**
 * 将数据库行映射为前端的 Competition 类型
 */
export function mapRowToCompetition(row: SupabaseCompetitionRow): Competition {
  const difficulty = mapDifficulty(row.level);
  const deadline = row.regist_end || row.contest_end || '待核实';
  const tags = buildTags(row);
  const summary = row.summary || row.description || '';
  const status = inferStatus(row.regist_end, row.contest_end);

  return {
    id: row.id,
    name: row.title,
    summary,
    difficulty,
    deadline,
    officialUrl: row.url,
    reason: '',
    tags,
    status,
    organizer: row.organizer || undefined,
  };
}

function mapDifficulty(level?: string): CompetitionDifficulty {
  if (!level) return '入门';
  if (level.includes('国际') || level.includes('国家')) return '挑战';
  if (level.includes('省')) return '进阶';
  return '入门';
}

function buildTags(row: SupabaseCompetitionRow): string[] {
  const tags: string[] = [];
  if (row.category) {
    const parts = row.category.split(/[,，、/]/).map(s => s.trim()).filter(Boolean);
    tags.push(...parts);
  }
  if (row.source) {
    const label = sourceToLabel(row.source);
    if (label && !tags.includes(label)) tags.push(label);
  }
  if (tags.length === 0) tags.push('竞赛');
  return tags;
}

function sourceToLabel(source: string): string {
  const map: Record<string, string> = {
    saikr: '赛氪', datafountain: 'DataFountain',
    kaggle: 'Kaggle', tianchi: '天池',
  };
  return map[source] || source;
}

function inferStatus(registEnd?: string, contestEnd?: string): '报名中' | '热门' | '推荐' {
  const now = new Date();
  const deadline = registEnd || contestEnd;
  if (!deadline) return '推荐';
  try {
    const d = new Date(deadline);
    if (isNaN(d.getTime())) return '推荐';
    const diffDays = (d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
    if (diffDays > 0 && diffDays <= 30) return '热门';
    if (diffDays > 30) return '报名中';
    return '推荐';
  } catch { return '推荐'; }
}
