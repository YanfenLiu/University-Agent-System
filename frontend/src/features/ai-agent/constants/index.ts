import type { AgentStatus } from "../types";

/** Agent 工作流步骤状态 */
export const STEP_STATUS = {
  WAIT: "wait",
  RUNNING: "running",
  DONE: "done",
} as const;

/** Agent 整体运行状态枚举 */
export const AGENT_STATUS: Record<AgentStatus, AgentStatus> = {
  idle: "idle",
  analyzing: "analyzing",
  matching: "matching",
  evaluating: "evaluating",
  generating: "generating",
  done: "done",
  error: "error",
};

/** 系统 Prompt 模板 */
export const SYSTEM_PROMPT = `你是一个帮助大学生规划竞赛的 AI 助手。
请根据用户提供的专业、兴趣和目标，推荐适合的竞赛。`;

/** 初始欢迎消息 */
export const WELCOME_MESSAGE =
  "你好，我是**赛智通竞赛助手**。\n\n" +
  "我可以根据你的专业、年级和兴趣方向推荐竞赛，也可以帮你了解赛事要求、比较项目或准备报名材料。\n\n" +
  "先简单说说你的专业和年级吧。";

/** 快捷提示词 */
export const SUGGESTIONS = [
  "我是计算机专业大二学生，对AI感兴趣",
  "推荐几个适合新手的入门竞赛",
  "我想找团队赛，有创新类推荐吗",
  "数学专业，想参加建模类竞赛",
];
