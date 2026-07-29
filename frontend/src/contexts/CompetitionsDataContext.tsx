import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';

import { type Competition } from '../services/competitions';
import { fetchCompetitions, refreshCompetitions } from '../services/dataLoader';

/* ===== Context ===== */

interface CompetitionsDataContextType {
  competitions: Competition[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const CompetitionsDataContext = createContext<CompetitionsDataContextType | null>(null);

/**
 * 竞赛数据提供者。
 * 唯一数据来源为 Supabase，加载完成前返回空数组。
 */
export function CompetitionsDataProvider({ children }: { children: ReactNode }) {
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await refreshCompetitions();
      setCompetitions(data);
      setError(data.length > 0 ? null : '暂无竞赛数据');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '更新竞赛数据失败';
      setError(msg);
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const data = await fetchCompetitions();

        if (cancelled) return;

        if (data.length > 0) {
          console.log('[CompetitionsData] ✅ 成功加载', data.length, '条');
          setCompetitions(data);
          setError(null);
        } else {
          console.warn('[CompetitionsData] ⚠️ 无可用数据');
          setError('暂无竞赛数据');
        }
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : '加载竞赛数据失败';
          setError(msg);
          console.error('[CompetitionsData] ❌ 加载失败:', err);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <CompetitionsDataContext.Provider value={{ competitions, loading, error, refresh }}>
      {children}
    </CompetitionsDataContext.Provider>
  );
}

/**
 * Hook — 获取竞赛数据列表。
 * Supabase 数据到达前返回 []，到达后自动更新。
 */
export function useCompetitionsData(): Competition[] {
  const ctx = useContext(CompetitionsDataContext);
  if (!ctx) {
    throw new Error('useCompetitionsData must be used within CompetitionsDataProvider');
  }
  return ctx.competitions;
}

/**
 * Hook — 获取加载状态。
 */
export function useCompetitionsLoading(): boolean {
  const ctx = useContext(CompetitionsDataContext);
  if (!ctx) {
    throw new Error('useCompetitionsLoading must be used within CompetitionsDataProvider');
  }
  return ctx.loading;
}

/**
 * Hook — 获取错误信息。
 */
export function useCompetitionsError(): string | null {
  const ctx = useContext(CompetitionsDataContext);
  if (!ctx) {
    throw new Error('useCompetitionsError must be used within CompetitionsDataProvider');
  }
  return ctx.error;
}

/** 未来“更新竞赛库”按钮调用：后端更新完成后强制同步 Supabase 数据。 */
export function useRefreshCompetitions(): () => Promise<void> {
  const ctx = useContext(CompetitionsDataContext);
  if (!ctx) {
    throw new Error('useRefreshCompetitions must be used within CompetitionsDataProvider');
  }
  return ctx.refresh;
}
