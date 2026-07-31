import { Button, List, Typography, Popconfirm, Spin, Space } from 'antd';
import { PlusOutlined, DeleteOutlined, MessageOutlined } from '@ant-design/icons';
import { useState, useEffect, useCallback } from 'react';
import { request } from '../../../services/apiClient';
import { useAuth } from '../../../contexts/AuthContext';
import { designTokens } from '../../../styles/tokens';
import { formatDate } from '../../../utils/time';
import type { ConversationSummary } from '../../../services/authTypes';

interface ConversationHistoryProps {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  refreshTrigger: number;
}

export function ConversationHistory({ activeId, onSelect, onNew, refreshTrigger }: ConversationHistoryProps) {
  const { user } = useAuth();
  const [convs, setConvs] = useState<ConversationSummary[]>([]);
  const [loading, setLoading] = useState(false);

  const loadList = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const res = await request<{ items: ConversationSummary[] }>('/api/conversations');
      setConvs(res.items || []);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (user) loadList();
    else setConvs([]);
  }, [user, loadList, refreshTrigger]);

  const handleDelete = async (id: string) => {
    try {
      await request(`/api/conversations/${id}`, { method: 'DELETE' });
      if (activeId === id) onNew();
      loadList();
    } catch {
      // silent
    }
  };

  if (!user) return null;

  return (
    <div
      style={{
        background: '#fff',
        borderRadius: designTokens.borderRadius,
        border: '1px solid rgba(22,119,255,0.08)',
        boxShadow: '0 12px 40px rgba(15, 23, 42, 0.08)',
        overflow: 'hidden',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid rgba(15,23,42,0.06)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <Typography.Text strong style={{ fontSize: 14 }}>对话历史</Typography.Text>
        <Button
          type="primary"
          size="small"
          icon={<PlusOutlined />}
          onClick={onNew}
          style={{ borderRadius: 8 }}
        >
          新建
        </Button>
      </div>

      {/* List */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading ? (
          <Spin size="small" style={{ display: 'block', padding: 24, textAlign: 'center' }} />
        ) : convs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 32, color: '#999', fontSize: 13 }}>
            暂无对话记录
          </div>
        ) : (
          <List
            dataSource={convs}
            renderItem={(item) => (
              <div
                onClick={() => onSelect(item.id)}
                style={{
                  padding: '10px 16px',
                  cursor: 'pointer',
                  borderLeft: activeId === item.id ? `3px solid ${designTokens.colorPrimary}` : '3px solid transparent',
                  background: activeId === item.id ? 'rgba(22,119,255,0.04)' : 'transparent',
                  borderBottom: '1px solid rgba(15,23,42,0.04)',
                  transition: 'background 0.2s',
                }}
                onMouseEnter={(e) => {
                  if (activeId !== item.id) (e.currentTarget as HTMLDivElement).style.background = 'rgba(15,23,42,0.02)';
                }}
                onMouseLeave={(e) => {
                  if (activeId !== item.id) (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Space size={6}>
                    <MessageOutlined style={{ fontSize: 12, color: '#999' }} />
                    <Typography.Text
                      ellipsis
                      style={{ fontSize: 13, maxWidth: 130, fontWeight: activeId === item.id ? 600 : 400 }}
                    >
                      {item.title}
                    </Typography.Text>
                  </Space>
                  <Popconfirm
                    title="确定删除此对话？"
                    onConfirm={(e) => { e?.stopPropagation(); handleDelete(item.id); }}
                    onCancel={(e) => e?.stopPropagation()}
                    okText="删除"
                    cancelText="取消"
                  >
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={(e) => e.stopPropagation()}
                      style={{ opacity: 0.5 }}
                    />
                  </Popconfirm>
                </div>
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                  {formatDate(item.updated_at)}
                </Typography.Text>
              </div>
            )}
          />
        )}
      </div>
    </div>
  );
}
