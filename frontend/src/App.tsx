import { ConfigProvider, Tabs } from 'antd';
import { useState } from 'react';

import { CompetitionsProvider } from './contexts/CompetitionsContext';
import { CompetitionsDataProvider } from './contexts/CompetitionsDataContext';
import { NavigationProvider } from './contexts/NavigationContext';
import { AppLayout } from './layouts/AppLayout';
import { AIRecommendation } from './pages/AIRecommendation';
import { CompetitionsLibrary } from './pages/CompetitionsLibrary';
import { Home } from './pages/Home';
import { MyCompetitions } from './pages/MyCompetitions';
import { designTokens } from './styles/tokens';

export default function App() {
  const [activeKey, setActiveKey] = useState('home');

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: designTokens.colorPrimary,
          borderRadius: designTokens.borderRadiusSmall
        }
      }}
    >
      <CompetitionsDataProvider>
      <CompetitionsProvider>
      <NavigationProvider navigateTo={(key: string) => setActiveKey(key)}>
      <AppLayout>
        <Tabs
          activeKey={activeKey}
          onChange={setActiveKey}
          items={[
            {
              key: 'home',
              label: '首页',
              children: <Home />
            },
            {
              key: 'ai',
              label: 'AI推荐',
              children: <AIRecommendation />
            },
            {
              key: 'library',
              label: '竞赛库',
              children: <CompetitionsLibrary />
            },
            {
              key: 'mine',
              label: '我的竞赛',
              children: <MyCompetitions />
            }
          ]}
                />
      </AppLayout>
      </NavigationProvider>
      </CompetitionsProvider>
      </CompetitionsDataProvider>
    </ConfigProvider>
  );
}
