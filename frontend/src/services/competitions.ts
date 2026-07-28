/* ===================================================================
 * 竞赛数据 — 纯类型定义
 * 数据加载由 CompetitionsDataContext 统一管理 (React Context)
 * 导入此文件不会触发任何副作用
 * =================================================================== */

/* ===== 类型定义 ===== */

export type CompetitionDifficulty = '入门' | '进阶' | '挑战';

/** 后端返回的六维评分详情 */
export interface DimensionalScores {
  major_score?: number;
  interest_score?: number;
  ability_score?: number;
  experience_score?: number;
  grade_score?: number;
  goal_score?: number;
  team_score?: number;
  [key: string]: unknown;
}

export interface Competition {
  id: number;
  name: string;
  summary: string;
  difficulty: CompetitionDifficulty;
  deadline: string;
  officialUrl: string;
  reason: string;
  tags: string[];
  status: '报名中' | '热门' | '推荐';

  /* ---- 后端推荐引擎返回的增强字段（可选） ---- */
  /** 综合匹配分数 (0-100) */
  match_score?: number;
  /** 推荐等级 S/A/B/C */
  recommend_level?: string;
  /** 六维评分明细 */
  detail?: DimensionalScores;
  /** 匹配信号列表 */
  matched_signals?: string[];
  /** 未匹配信号列表 */
  unmatched_signals?: string[];
  /** 风险提示文案 */
  risk?: string;
  /** 建议行动文案 */
  suggested_action?: string;
  /** 发起方/主办方 */
  organizer?: string;
}
