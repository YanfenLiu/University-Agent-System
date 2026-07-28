import { Button, Typography } from "antd";
import { SUGGESTIONS } from "../utils/extractKeywords";

interface ChatSuggestionsProps {
  visible: boolean;
  messageCount: number;
  colorPrimary: string;
  onSelect: (text: string) => void;
}

export function ChatSuggestions({ visible, messageCount, colorPrimary, onSelect }: ChatSuggestionsProps) {
  if (!visible || messageCount > 1) return null;

  return (
    <div style={{ marginBottom: 20, textAlign: "center" }}>
      <Typography.Text type="secondary" style={{ fontSize: 13, display: "block", marginBottom: 12 }}>
        试试这些提问
      </Typography.Text>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
        {SUGGESTIONS.map((s, i) => (
          <Button
            key={i}
            size="small"
            type="default"
            style={{
              borderRadius: 20,
              borderColor: "rgba(22, 119, 255, 0.3)",
              color: colorPrimary,
              fontSize: 13,
              padding: "4px 16px",
            }}
            onClick={() => onSelect(s)}
          >
            {s}
          </Button>
        ))}
      </div>
    </div>
  );
}
