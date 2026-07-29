import { Tag } from 'antd';
import { designTokens } from '../styles/tokens';

interface CompetitionTagProps {
  children: string;
  type?: 'primary' | 'success' | 'warning' | 'default';
}

const colorMap = {
  primary: designTokens.colorPrimary,
  success: designTokens.colorSuccess,
  warning: designTokens.colorWarning,
  default: designTokens.colorTextSecondary,
};

export function CompetitionTag({ children, type = 'default' }: CompetitionTagProps) {
  return <Tag color={colorMap[type]}>{children}</Tag>;
}
