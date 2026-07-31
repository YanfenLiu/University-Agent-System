import { createContext, useContext, useEffect, useState, useCallback, useRef, type ReactNode } from 'react';
import { type Competition } from '../services/competitions';
import { useAuth } from './AuthContext';
import { request } from '../services/apiClient';

interface CompetitionsContextType {
  myCompetitions: Competition[];
  addCompetition: (competition: Competition) => void;
  removeCompetition: (id: number) => void;
  isJoined: (id: number) => boolean;
  loading: boolean;
}

const CompetitionsContext = createContext<CompetitionsContextType | null>(null);

async function loadFromServer(): Promise<Competition[]> {
  const res = await request<{ items: Competition[] }>('/api/saved-competitions');
  return res.items || [];
}

export function CompetitionsProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const prevUserId = useRef<string | undefined>(undefined);
  const [myCompetitions, setMyCompetitions] = useState<Competition[]>([]);
  const [loading, setLoading] = useState(false);

  // 登录/退出 → 重新从服务端加载
  useEffect(() => {
    if (prevUserId.current === user?.id) return;
    prevUserId.current = user?.id;

    if (!user) {
      setMyCompetitions([]);
      return;
    }

    setLoading(true);
    loadFromServer()
      .then(setMyCompetitions)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [user]);

  const addCompetition = useCallback((competition: Competition) => {
    setMyCompetitions((prev) => {
      if (prev.some((item) => item.id === competition.id)) return prev;
      return [...prev, competition];
    });
    if (user) {
      request(`/api/saved-competitions/${competition.id}`, { method: 'POST' }).catch(() => {});
    }
  }, [user]);

  const removeCompetition = useCallback((id: number) => {
    setMyCompetitions((prev) => prev.filter((item) => item.id !== id));
    if (user) {
      request(`/api/saved-competitions/${id}`, { method: 'DELETE' }).catch(() => {});
    }
  }, [user]);

  const isJoined = useCallback(
    (id: number) => myCompetitions.some((item) => item.id === id),
    [myCompetitions],
  );

  return (
    <CompetitionsContext.Provider value={{ myCompetitions, addCompetition, removeCompetition, isJoined, loading }}>
      {children}
    </CompetitionsContext.Provider>
  );
}

export function useCompetitions(): CompetitionsContextType {
  const ctx = useContext(CompetitionsContext);
  if (!ctx) throw new Error('useCompetitions must be used within CompetitionsProvider');
  return ctx;
}
