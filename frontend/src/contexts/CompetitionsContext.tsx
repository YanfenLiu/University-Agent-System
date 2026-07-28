import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { type Competition } from '../services/competitions';

const STORAGE_KEY = 'myCompetitions';

interface CompetitionsContextType {
  myCompetitions: Competition[];
  addCompetition: (competition: Competition) => void;
  removeCompetition: (id: number) => void;
  isJoined: (id: number) => boolean;
}

const CompetitionsContext = createContext<CompetitionsContextType | null>(null);

export function CompetitionsProvider({ children }: { children: ReactNode }) {
  const [myCompetitions, setMyCompetitions] = useState<Competition[]>(() => {
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : [];
  });

  // 同步到 localStorage
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(myCompetitions));
  }, [myCompetitions]);

  const addCompetition = (competition: Competition) => {
    setMyCompetitions(prev => {
      if (prev.some(item => item.id === competition.id)) return prev;
      return [...prev, competition];
    });
  };

  const removeCompetition = (id: number) => {
    setMyCompetitions(prev => prev.filter(item => item.id !== id));
  };

  const isJoined = (id: number) => myCompetitions.some(item => item.id === id);

  return (
    <CompetitionsContext.Provider value={{ myCompetitions, addCompetition, removeCompetition, isJoined }}>
      {children}
    </CompetitionsContext.Provider>
  );
}

export function useCompetitions(): CompetitionsContextType {
  const ctx = useContext(CompetitionsContext);
  if (!ctx) throw new Error('useCompetitions must be used within CompetitionsProvider');
  return ctx;
}
