import { Typography } from "antd";
import { RobotOutlined, UserOutlined } from "@ant-design/icons";
import ReactMarkdown from "react-markdown";
import type { Message } from "../types";

interface ChatMessageProps {
  message: Message;
  colorPrimary: string;
}

export function ChatMessage({ message, colorPrimary }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: 16,
        gap: 10,
      }}
    >
      {!isUser && (
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
      )}

      <div
        style={{
          position: "relative",
          maxWidth: "78%",
          padding: "14px 18px",
          borderRadius: isUser ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isUser
            ? "linear-gradient(135deg, #1677ff 0%, #4096ff 100%)"
            : "#ffffff",
          color: isUser ? "#fff" : "inherit",
          border: isUser ? "none" : "1px solid rgba(22, 119, 255, 0.12)",
          boxShadow: isUser
            ? "0 4px 12px rgba(22, 119, 255, 0.2)"
            : "0 4px 12px rgba(15, 23, 42, 0.06)",
          whiteSpace: "pre-wrap",
          lineHeight: 1.7,
          overflow: "hidden",
        }}
      >
        {isUser ? (
          <Typography.Text
            style={{
              color: "#fff",
              fontSize: 14,
              position: "relative",
              zIndex: 1,
            }}
          >
            {message.content}
          </Typography.Text>
        ) : (
          <div
            style={{
              color: "rgba(15,23,42,0.85)",
              fontSize: 14,
              position: "relative",
              zIndex: 1,
            }}
          >
            <ReactMarkdown
              components={{
                p: ({ children }) => (
                  <p style={{ margin: "0 0 8px" }}>{children}</p>
                ),
                ul: ({ children }) => (
                  <ul style={{ margin: "4px 0 8px", paddingLeft: 22 }}>
                    {children}
                  </ul>
                ),
                ol: ({ children }) => (
                  <ol style={{ margin: "4px 0 8px", paddingLeft: 22 }}>
                    {children}
                  </ol>
                ),
                a: ({ children, href }) => (
                  <a href={href} target="_blank" rel="noreferrer">
                    {children}
                  </a>
                ),
                code: ({ children }) => (
                  <code
                    style={{
                      padding: "1px 5px",
                      borderRadius: 4,
                      background: "rgba(15,23,42,0.06)",
                    }}
                  >
                    {children}
                  </code>
                ),
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
        {!isUser && message.files && message.files.length > 0 && (
          <div style={{ marginTop: 10 }}>
            {message.files.map((url, index) => (
              <a
                key={url}
                href={url}
                download
                style={{ display: "block", marginTop: 4 }}
              >
                下载生成文件{message.files!.length > 1 ? ` ${index + 1}` : ""}
              </a>
            ))}
          </div>
        )}
      </div>

      {isUser && (
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: "#e8f0fe",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            marginTop: 4,
          }}
        >
          <UserOutlined style={{ color: colorPrimary, fontSize: 14 }} />
        </div>
      )}
    </div>
  );
}
