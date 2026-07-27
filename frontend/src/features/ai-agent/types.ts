/** AI 对话消息 */
export type Message = {
  role: "user" | "assistant";
  content: string;
};

/** Agent 工作流步骤 */
export interface AgentStep {
  label: string;
  status: "wait" | "running" | "done";
  detail: string;
}

/** 用户画像 */
export interface UserProfile {
  major: string;
  interests: string[];
  goal: string;
  matched: boolean;
}

/** Agent 整体运行状态 */
export type AgentStatus =
  | "idle"
  | "analyzing"
  | "matching"
  | "evaluating"
  | "generating"
  | "done"
  | "error";

/** Agent API 响应（后端返回结构） */
export interface AgentResponse {
  success: boolean;
  session_id: string;
  response: {
    text: string;
    type: "agent" | "error" | "need_input" | "result";
    files: unknown[];
    recommendations: unknown[];
  };
  state_snapshot: Record<string, unknown>;
  metadata: Record<string, unknown>;
}

/** 增强对话消息（带可选元数据） */
export interface AgentMessage extends Message {
  id?: string;
  timestamp?: number;
}
