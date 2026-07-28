import { Card, Space, Tag, Typography } from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";

interface AgentStep {
  label: string;
  status: "wait" | "running" | "done";
  detail: string;
}

interface AgentStatusCardProps {
  steps: AgentStep[];
  colorPrimary: string;
  borderRadius: number | string;
}

const STATUS_MAP = {
  done: { bg: "#52c41a", tagColor: "success", label: "完成", icon: "✓" },
  running: { bg: null as string | null, tagColor: "processing", label: "进行中", icon: "◉" },
  wait: { bg: "rgba(15,23,42,0.12)", tagColor: "default", label: "待执行", icon: "○" },
} as const;

export function AgentStatusCard({ steps, colorPrimary, borderRadius }: AgentStatusCardProps) {
  return (
    <Card
      title={
        <Space align="center" size={8}>
          <ThunderboltOutlined style={{ color: colorPrimary }} />
          <span>Agent 运行状态</span>
        </Space>
      }
      styles={{ body: { padding: "12px 16px" } }}
      style={{
        borderRadius,
        boxShadow: "0 12px 40px rgba(15, 23, 42, 0.08)",
        border: "1px solid rgba(22, 119, 255, 0.08)",
        flex: 1,
      }}
    >
      <Space direction="vertical" size={0} style={{ width: "100%" }}>
        {steps.map((step, index) => {
          const cfg = STATUS_MAP[step.status];

          return (
            <div
              key={index}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: "10px 0",
                borderBottom:
                  index < steps.length - 1
                    ? "1px solid rgba(15, 23, 42, 0.06)"
                    : undefined,
                opacity: step.status === "wait" ? 0.5 : 1,
                transition: "all 0.3s ease",
              }}
            >
              <div
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: "50%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 12,
                  flexShrink: 0,
                  background: cfg.bg ?? colorPrimary,
                  color: "#fff",
                  transition: "all 0.3s ease",
                }}
              >
                {cfg.icon}
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                <Typography.Text
                  strong
                  style={{
                    fontSize: 13,
                    color:
                      step.status === "done"
                        ? "#52c41a"
                        : step.status === "running"
                          ? colorPrimary
                          : "rgba(15,23,42,0.65)",
                    transition: "color 0.3s ease",
                  }}
                >
                  {step.label}
                </Typography.Text>
                {step.detail && (
                  <div>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {step.detail}
                    </Typography.Text>
                  </div>
                )}
              </div>

              <Tag
                color={cfg.tagColor}
                style={{
                  fontSize: 11,
                  lineHeight: "18px",
                  padding: "0 6px",
                  margin: 0,
                  flexShrink: 0,
                }}
              >
                {cfg.label}
              </Tag>
            </div>
          );
        })}
      </Space>
    </Card>
  );
}
