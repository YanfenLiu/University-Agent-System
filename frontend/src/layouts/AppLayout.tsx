import { Layout, Menu, Typography } from 'antd';
import { ReactNode } from 'react';
import { designTokens } from '../styles/tokens';

interface AppLayoutProps { children: ReactNode; }

export function AppLayout({ children }: AppLayoutProps) {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Header style={{ background: designTokens.colorBgContainer, display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxShadow: designTokens.boxShadow }}>
        <Typography.Title level={4} style={{ margin: 0, color: designTokens.colorPrimary }}>赛智通</Typography.Title>
      </Layout.Header>
      <Layout.Content style={{ padding: designTokens.spacing.xl }}>{children}</Layout.Content>
      <Layout.Footer style={{ textAlign: 'center', color: designTokens.colorTextSecondary }}>用 AI 帮你找到更适合的竞赛</Layout.Footer>
    </Layout>
  );
}
