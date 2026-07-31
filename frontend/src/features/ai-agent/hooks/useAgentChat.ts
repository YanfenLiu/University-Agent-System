import { useState, useEffect, useRef, useCallback } from "react";
import { sendMessage } from "../services";
import type { Competition, DimensionalScores } from "../../../services/competitions";
import type { Message, AgentStep, UserProfile, AgentResponse } from "../types";
import { useAuth } from "../../../contexts/AuthContext";
import { request } from "../../../services/apiClient";
import type { ConversationDetail } from "../../../services/authTypes";

const WELCOME_MESSAGE =
  "你好！我是 **赛智通 AI 竞赛智能体** 🤖\n\n" +
  "我可以帮你分析专业背景、推荐适合的竞赛、规划参赛路线。\n\n" +
  "请先告诉我你的专业和年级。";

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
  const { user } = useAuth();
  const prevUserId = useRef<string | undefined>(user?.id);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  const triggerHistoryRefresh = useCallback(() => {
    setHistoryRefreshKey((k) => k + 1);
  }, []);

  const resetToWelcome = useCallback(() => {
    setConversationId(null);
    setMessages([{ role: "assistant" as const, content: WELCOME_MESSAGE }]);
    setStateSnapshot({});
    setShowSuggestions(true);
    setAgentSteps([
      { label: "等待用户输入", status: "wait" as const, detail: "请描述你的背景和需求" },
      { label: "分析用户画像", status: "wait" as const, detail: "" },
      { label: "匹配竞赛数据库", status: "wait" as const, detail: "" },
      { label: "评估匹配程度", status: "wait" as const, detail: "" },
      { label: "生成推荐方案", status: "wait" as const, detail: "" },
    ]);
  }, []);

  // 用户登出或切换账号时重置对话
  useEffect(() => {
    if (prevUserId.current !== user?.id) {
      prevUserId.current = user?.id;
      resetToWelcome();
    }
  }, [user?.id, resetToWelcome]);

  const inputRef = useRef<any>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: WELCOME_MESSAGE },
  ]);
  const [stateSnapshot, setStateSnapshot] = useState<Record<string, unknown>>({});

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

  // ---- conversation persistence ----
  const saveConversation = useCallback(async (
    convId: string | null,
    msgs: Message[],
    snapshot: Record<string, unknown>,
  ) => {
    if (!user) return;
    const title = msgs.find((m) => m.role === "user")?.content?.slice(0, 30) || "新对话";
    try {
      const res = await request<{ id: string }>("/api/conversations", {
        method: "POST",
        body: {
          conversation_id: convId,
          title,
          state_snapshot: snapshot,
          messages: msgs,
        },
      });
      if (!convId && res?.id) {
        setConversationId(res.id);
      }
    } catch {
      // silent
    }
  }, [user]);

  const loadConversation = useCallback(async (id: string) => {
    try {
      const res = await request<{ conversation: ConversationDetail }>(`/api/conversations/${id}`);
      const conv = res.conversation;
      setConversationId(conv.id);
      setMessages(conv.messages as Message[]);
      setStateSnapshot(conv.state_snapshot as Record<string, unknown>);
      setShowSuggestions(false);
      // Reset agent steps to reflect loaded state
      setAgentSteps([
        { label: "已加载历史对话", status: "done", detail: `对话: ${conv.title}` },
        { label: "分析用户画像", status: "wait", detail: "" },
        { label: "匹配竞赛数据库", status: "wait", detail: "" },
        { label: "评估匹配程度", status: "wait", detail: "" },
        { label: "生成推荐方案", status: "wait", detail: "" },
      ]);
      return true;
    } catch {
      return false;
    }
  }, []);

  const newConversation = useCallback(() => {
    resetToWelcome();
    triggerHistoryRefresh();
  }, [resetToWelcome, triggerHistoryRefresh]);

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
        setStateSnapshot({});
        setMessages([{ role: "assistant", content: WELCOME_MESSAGE }]);
        setShowSuggestions(true);
        setAgentSteps([
          { label: "等待用户输入", status: "wait", detail: "请描述你的背景和需求" },
          { label: "分析用户画像", status: "wait", detail: "" },
          { label: "匹配竞赛数据库", status: "wait", detail: "" },
          { label: "评估匹配程度", status: "wait", detail: "" },
          { label: "生成推荐方案", status: "wait", detail: "" },
        ]);
        setLoading(false);
        setTimeout(() => inputRef.current?.focus(), 100);
        return;
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

      // Auto-save conversation for logged-in users
      const updatedMessages = [...messages, { role: "user" as const, content: text }, { role: "assistant" as const, content: result.response.text, files: result.response.files }];
      saveConversation(conversationId, updatedMessages, result.state_snapshot).then(() => {
        triggerHistoryRefresh();
      });

      const responseType = result.response.type;
      const hasRecommendations =
        Array.isArray(result.response.recommendations) &&
        result.response.recommendations.length > 0;

      if (responseType === "result" || hasRecommendations) {
        // 后端真正执行了推荐流程，有推荐结果
        updateAgentStep(2, "done", "已匹配到符合条件的竞赛数据");
        updateAgentStep(3, "done", "已完成多维度匹配评估");
        updateAgentStep(4, "done", "已生成个性化推荐方案");
      } else if (responseType === "need_input") {
        // 后端仍在收集用户信息，尚未执行推荐
        updateAgentStep(2, "wait", "等待信息收集完成后再检索");
        updateAgentStep(3, "wait", "");
        updateAgentStep(4, "wait", "");
      } else {
        // 一般性回复（agent/error），未触发推荐
        updateAgentStep(2, "wait", "本轮无需检索");
        updateAgentStep(3, "wait", "");
        updateAgentStep(4, "wait", "");
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "当前AI服务暂时无法连接，我已保留你的对话内容，请稍后重试。",
        },
      ]);
      updateAgentStep(1, "done", "连接失败");
      updateAgentStep(2, "wait", "未执行检索");
      updateAgentStep(3, "wait", "");
      updateAgentStep(4, "wait", "未生成推荐");
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
    conversationId,
    messages,
    agentSteps,
    userProfile,
    inputRef,
    messagesContainerRef,
    handleSend,
    handleSuggestionClick,
    loadConversation,
    newConversation,
    historyRefreshKey,
    recommendedCompetitions,
  };
}
