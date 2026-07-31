import { ConfigProvider, Tabs, Spin } from 'antd';
import { useState, useEffect } from 'react';

import { AuthProvider, useAuth } from './contexts/AuthContext';
import { CompetitionsProvider } from './contexts/CompetitionsContext';
import { CompetitionsDataProvider } from './contexts/CompetitionsDataContext';
import { NavigationProvider } from './contexts/NavigationContext';
import { AppLayout } from './layouts/AppLayout';
import { LoginPage } from './pages/LoginPage';
import { AIRecommendation } from './pages/AIRecommendation';
import { CompetitionsLibrary } from './pages/CompetitionsLibrary';
import { Home } from './pages/Home';
import { MyCompetitions } from './pages/MyCompetitions';
import { AdminDashboard } from './pages/AdminDashboard';
import { designTokens } from './styles/tokens';

function AppShell() {
  const { user, loading, isAdmin } = useAuth();
  const [activeKey, setActiveKey] = useState('home');
  const [showLogin, setShowLogin] = useState(false);

  useEffect(() => {
    if (!loading && isAdmin) {
      setActiveKey('admin');
    }
  }, [loading, isAdmin]);

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (showLogin) {
    return <LoginPage onSuccess={() => setShowLogin(false)} />;
  }

  const tabItems = isAdmin
    ? [
        { key: 'admin', label: '管理', children: <AdminDashboard /> },
        { key: 'library', label: '竞赛库', children: <CompetitionsLibrary /> },
      ]
    : [
        { key: 'home', label: '首页', children: <Home /> },
        { key: 'ai', label: 'AI推荐', children: <AIRecommendation /> },
        { key: 'library', label: '竞赛库', children: <CompetitionsLibrary /> },
        { key: 'mine', label: '我的竞赛', children: <MyCompetitions /> },
      ];

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: designTokens.colorPrimary,
          borderRadius: designTokens.borderRadiusSmall,
        },
      }}
    >
      <NavigationProvider navigateTo={(key: string) => setActiveKey(key)}>
        <AppLayout onLoginClick={() => setShowLogin(true)}>
          <Tabs
            activeKey={activeKey}
            onChange={setActiveKey}
            items={tabItems}
            destroyInactiveTabPane={false}
          />
        </AppLayout>
      </NavigationProvider>
    </ConfigProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <CompetitionsDataProvider>
        <CompetitionsProvider>
          <AppShell />
        </CompetitionsProvider>
      </CompetitionsDataProvider>
    </AuthProvider>
  );
}
