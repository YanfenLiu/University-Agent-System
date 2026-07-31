import { Card, Form, Input, Button, Tabs, Typography, message } from 'antd';
import { UserOutlined, LockOutlined, RobotOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { login, register } from '../services/authService';
import { designTokens } from '../styles/tokens';

interface LoginPageProps {
  onSuccess: () => void;
}

export function LoginPage({ onSuccess }: LoginPageProps) {
  const { setAuth } = useAuth();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('login');

  const handleLogin = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const data = await login({ username: values.username, password: values.password });
      setAuth(data.access_token, data.user);
      message.success('登录成功');
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '登录失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (values: {
    username: string;
    password: string;
    display_name?: string;
  }) => {
    setLoading(true);
    try {
      const data = await register({
        username: values.username,
        password: values.password,
        display_name: values.display_name,
      });
      setAuth(data.access_token, data.user);
      message.success('注册成功');
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '注册失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fade-in"
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        overflow: 'hidden',
        background: 'linear-gradient(135deg, #0c1833 0%, #132952 40%, #1a3a6b 100%)',
      }}
    >
      {/* 网格纹理 — 与 Home Hero 一致 */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          opacity: 0.04,
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.3) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />
      {/* 径向辉光 — 与 Home Hero 一致 */}
      <div
        style={{
          position: 'absolute',
          top: -80,
          right: '40%',
          width: 400,
          height: 400,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(22,119,255,0.18) 0%, transparent 70%)',
          animation: 'glowPulse 4s ease-in-out infinite',
        }}
      />
      <div
        style={{
          position: 'absolute',
          bottom: -40,
          left: -40,
          width: 200,
          height: 200,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(82,196,26,0.10) 0%, transparent 70%)',
        }}
      />

      <Card
        style={{
          width: 420,
          borderRadius: designTokens.borderRadius,
          boxShadow: '0 16px 48px rgba(0,0,0,0.2)',
          position: 'relative',
          zIndex: 1,
          border: '1px solid rgba(22,119,255,0.08)',
        }}
        bodyStyle={{ padding: '32px' }}
      >
        {/* Logo 区 */}
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 14,
              margin: '0 auto 12px',
              background: `linear-gradient(135deg, ${designTokens.colorPrimary}, #4096ff)`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 8px 24px rgba(22,119,255,0.35)',
            }}
          >
            <RobotOutlined style={{ color: '#fff', fontSize: 28 }} />
          </div>
          <Typography.Title level={3} style={{ margin: 0, fontSize: 22 }}>
            赛智通
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 13 }}>
            大学生竞赛智能规划平台
          </Typography.Text>
        </div>

        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          centered
          items={[
            {
              key: 'login',
              label: '登录',
              children: (
                <Form onFinish={handleLogin} size="large" style={{ marginTop: 8 }}>
                  <Form.Item
                    name="username"
                    rules={[{ required: true, message: '请输入用户名' }]}
                  >
                    <Input
                      prefix={<UserOutlined style={{ color: '#999' }} />}
                      placeholder="用户名"
                      style={{ borderRadius: 10, height: 44 }}
                    />
                  </Form.Item>
                  <Form.Item
                    name="password"
                    rules={[{ required: true, message: '请输入密码' }]}
                  >
                    <Input.Password
                      prefix={<LockOutlined style={{ color: '#999' }} />}
                      placeholder="密码"
                      style={{ borderRadius: 10, height: 44 }}
                    />
                  </Form.Item>
                  <Form.Item style={{ marginBottom: 8 }}>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={loading}
                      block
                      style={{
                        height: 44,
                        borderRadius: 12,
                        fontSize: 15,
                        fontWeight: 500,
                        boxShadow: '0 8px 24px rgba(22,119,255,0.35)',
                      }}
                    >
                      登录
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: 'register',
              label: '注册',
              children: (
                <Form onFinish={handleRegister} size="large" style={{ marginTop: 8 }}>
                  <Form.Item
                    name="username"
                    rules={[
                      { required: true, message: '请输入用户名' },
                      { min: 2, max: 32, message: '用户名 2-32 个字符' },
                    ]}
                  >
                    <Input
                      prefix={<UserOutlined style={{ color: '#999' }} />}
                      placeholder="用户名"
                      style={{ borderRadius: 10, height: 44 }}
                    />
                  </Form.Item>
                  <Form.Item name="display_name">
                    <Input
                      placeholder="显示名称（选填）"
                      style={{ borderRadius: 10, height: 44 }}
                    />
                  </Form.Item>
                  <Form.Item
                    name="password"
                    rules={[
                      { required: true, message: '请输入密码' },
                      { min: 8, message: '密码至少 8 位' },
                      {
                        pattern: /^(?=.*[a-zA-Z])(?=.*\d)/,
                        message: '密码需包含字母和数字',
                      },
                    ]}
                  >
                    <Input.Password
                      prefix={<LockOutlined style={{ color: '#999' }} />}
                      placeholder="密码（8位以上，含字母和数字）"
                      style={{ borderRadius: 10, height: 44 }}
                    />
                  </Form.Item>
                  <Form.Item
                    name="confirmPassword"
                    dependencies={['password']}
                    rules={[
                      { required: true, message: '请确认密码' },
                      ({ getFieldValue }) => ({
                        validator(_, value) {
                          if (!value || getFieldValue('password') === value) {
                            return Promise.resolve();
                          }
                          return Promise.reject(new Error('两次输入的密码不一致'));
                        },
                      }),
                    ]}
                  >
                    <Input.Password
                      prefix={<LockOutlined style={{ color: '#999' }} />}
                      placeholder="确认密码"
                      style={{ borderRadius: 10, height: 44 }}
                    />
                  </Form.Item>
                  <Form.Item style={{ marginBottom: 8 }}>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={loading}
                      block
                      style={{
                        height: 44,
                        borderRadius: 12,
                        fontSize: 15,
                        fontWeight: 500,
                        boxShadow: '0 8px 24px rgba(22,119,255,0.35)',
                      }}
                    >
                      注册
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
