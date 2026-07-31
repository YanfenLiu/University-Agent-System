import { Layout, Typography, Dropdown, Button, Avatar, Space } from 'antd';
import { UserOutlined, LogoutOutlined, SettingOutlined } from '@ant-design/icons';
import { ReactNode } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { logout } from '../services/authService';
import { designTokens } from '../styles/tokens';

interface AppLayoutProps {
  children: ReactNode;
  onLoginClick?: () => void;
}

export function AppLayout({ children, onLoginClick }: AppLayoutProps) {
  const { user, clearAuth, isAdmin } = useAuth();

  const handleLogout = async () => {
    await logout();
    clearAuth();
  };

  const userMenu = {
    items: [
      {
        key: 'profile',
        icon: <UserOutlined />,
        label: user?.display_name || user?.username || '用户',
        disabled: true,
      },
      { type: 'divider' as const },
      ...(isAdmin
        ? [
            {
              key: 'admin',
              icon: <SettingOutlined />,
              label: '管理后台',
            },
            { type: 'divider' as const },
          ]
        : []),
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: '退出登录',
        danger: true,
      },
    ],
    onClick: ({ key }: { key: string }) => {
      if (key === 'logout') handleLogout();
      if (key === 'admin' && onLoginClick) {
        // Admin dashboard is a tab, no action needed here
      }
    },
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Header
        style={{
          background: designTokens.colorBgContainer,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: designTokens.boxShadow,
          padding: '0 32px',
        }}
      >
        <Typography.Title level={4} style={{ margin: 0, color: designTokens.colorPrimary }}>
          赛智通
        </Typography.Title>
        <Space>
          {user ? (
            <Dropdown menu={userMenu} placement="bottomRight">
              <Space style={{ cursor: 'pointer' }}>
                <Avatar
                  size="small"
                  icon={<UserOutlined />}
                  style={{ backgroundColor: designTokens.colorPrimary }}
                />
                <Typography.Text style={{ fontSize: 14 }}>
                  {user.display_name || user.username}
                </Typography.Text>
              </Space>
            </Dropdown>
          ) : (
            <Button
              type="primary"
              size="small"
              onClick={onLoginClick}
              style={{ borderRadius: 10, height: 36, padding: '0 20px' }}
            >
              登录 / 注册
            </Button>
          )}
        </Space>
      </Layout.Header>
      <Layout.Content style={{ padding: '12px 32px 32px' }}>{children}</Layout.Content>
      <Layout.Footer
        style={{
          textAlign: 'center',
          color: designTokens.colorTextSecondary,
        }}
      >
        用 AI 帮你找到更适合的竞赛
      </Layout.Footer>
    </Layout>
  );
}
