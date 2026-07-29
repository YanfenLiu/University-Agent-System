import { Button, Tooltip } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useState, useCallback, useRef } from 'react';
import { designTokens } from '../styles/tokens';

interface RefreshButtonProps {
  onRefresh?: () => Promise<void> | void;
  loading?: boolean;
  disabled?: boolean;
  style?: React.CSSProperties;
}

export function RefreshButton({
  onRefresh,
  loading: externalLoading,
  disabled = false,
  style,
}: RefreshButtonProps) {
  const [internalLoading, setInternalLoading] = useState(false);
  const isLoading = externalLoading ?? internalLoading;
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleClick = useCallback(async () => {
    if (isLoading || !onRefresh) return;

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }

    setInternalLoading(true);
    try {
      await onRefresh();
    } catch {
      // 错误由父页面处理
    } finally {
      debounceRef.current = setTimeout(() => {
        setInternalLoading(false);
        debounceRef.current = null;
      }, 300);
    }
  }, [isLoading, onRefresh]);

  return (
    <Tooltip title="刷新竞赛数据">
      <Button
        type="default"
        size="small"
        icon={<ReloadOutlined spin={isLoading} />}
        loading={isLoading}
        disabled={disabled || isLoading}
        onClick={handleClick}
        style={{
          borderRadius: designTokens.borderRadiusSmall,
          fontSize: 13,
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          border: '1px solid rgba(22, 119, 255, 0.2)',
          color: designTokens.colorPrimary,
          transition: 'all 0.2s ease',
          ...style,
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.borderColor = designTokens.colorPrimary;
          e.currentTarget.style.background = 'rgba(22, 119, 255, 0.06)';
          e.currentTarget.style.boxShadow =
            '0 2px 6px rgba(22, 119, 255, 0.15)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.borderColor = 'rgba(22, 119, 255, 0.2)';
          e.currentTarget.style.background = '';
          e.currentTarget.style.boxShadow = 'none';
        }}
        onMouseDown={(e) => {
          e.currentTarget.style.transform = 'scale(0.95)';
        }}
        onMouseUp={(e) => {
          e.currentTarget.style.transform = 'scale(1)';
        }}
      >
        刷新数据
      </Button>
    </Tooltip>
  );
}
