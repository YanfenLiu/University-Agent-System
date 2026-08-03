import { Button, Card, Progress, Typography } from 'antd';
import { useState } from 'react';

import { Competition } from '../services/competitions';

import { designTokens } from '../styles/tokens';
import { CompetitionTag } from './CompetitionTag';





interface CompetitionCardProps {
  competition: Competition;
  joined?: boolean;
  onAdd?: () => void;
  showActions?: boolean;
}


const statusType = {
  报名中: 'success',
  热门: 'warning',
  推荐: 'primary',
} as const;

/** 可向用户解释的细分匹配维度；总体分和推荐等级仍不展示。 */
const dimLabelMap: Record<string, string> = {
  major_score: '专业匹配',
  interest_score: '兴趣契合',
  ability_score: '能力要求',
  experience_score: '经验匹配',
  grade_score: '年级适应',
  goal_score: '目标一致',
  team_score: '组队形式',
};

const dimColorMap: Record<string, string> = {
  major_score: '#1677ff',
  interest_score: '#722ed1',
  ability_score: '#13c2c2',
  experience_score: '#eb2f96',
  grade_score: '#fa8c16',
  goal_score: '#52c41a',
  team_score: '#2f54eb',
};

export function CompetitionCard({
  competition,
  joined = false,
  onAdd,
  showActions = true,
}: CompetitionCardProps) {

  const [expanded, setExpanded] = useState(false);
  const hasBackendData = Boolean(
    competition.reason ||
    competition.risk ||
    competition.suggested_action ||
    competition.detail ||
    competition.matched_signals?.length,
  );

  const handleAdd = () => {
    onAdd?.();
  };





        const bodyStyle: React.CSSProperties = {
    padding: '20px 24px',
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
  };

  return (
    <Card
      styles={{ body: bodyStyle }}
      style={{
        borderRadius: designTokens.borderRadius,
        boxShadow: designTokens.boxShadow,
        height: '100%',
      }}
    >
            {/* Tags row - fixed height 32px */}
      <div style={{ height: 32, display: 'flex', gap: 6, alignItems: 'center' }}>
        <CompetitionTag type={statusType[competition.status]}>
          {competition.status}
        </CompetitionTag>
        <CompetitionTag>
          {competition.difficulty}
        </CompetitionTag>
      </div>

      {/* Title - fixed height 48px for 2 rows */}
      <div style={{ height: 48, display: 'flex', alignItems: 'flex-start', marginBottom: 4 }}>
        <Typography.Title
          level={4}
          style={{ margin: 0, fontSize: 16, lineHeight: 1.4 }}
          ellipsis={{ rows: 2 }}
        >
          {competition.name}
        </Typography.Title>
      </div>

      {/* Summary - expands on click */}
      <div style={{ minHeight: 48, marginBottom: 4 }}>
        <Typography.Paragraph
          type="secondary"
          style={{ fontSize: 13, margin: 0, lineHeight: 1.6 }}
          ellipsis={expanded ? { rows: 6 } : { rows: 2 }}
        >
          {competition.summary}
        </Typography.Paragraph>
      </div>

      {/* Tags */}
      <div style={{ minHeight: 28, display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
        {competition.tags.map(tag => (
          <CompetitionTag key={tag} type="primary">
            {tag}
          </CompetitionTag>
        ))}
      </div>

            {/* Bottom area */}
      <div style={{ marginTop: 'auto' }}>
        {/* 截止时间 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', marginBottom: 8 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            截止时间：{competition.deadline}
          </Typography.Text>
        </div>

        {/* 推荐理由 — 更醒目 */}
        {competition.reason && (
          <div style={{
            background: '#f6f8ff',
            borderRadius: 8,
            padding: '8px 10px',
            marginBottom: 8,
            border: '1px solid #e8edff',
          }}>
            <Typography.Text style={{ fontSize: 12, fontWeight: 600, color: '#1677ff', display: 'block', marginBottom: 2 }}>
              为什么值得了解
            </Typography.Text>
            <Typography.Paragraph
              style={{ fontSize: 12, margin: 0, lineHeight: 1.6, color: '#333' }}
              ellipsis={expanded ? { rows: 6 } : { rows: 2 }}
            >
              {competition.reason}
            </Typography.Paragraph>
          </div>
        )}

        {/* 细分维度有参考意义；仅在展开时展示，不显示总体分或推荐等级。 */}
        {expanded && hasBackendData && competition.detail && (
          <div style={{
            background: '#fafafa',
            borderRadius: 8,
            padding: '10px 12px',
            marginBottom: 8,
          }}>
            <Typography.Text style={{ fontSize: 12, fontWeight: 600, color: '#333', display: 'block', marginBottom: 6 }}>
              专业匹配分析
            </Typography.Text>
            {Object.entries(dimLabelMap).map(([key, label]) => {
              const value = competition.detail?.[key];
              if (value == null || !Number.isFinite(Number(value))) return null;

              const score = Math.max(0, Math.min(100, Math.round(Number(value))));
              const color = dimColorMap[key] || '#1677ff';
              return (
                <div key={key} style={{ display: 'flex', alignItems: 'center', marginBottom: 4, gap: 8 }}>
                  <span style={{
                    width: 56,
                    fontSize: 11,
                    color: '#666',
                    flexShrink: 0,
                    textAlign: 'right',
                  }}>
                    {label}
                  </span>
                  <Progress
                    percent={score}
                    size={{ height: 8 }}
                    strokeColor={color}
                    trailColor="#e8e8e8"
                    showInfo={false}
                    style={{ flex: 1, margin: 0 }}
                  />
                  <span style={{
                    width: 30,
                    fontSize: 11,
                    fontWeight: 600,
                    color: score >= 80 ? '#52c41a' : score >= 60 ? '#faad14' : '#ff4d4f',
                    textAlign: 'right',
                  }}>
                    {score}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* 匹配信号标签（仅后端数据有） */}
        {hasBackendData && competition.matched_signals && competition.matched_signals.length > 0 && (
          <div style={{ marginBottom: 6 }}>
            <Typography.Text style={{ fontSize: 11, fontWeight: 600, color: '#52c41a', display: 'block', marginBottom: 3 }}>
              与你相关的方面
            </Typography.Text>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {competition.matched_signals.map((sig, i) => {
                const display = sig.includes(':') ? sig.split(':').slice(1).join(':').trim() : sig;
                return (
                  <span key={i} style={{
                    fontSize: 11,
                    background: '#f6ffed',
                    color: '#52c41a',
                    border: '1px solid #b7eb8f',
                    borderRadius: 6,
                    padding: '0 6px',
                    lineHeight: '20px',
                    maxWidth: '100%',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap' as const,
                  }}>
                    {display}
                  </span>
                );
              })}
            </div>
          </div>
        )}

        {/* 风险提示（仅后端数据有） */}
        {hasBackendData && competition.risk && (
          <div style={{
            background: '#fffbe6',
            borderRadius: 6,
            padding: '6px 10px',
            marginBottom: 6,
            border: '1px solid #ffe58f',
          }}>
            <Typography.Text style={{ fontSize: 11, fontWeight: 600, color: '#faad14', display: 'block', marginBottom: 1 }}>
              需要留意
            </Typography.Text>
            <Typography.Text style={{ fontSize: 11, color: '#ad8b00', lineHeight: 1.5, display: 'block' }}>
              {competition.risk}
            </Typography.Text>
          </div>
        )}

        {/* 建议行动（仅后端数据有） */}
        {expanded && hasBackendData && competition.suggested_action && (
          <div style={{ marginBottom: 8 }}>
            <Typography.Text style={{ fontSize: 11, color: '#666' }}>
              下一步建议：{competition.suggested_action}
            </Typography.Text>
          </div>
        )}

        {/* 展开/收起 */}
        {hasBackendData && (
          <span
            onClick={() => setExpanded(!expanded)}
            style={{
              cursor: 'pointer',
              color: designTokens.colorPrimary,
              fontSize: 12,
              userSelect: 'none',
              display: 'inline-block',
              marginBottom: 8,
            }}
          >
            {expanded ? '收起详情' : '展开详情'}
          </span>
        )}

                {showActions && (
          <div style={{ display: 'flex', gap: 8 }}>
            <Button
              type="primary"
              size="small"
                            disabled={joined}
              onClick={handleAdd}
              style={{ borderRadius: 8, fontSize: 13 }}
            >
              {joined ? '✓ 已加入' : '加入我的竞赛'}
            </Button>

            <Button
              size="small"
              href={competition.officialUrl}
              target="_blank"
              style={{ borderRadius: 8, fontSize: 13 }}
            >
              查看详情
            </Button>
          </div>
        )}
      </div>
    </Card>
  );

}
