import { Col, Input, Row, Tag, Typography, Spin, Alert, Result, message } from 'antd';
import { useMemo, useState } from 'react';

import { CompetitionCard } from '../components/CompetitionCard';
import { RefreshButton } from '../components/RefreshButton';
import { useCompetitionsData, useCompetitionsLoading, useCompetitionsError } from '../contexts/CompetitionsDataContext';
import { useCompetitions } from '../contexts/CompetitionsContext';
import { useAuth } from '../contexts/AuthContext';
import { designTokens } from '../styles/tokens';
import { startCompetitionRefresh } from '../services/refresh';

import { SearchOutlined, TrophyOutlined } from '@ant-design/icons';

const { success } = message;

/** 竞赛库页面 —— 展示所有 Supabase 竞赛数据 */
export function CompetitionsLibrary() {
  const competitions = useCompetitionsData();
  const loading = useCompetitionsLoading();
  const error = useCompetitionsError();
  const [searchText, setSearchText] = useState('');
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const { addCompetition, isJoined } = useCompetitions();
  const { isAdmin } = useAuth();

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const result = await startCompetitionRefresh();
      if (result.status === 'rate_limited') {
        message.warning(result.message);
      } else {
        success(result.message);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '无法启动数据库刷新');
    } finally {
      setRefreshing(false);
    }
  };

  // ===== 加载中状态 =====
  if (loading) {
    return (
      <div className="fade-in" style={{ textAlign: 'center', padding: '120px 0' }}>
        <Spin size="large" tip="正在加载竞赛数据…" />
      </div>
    );
  }

  // ===== 错误状态 =====
  if (error) {
    return (
      <div className="fade-in">
        <Result
          status="warning"
          title="竞赛数据加载失败"
          subTitle={error}
          extra={
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              请检查 Supabase 配置或查看浏览器控制台中的详细错误信息
            </Typography.Text>
          }
        />
      </div>
    );
  }

  // 提取所有标签并计数
  const tagStats = useMemo(() => {
    const map = new Map<string, number>();
    competitions.forEach((c) => {
      c.tags.forEach((t) => {
        map.set(t, (map.get(t) || 0) + 1);
      });
    });
    return Array.from(map.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 20); // 只展示前 20 个热门标签
  }, [competitions]);

  // 筛选
  const filtered = useMemo(() => {
    let list = competitions;
    if (searchText) {
      const q = searchText.toLowerCase();
      list = list.filter(
        (c) =>
          c.name.toLowerCase().includes(q) ||
          c.summary.toLowerCase().includes(q) ||
          c.tags.some((t) => t.toLowerCase().includes(q)),
      );
    }
    if (selectedTag) {
      list = list.filter((c) => c.tags.includes(selectedTag));
    }
    return list;
  }, [competitions, searchText, selectedTag]);

  return (
    <div className="fade-in">
      {/* 页头 */}
      <div
        style={{
          marginBottom: designTokens.spacing.lg,
        }}
      >
        <Typography.Title
          level={3}
          style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}
        >
          <TrophyOutlined style={{ color: designTokens.colorPrimary }} />
          竞赛库
          {isAdmin && (
            <RefreshButton
              onRefresh={handleRefresh}
              loading={refreshing}
              style={{ marginLeft: 'auto' }}
            />
          )}
        </Typography.Title>
        <Typography.Text type="secondary" style={{ fontSize: 14 }}>
          共收录 <strong style={{ color: designTokens.colorPrimary }}>{competitions.length}</strong> 个竞赛资源
        </Typography.Text>
      </div>

      {/* 搜索栏 */}
      <Input
        prefix={<SearchOutlined style={{ color: '#999' }} />}
        placeholder="搜索竞赛名称、简介或标签…"
        allowClear
        value={searchText}
        onChange={(e) => setSearchText(e.target.value)}
        style={{
          borderRadius: 10,
          height: 44,
          marginBottom: designTokens.spacing.md,
          border:'1px solid rgba(22,119,255,0.12)',
          boxShadow:'0 2px 6px rgba(0,0,0,0.02)',
        }}
      />

      {/* 标签筛选 */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 8,
          marginBottom: designTokens.spacing.lg,
        }}
      >
        <Tag
          style={{
            borderRadius: 20,
            padding: '4px 14px',
            fontSize: 13,
            cursor: 'pointer',
            border: selectedTag === null ? '1px solid ' + designTokens.colorPrimary : '1px solid #d9d9d9',
            color: selectedTag === null ? designTokens.colorPrimary : '#666',
            background: selectedTag === null ? designTokens.colorPrimary + '12' : '#fff',
            fontWeight: selectedTag === null ? 600 : 400,
          }}
          onClick={() => setSelectedTag(null)}
        >
          全部
        </Tag>
        {tagStats.map(([tag, count]) => (
          <Tag
            key={tag}
            style={{
              borderRadius: 20,
              padding: '4px 14px',
              fontSize: 13,
              cursor: 'pointer',
              border: selectedTag === tag ? '1px solid ' + designTokens.colorPrimary : '1px solid #d9d9d9',
              color: selectedTag === tag ? designTokens.colorPrimary : '#666',
              background: selectedTag === tag ? designTokens.colorPrimary + '12' : '#fff',
              fontWeight: selectedTag === tag ? 600 : 400,
            }}
            onClick={() => setSelectedTag(tag === selectedTag ? null : tag)}
          >
            {tag} ({count})
          </Tag>
        ))}
      </div>

      {/* 竞赛卡片网格 */}
      <Row gutter={[designTokens.spacing.lg, designTokens.spacing.lg]}>
        {filtered.map((item) => (
          <Col xs={24} sm={12} lg={8} xl={6} key={item.id}>
            <CompetitionCard
              competition={item}
              showActions={true}
              joined={isJoined(item.id)}
              onAdd={() => {
                addCompetition(item);
                success('✓ 已加入「' + item.name.slice(0, 16) + '…」');
              }}
            />
          </Col>
        ))}
      </Row>

      {/* 空状态提示 */}
      {filtered.length === 0 && (
        <div
          style={{
            textAlign: 'center',
            padding: '80px 0',
            color: '#999',
          }}
        >
          <TrophyOutlined style={{ fontSize: 48, display: 'block', marginBottom: 12, opacity: 0.3 }} />
          <Typography.Text type="secondary" style={{ fontSize: 15 }}>
            {searchText || selectedTag ? '没有匹配的竞赛，试试其他关键词？' : '暂无竞赛数据'}
          </Typography.Text>
        </div>
      )}
    </div>
  );
}
