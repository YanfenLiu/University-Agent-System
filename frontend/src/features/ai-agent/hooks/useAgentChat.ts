import { useState, useEffect, useRef } from "react";
import { sendMessage } from "../services";
import type { Competition, DimensionalScores } from "../../../services/competitions";
import type { Message, AgentStep, UserProfile, AgentResponse } from "../types";

const CHAT_STORAGE_KEY = "saizhitong-main-agent-chat-v1";
const WELCOME_MESSAGE =
  "你好！我是 **赛智通 AI 竞赛智能体** 🤖\n\n" +
  "我可以帮你分析专业背景、推荐适合的竞赛、规划参赛路线。\n\n" +
  "请先告诉我你的专业和年级。";

type StoredChat = {
  messages: Message[];
  stateSnapshot: Record<string, unknown>;
};

function loadStoredChat(): StoredChat {
  try {
    const raw = window.localStorage.getItem(CHAT_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StoredChat>;
      if (Array.isArray(parsed.messages) && parsed.stateSnapshot) {
        return {
          messages: parsed.messages,
          stateSnapshot: parsed.stateSnapshot,
        };
      }
    }
  } catch {
    // Corrupt browser state should never prevent the chat page from loading.
  }
  return {
    messages: [{ role: "assistant", content: WELCOME_MESSAGE }],
    stateSnapshot: {},
  };
}

function mapRecommendations(rawRows: unknown): Competition[] {
  const rows = Array.isArray(rawRows) ? rawRows : [];
  return rows
    .filter((row): row is Record<string, any> => Boolean(row && typeof row === "object"))
    .map((rec, idx) => {
      let tags: string[] = ["竞赛"];
      if (Array.isArray(rec.requirements?.tags)) tags = rec.requirements.tags;
      else if (Array.isArray(rec.tags)) tags = rec.tags;
      else if (rec.requirements?.category) tags = [rec.requirements.category];
      else if (rec.type) tags = [rec.type];

      const detail: DimensionalScores | undefined = rec.detail
        ? { ...rec.detail }
        : undefined;
      return {
        id: rec.id || -(idx + 1),
        name: rec.title || rec.name || "未命名竞赛",
        summary: rec.summary || rec.description || "",
        difficulty:
          rec.level === "国际级" || rec.level === "国家级"
            ? "挑战"
            : rec.level === "省级"
              ? "进阶"
              : "入门",
        deadline: rec.deadline || rec.regist_end || "待核实",
        officialUrl: rec.source_url || rec.url || "",
        reason: rec.reason || rec.summary || "",
        tags,
        status:
          rec.match_score != null && rec.match_score >= 80
            ? "推荐"
            : rec.deadline
              ? "报名中"
              : "热门",
        match_score:
          rec.match_score != null ? Number(rec.match_score) : undefined,
        recommend_level: rec.recommend_level || undefined,
        detail,
        matched_signals: Array.isArray(rec.matched_signals)
          ? rec.matched_signals
          : undefined,
        unmatched_signals: Array.isArray(rec.unmatched_signals)
          ? rec.unmatched_signals
          : undefined,
        risk: rec.risk || undefined,
        suggested_action: rec.suggested_action || undefined,
        organizer: rec.organizer || undefined,
      };
    });
}

export function useAgentChat() {
  const initialChat = useRef<StoredChat | null>(null);
  if (initialChat.current === null) initialChat.current = loadStoredChat();
  const inputRef = useRef<any>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);

  const [messages, setMessages] = useState<Message[]>(
    initialChat.current.messages,
  );
  const [stateSnapshot, setStateSnapshot] = useState<Record<string, unknown>>(
    initialChat.current.stateSnapshot,
  );

  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([
    { label: "等待用户输入", status: "wait", detail: "请描述你的背景和需求" },
    { label: "分析用户画像", status: "wait", detail: "" },
    { label: "匹配竞赛数据库", status: "wait", detail: "" },
    { label: "评估匹配程度", status: "wait", detail: "" },
    { label: "生成推荐方案", status: "wait", detail: "" },
  ]);

  const userProfile: UserProfile = {
    major: String(stateSnapshot.major || ""),
    interests: Array.isArray(stateSnapshot.interests)
      ? stateSnapshot.interests.map(String)
      : [],
    goal: Array.isArray(stateSnapshot.development_goals)
      ? stateSnapshot.development_goals.map(String).join("、")
      : "",
    matched: Boolean(stateSnapshot.major),
  };

  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [shouldScroll, setShouldScroll] = useState(false);

  // 仅在用户发送消息后滚动到底部
  useEffect(() => {
    if (shouldScroll && messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop =
        messagesContainerRef.current.scrollHeight;
      setShouldScroll(false);
    }
  }, [messages, shouldScroll]);

  useEffect(() => {
    window.localStorage.setItem(
      CHAT_STORAGE_KEY,
      JSON.stringify({ messages, stateSnapshot }),
    );
  }, [messages, stateSnapshot]);

  const updateAgentStep = (
    index: number,
    status: "wait" | "running" | "done",
    detail?: string,
  ) => {
    setAgentSteps((prev) =>
      prev.map((step, i) =>
        i === index ? { ...step, status, detail: detail || step.detail } : step,
      ),
    );
  };

  const processMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    setShowSuggestions(false);

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);
    setShouldScroll(true);

    updateAgentStep(0, "done", "用户已发送需求");
    updateAgentStep(1, "running", "MainAgent 正在理解当前对话...");

    try {
      const result: AgentResponse = await sendMessage(text, stateSnapshot);
      const shouldReset = Boolean(result.metadata?.reset);
      if (shouldReset) {
        window.localStorage.removeItem(CHAT_STORAGE_KEY);
        setStateSnapshot({});
        setMessages([{ role: "assistant", content: WELCOME_MESSAGE }]);
        setShowSuggestions(true);
      } else {
        setStateSnapshot(result.state_snapshot);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: result.response.text,
            files: result.response.files,
          },
        ]);
      }

      updateAgentStep(1, "done", "MainAgent 已完成语义理解");
      updateAgentStep(
        2,
        "done",
        result.response.type === "result" ? "已调用推荐流程" : "本轮无需检索",
      );
      updateAgentStep(3, "done", "对话状态已更新");
      updateAgentStep(4, "done", "回复已生成");
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "当前AI服务暂时无法连接，我已保留你的对话内容，请稍后重试。",
        },
      ]);
      updateAgentStep(1, "done", "连接失败");
      updateAgentStep(2, "done", "未执行检索");
      updateAgentStep(3, "done", "原状态已保留");
      updateAgentStep(4, "done", "已明确提示错误");
    }

    setLoading(false);
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const handleSend = async () => {
    await processMessage(input);
  };

  const handleSuggestionClick = (text: string) => {
    void processMessage(text);
  };

  const recommendedCompetitions = mapRecommendations(
    stateSnapshot.last_recommendations,
  );

  return {
    input,
    setInput,
    loading,
    showSuggestions,
    messages,
    agentSteps,
    userProfile,
    inputRef,
    messagesContainerRef,
    handleSend,
    handleSuggestionClick,
    recommendedCompetitions,
  };
}
