import {
  Tabs, Card, Statistic, Table, Tag, Button, Input, Typography, Drawer, message, Space, Spin, Result,
} from 'antd';
import {
  UserOutlined, BarChartOutlined, MessageOutlined,
  TeamOutlined, SearchOutlined,
} from '@ant-design/icons';
import { formatTime } from '../utils/time';
import { useState, useEffect, useCallback } from 'react';
import { request } from '../services/apiClient';
import { designTokens } from '../styles/tokens';

const CARD_STYLE = {
  borderRadius: designTokens.borderRadius,
  border: '1px solid rgba(22,119,255,0.08)',
  boxShadow: '0 4px 16px rgba(15,23,42,0.06)',
};

interface StatsData {
  total_users: number;
  active_users: number;
  total_conversations: number;
  today_conversations: number;
}

function OverviewTab() {
  const [stats, setStats] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    request<{ stats: StatsData }>('/api/admin/stats')
      .then((res) => setStats(res.stats))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 16 }}>
      {[
        { icon: <TeamOutlined />, title: '总用户数', value: stats?.total_users ?? 0, gradient: 'linear-gradient(135deg,#1677ff,#4096ff)' },
        { icon: <UserOutlined />, title: '活跃用户', value: stats?.active_users ?? 0, gradient: 'linear-gradient(135deg,#52c41a,#73d13d)' },
        { icon: <MessageOutlined />, title: '总对话数', value: stats?.total_conversations ?? 0, gradient: 'linear-gradient(135deg,#fa8c16,#ffa940)' },
        { icon: <BarChartOutlined />, title: '今日对话', value: stats?.today_conversations ?? 0, gradient: 'linear-gradient(135deg,#a78bfa,#c4b5fd)' },
      ].map((item, i) => (
        <Card key={i} style={CARD_STYLE} bodyStyle={{ padding: '20px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div
              style={{
                width: 44, height: 44, borderRadius: 12, background: item.gradient,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
              }}
            >
              <span style={{ color: '#fff', fontSize: 20 }}>{item.icon}</span>
            </div>
            <div>
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>{item.title}</Typography.Text>
              <Statistic value={item.value} valueStyle={{ fontSize: 24, fontWeight: 600 }} />
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  const loadUsers = useCallback(async (p: number, s: string, st: string) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(p), page_size: '50' });
      if (s) params.set('search', s);
      if (st) params.set('status', st);
      const res = await request<{ items: any[]; total: number }>(`/api/admin/users?${params}`);
      setUsers(res.items);
      setTotal(res.total);
    } catch {
      message.error('加载用户列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadUsers(page, search, statusFilter); }, [page, search, statusFilter, loadUsers]);

  const handleStatusToggle = async (userId: string, currentStatus: string) => {
    const newStatus = currentStatus === 'active' ? 'frozen' : 'active';
    try {
      await request(`/api/admin/users/${userId}`, { method: 'PATCH', body: { status: newStatus } });
      message.success(`用户已${newStatus === 'active' ? '解冻' : '冻结'}`);
      loadUsers(page, search, statusFilter);
    } catch {
      message.error('操作失败');
    }
  };

  return (
    <>
      <Space style={{ marginBottom: 16 }}>
        <Input.Search
          placeholder="搜索用户名或昵称"
          allowClear
          onSearch={setSearch}
          style={{ width: 260 }}
          prefix={<SearchOutlined style={{ color: '#999' }} />}
        />
        <Button onClick={() => setStatusFilter(statusFilter === 'active' ? '' : 'active')} type={statusFilter ? 'primary' : 'default'}>
          仅活跃
        </Button>
        <Button onClick={() => setStatusFilter(statusFilter === 'frozen' ? '' : 'frozen')} type={statusFilter === 'frozen' ? 'primary' : 'default'}>
          仅冻结
        </Button>
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={users}
        pagination={{ current: page, total, pageSize: 50, onChange: setPage }}
        columns={[
          { title: '用户名', dataIndex: 'username', width: 140 },
          { title: '显示名', dataIndex: 'display_name', width: 140 },
          {
            title: '角色', dataIndex: 'role', width: 80,
            render: (role: string) => (
              <Tag color={role === 'admin' ? 'gold' : 'blue'} style={{ borderRadius: 20 }}>{role}</Tag>
            ),
          },
          {
            title: '状态', dataIndex: 'status', width: 80,
            render: (status: string) => (
              <Tag color={status === 'active' ? 'green' : 'red'} style={{ borderRadius: 20 }}>{status === 'active' ? '正常' : '冻结'}</Tag>
            ),
          },
          {
            title: '注册时间', dataIndex: 'created_at', width: 180,
            render: (v: string) => formatTime(v),
          },
          {
            title: '操作', key: 'action', width: 160,
            render: (_: any, record: any) => (
              <Space>
                <Button size="small" danger={record.status === 'active'} onClick={() => handleStatusToggle(record.id, record.status)} style={{ borderRadius: 8 }}>
                  {record.status === 'active' ? '冻结' : '解冻'}
                </Button>
              </Space>
            ),
          },
        ]}
      />
    </>
  );
}

function ConversationsTab() {
  const [convs, setConvs] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedConv, setSelectedConv] = useState<any>(null);

  const loadConvs = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const res = await request<{ items: any[]; total: number }>(`/api/admin/conversations?page=${p}&page_size=50`);
      setConvs(res.items);
      setTotal(res.total);
    } catch {
      message.error('加载对话列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadConvs(page); }, [page, loadConvs]);

  const viewConv = async (id: string) => {
    try {
      const res = await request<{ conversation: any }>(`/api/admin/conversations/${id}`);
      setSelectedConv(res.conversation);
      setDrawerOpen(true);
    } catch {
      message.error('加载对话详情失败');
    }
  };

  const deleteConv = async (id: string) => {
    try {
      await request(`/api/admin/conversations/${id}`, { method: 'DELETE' });
      message.success('已删除');
      loadConvs(page);
    } catch {
      message.error('删除失败');
    }
  };

  return (
    <>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={convs}
        pagination={{ current: page, total, pageSize: 50, onChange: setPage }}
        columns={[
          { title: '标题', dataIndex: 'title', width: 200, ellipsis: true },
          { title: '用户ID', dataIndex: 'user_id', width: 280, ellipsis: true },
          {
            title: '更新时间', dataIndex: 'updated_at', width: 180,
            render: (v: string) => formatTime(v),
          },
          {
            title: '操作', key: 'action', width: 160,
            render: (_: any, record: any) => (
              <Space>
                <Button size="small" onClick={() => viewConv(record.id)} style={{ borderRadius: 8 }}>查看</Button>
                <Button size="small" danger onClick={() => deleteConv(record.id)} style={{ borderRadius: 8 }}>删除</Button>
              </Space>
            ),
          },
        ]}
      />
      <Drawer
        title="对话详情"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        width={600}
      >
        {selectedConv && (
          <div>
            <Typography.Title level={5}>{selectedConv.title}</Typography.Title>
            <div style={{ maxHeight: '70vh', overflow: 'auto' }}>
              {(selectedConv.messages || []).map((msg: any, i: number) => (
                <div
                  key={i}
                  style={{
                    marginBottom: 12,
                    padding: '10px 14px',
                    borderRadius: 10,
                    background: msg.role === 'user' ? 'rgba(22,119,255,0.06)' : 'rgba(82,196,26,0.06)',
                    border: `1px solid ${msg.role === 'user' ? 'rgba(22,119,255,0.12)' : 'rgba(82,196,26,0.12)'}`,
                  }}
                >
                  <Typography.Text type="secondary" style={{ fontSize: 11, display: 'block', marginBottom: 4 }}>
                    {msg.role === 'user' ? '用户' : 'AI'}
                  </Typography.Text>
                  <Typography.Text style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{msg.content}</Typography.Text>
                </div>
              ))}
            </div>
          </div>
        )}
      </Drawer>
    </>
  );
}

function RefreshJobsTab() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    request<{ items: any[] }>('/api/admin/refresh-jobs')
      .then((res) => setJobs(res.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />;

  return (
    <Table
      rowKey="id"
      dataSource={jobs}
      columns={[
        { title: 'ID', dataIndex: 'id', width: 60 },
        {
          title: '状态', dataIndex: 'status', width: 100,
          render: (s: string) => {
            const colors: Record<string, string> = { completed: 'green', failed: 'red', running: 'blue', queued: 'gold' };
            return <Tag color={colors[s] || 'default'} style={{ borderRadius: 20 }}>{s}</Tag>;
          },
        },
        { title: '类型', dataIndex: 'trigger_type', width: 80 },
        { title: '新增', dataIndex: 'items_found', width: 70 },
        { title: '更新', dataIndex: 'items_updated', width: 70 },
        {
          title: '开始', dataIndex: 'started_at', width: 180,
          render: (v: string) => formatTime(v),
        },
        {
          title: '结束', dataIndex: 'finished_at', width: 180,
          render: (v: string) => formatTime(v),
        },
      ]}
    />
  );
}

export function AdminDashboard() {
  return (
    <div className="fade-in">
      <div style={{ marginBottom: designTokens.spacing.lg }}>
        <Typography.Title level={3} style={{ marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
          <BarChartOutlined style={{ color: designTokens.colorPrimary }} />
          管理后台
        </Typography.Title>
        <Typography.Text type="secondary" style={{ fontSize: 14 }}>
          用户管理、对话审核与系统监控
        </Typography.Text>
      </div>

      <Tabs
        defaultActiveKey="overview"
        items={[
          { key: 'overview', label: '概览', children: <OverviewTab /> },
          { key: 'users', label: '用户管理', children: <UsersTab /> },
          { key: 'conversations', label: '对话审核', children: <ConversationsTab /> },
          { key: 'refresh', label: '刷新日志', children: <RefreshJobsTab /> },
        ]}
      />
    </div>
  );
}
