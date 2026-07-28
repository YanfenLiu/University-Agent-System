import { useState, useEffect, useRef, useCallback } from "react";
import { extractKeywords } from "../utils/extractKeywords";
import { recommendCompetitions } from "../utils/recommendCompetitions";
import { sendMessage } from "../services";
import { useCompetitionsData } from "../../../contexts/CompetitionsDataContext";
import type { Competition, DimensionalScores } from "../../../services/competitions";
import type { Message, AgentStep, UserProfile, AgentResponse } from "../types";

export function useAgentChat() {
  const inputRef = useRef<any>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);

  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content:
        "你好！我是 **赛智通 AI 竞赛智能体** 🤖\n\n我可以帮你分析专业背景、推荐适合的竞赛、规划参赛路线。\n\n**请告诉我：**\n• 你的专业是什么？\n• 你对哪些方向感兴趣？\n• 你想达到什么目标？",
    },
  ]);

  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([
    { label: "等待用户输入", status: "wait", detail: "请描述你的背景和需求" },
    { label: "分析用户画像", status: "wait", detail: "" },
    { label: "匹配竞赛数据库", status: "wait", detail: "" },
    { label: "评估匹配程度", status: "wait", detail: "" },
    { label: "生成推荐方案", status: "wait", detail: "" },
  ]);

  const [userProfile, setUserProfile] = useState<UserProfile>({
    major: "",
    interests: [],
    goal: "",
    matched: false,
  });

  // 后端 API 返回的推荐结果（优先使用，格式转换为本地 Competition 类型）
  const [backendRecommendations, setBackendRecommendations] = useState<Competition[]>([]);

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
    updateAgentStep(1, "running", "正在提取关键词...");
    await new Promise((r) => setTimeout(r, 400));

    const { major, interests, goal } = extractKeywords(text);

    // 立即合并提取结果，不依赖 React state 的异步更新
    const mergedProfile: UserProfile = {
      major: major || userProfile.major,
      interests: [
        ...new Set([...userProfile.interests, ...interests]),
      ],
      goal: goal || userProfile.goal,
      matched: !!(major || interests.length > 0 || goal || userProfile.matched),
    };
    setUserProfile(mergedProfile);

    updateAgentStep(
      1,
      "done",
      mergedProfile.major
        ? `已识别专业: ${mergedProfile.major}`
        : "继续分析用户输入...",
    );

    updateAgentStep(2, "running", "正在搜索相关竞赛...");
    await new Promise((r) => setTimeout(r, 500));

    // 构造对话上下文，为多轮状态传递做准备
    const conversationContext: Record<string, unknown> = {
      major: mergedProfile.major,
      interests: mergedProfile.interests,
      goal: mergedProfile.goal,
      last_recommendations: backendRecommendations,
    };

    try {
      const result: AgentResponse = await sendMessage(
        text,
        mergedProfile as unknown as Record<string, unknown>,
        messages.slice(-10).map((m) => ({ role: m.role, content: m.content })),
        conversationContext,
      );

      // 使用后端返回的推荐结果（当存在时），并转换为本地 Competition 格式
      // 完整保留后端推荐引擎生成的 reason、match_score、detail（六维评分）、
      // matched_signals、unmatched_signals、risk、suggested_action 等字段
      const backendRecs = result.response?.recommendations;
      if (Array.isArray(backendRecs) && backendRecs.length > 0) {
        const mapped: Competition[] = backendRecs.map((rec: any, idx: number) => {
          // 构建 tags 列表
          let tags: string[] = ["竞赛"];
          if (Array.isArray(rec.requirements?.tags)) {
            tags = rec.requirements.tags;
          } else if (Array.isArray(rec.tags)) {
            tags = rec.tags;
          } else if (rec.requirements?.category) {
            tags = [rec.requirements.category];
          } else if (rec.type) {
            tags = [rec.type];
          }

          // 补充 DimensionalScores 中的 team_score
          const detail: DimensionalScores | undefined = rec.detail
            ? { ...rec.detail }
            : undefined;

          // 匹配信号保留原始字符串列表
          const matched_signals: string[] | undefined = Array.isArray(rec.matched_signals)
            ? rec.matched_signals
            : undefined;
          const unmatched_signals: string[] | undefined = Array.isArray(rec.unmatched_signals)
            ? rec.unmatched_signals
            : undefined;

          return {
            id: rec.id || -(idx + 1),
            name: rec.title || rec.name || "未命名竞赛",
            summary: rec.summary || rec.description || "",
            difficulty: (rec.level === "国际级" || rec.level === "国家级") ? "挑战" :
                        (rec.level === "省级") ? "进阶" : "入门",
            deadline: rec.deadline || rec.regist_end || "待核实",
            officialUrl: rec.source_url || rec.url || "",
            reason: rec.reason || rec.summary || "",
            tags,
            status: (rec.match_score != null && rec.match_score >= 80) ? "推荐" :
                    (rec.deadline ? "报名中" : "热门"),
            /* ---- 保留后端原始增强字段 ---- */
            match_score: rec.match_score != null ? Number(rec.match_score) : undefined,
            recommend_level: rec.recommend_level || undefined,
            detail,
            matched_signals,
            unmatched_signals,
            risk: rec.risk || undefined,
            suggested_action: rec.suggested_action || undefined,
            organizer: rec.organizer || undefined,
          };
        });
        setBackendRecommendations(mapped);
      }

      updateAgentStep(2, "done", "数据库匹配完成");
      updateAgentStep(3, "running", "正在评估匹配度...");
      await new Promise((r) => setTimeout(r, 300));

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: result.response.text,
        },
      ]);

      updateAgentStep(3, "done", "评估完成");
      updateAgentStep(4, "running", "生成推荐方案...");
      await new Promise((r) => setTimeout(r, 300));
      updateAgentStep(4, "done", "推荐方案已就绪");
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "😅 抱歉，AI 暂时无法连接，请稍后再试。你可以先查看下方的竞赛列表。",
        },
      ]);
      updateAgentStep(2, "done", "连接失败，使用本地数据");
      updateAgentStep(3, "done", "已切换至离线模式");
      updateAgentStep(4, "done", "已展示本地推荐");
    }

    setLoading(false);
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const handleSend = useCallback(async () => {
    await processMessage(input);
  }, [input]);

  const handleSuggestionClick = useCallback((text: string) => {
    processMessage(text);
  }, []);

  // 响应式获取竞赛数据（Supabase 加载后自动更新）
  const localCompetitions = useCompetitionsData();

  // 合并推荐结果：后端推荐优先，不足时用本地推荐补充
  const recommendedCompetitions: Competition[] =
    backendRecommendations.length > 0
      ? backendRecommendations
      : recommendCompetitions(localCompetitions, userProfile);

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
