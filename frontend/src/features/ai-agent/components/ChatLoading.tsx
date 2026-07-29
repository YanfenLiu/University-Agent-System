import { Typography } from "antd";
import { RobotOutlined } from "@ant-design/icons";

interface ChatLoadingProps {
  colorPrimary: string;
}

export function ChatLoading({ colorPrimary }: ChatLoadingProps) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "flex-start",
        marginBottom: 16,
        gap: 10,
      }}
    >
      <div
        style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          background: `linear-gradient(135deg, ${colorPrimary}, #4096ff)`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          marginTop: 4,
        }}
      >
        <RobotOutlined style={{ color: "#fff", fontSize: 14 }} />
      </div>

      <div
        style={{
          position: "relative",
          padding: "14px 20px",
          borderRadius: "18px 18px 18px 4px",
          background: "#ffffff",
          border: "2px solid rgba(22, 119, 255, 0.5)",
          boxShadow:
            "0 4px 12px rgba(15, 23, 42, 0.06), 0 0 10px rgba(22, 119, 255, 0.35), 0 0 20px rgba(22, 119, 255, 0.15)",
          overflow: "hidden",
        }}
      >
        {/* 旋转光晕边框 */}
        <div
          style={{
            position: "absolute",
            inset: -2,
            borderRadius: "20px 20px 20px 6px",
            background: `conic-gradient(
              from 0deg,
              transparent 0deg,
              rgba(22,119,255,0.40) 40deg,
              rgba(64,150,255,0.50) 80deg,
              rgba(22,119,255,0.40) 120deg,
              transparent 180deg,
              transparent 360deg
            )`,
            WebkitMask: "linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)",
            WebkitMaskComposite: "xor",
            mask: "linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)",
            maskComposite: "exclude",
            padding: "2px",
            animation: "glowRotate 1.5s linear infinite",
            zIndex: 0,
            pointerEvents: "none",
          }}
        />

        {/* 脉冲点 */}
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          {[0, 0.3, 0.6].map((delay) => (
            <span
              key={delay}
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: colorPrimary,
                animation: "loadingPulse 1.2s ease-in-out infinite",
                animationDelay: `${delay}s`,
              }}
            />
          ))}
        </div>

        <Typography.Text
          type="secondary"
          style={{ fontSize: 13, marginTop: 6, display: "block" }}
        >
          AI 正在分析你的需求...
        </Typography.Text>
      </div>
    </div>
  );
}
