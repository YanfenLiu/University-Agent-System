import { createContext, useContext, type ReactNode } from 'react';

interface NavigationContextType {
  navigateTo: (key: string) => void;
}

const NavigationContext = createContext<NavigationContextType | null>(null);

export function NavigationProvider({
  navigateTo,
  children,
}: NavigationContextType & { children: ReactNode }) {
  return (
    <NavigationContext.Provider value={{ navigateTo }}>
      {children}
    </NavigationContext.Provider>
  );
}

export function useNavigation(): NavigationContextType {
  const ctx = useContext(NavigationContext);
  if (!ctx) throw new Error('useNavigation must be used within NavigationProvider');
  return ctx;
}
