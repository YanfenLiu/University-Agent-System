import { request } from "./apiClient";
import type { AgentResponse } from "../features/ai-agent/types";
import { apiUrl } from "./apiClient";

export type { AgentResponse };

let sessionId = "";

export async function sendMessage(
  message: string,
  stateSnapshot: Record<string, unknown>,
): Promise<AgentResponse> {
  try {
    const body: Record<string, unknown> = {
      user_input: message,
      state_snapshot: stateSnapshot,
    };

    const data = await request<Record<string, unknown>>(
      "/api/agent/run",
      {
        method: "POST",
        body,
        timeout: 300000,
      },
    );

    // Fail clearly when GitHub Pages has updated but Render is still serving
    // the legacy API.  Silently accepting that response loses conversation
    // state and can expose backend orchestration messages to the user.
    if (
      !Object.prototype.hasOwnProperty.call(data, "state_snapshot") ||
      !data.state_snapshot ||
      typeof data.state_snapshot !== "object"
    ) {
      return {
        success: false,
        session_id: sessionId,
        response: {
          text: "后端服务版本尚未更新，请先在 Render 部署 main 分支的最新提交后再试。",
          type: "error",
          files: [],
          recommendations: [],
        },
        state_snapshot: stateSnapshot,
        metadata: {
          status: "error",
          error_code: "backend_version_mismatch",
        },
      };
    }

    const responseData = (data?.response as Record<string, unknown>) || {};
    const rawRecs = responseData?.recommendations;
    const recommendations: Array<Record<string, unknown>> = Array.isArray(rawRecs)
      ? (rawRecs as Array<Record<string, unknown>>)
      : [];

    const respType = String(responseData?.type || (data?.success ? "agent" : "error"));
    // 后端可能返回 "result"（partial + 有推荐）、"agent"、"need_input"、"error"
    const allowedTypes = ["agent", "error", "need_input", "result", "reset"] as const;
    const safeType = (allowedTypes as readonly string[]).includes(respType) ? respType as typeof allowedTypes[number] : "agent";
    const isSuccess = Boolean(data?.success);

    return {
      success: isSuccess,
      session_id: sessionId,
      response: {
        text: (responseData?.text as string) || (isSuccess ? "Agent 执行完毕。" : "请告诉我你的专业和年级，以便为你推荐竞赛。"),
        type: safeType,
        files: Array.isArray(responseData?.files)
          ? responseData.files.map((item) => apiUrl(String(item)))
          : [],
        recommendations,
      },
      state_snapshot:
        data?.state_snapshot && typeof data.state_snapshot === "object"
          ? (data.state_snapshot as Record<string, unknown>)
          : stateSnapshot,
      metadata:
        data?.metadata && typeof data.metadata === "object"
          ? (data.metadata as Record<string, unknown>)
          : { status: isSuccess ? "success" : "error" },
    };
  } catch (error) {
    console.error("Agent request failed:", error);

    return {
      success: false,
      session_id: sessionId,
      response: {
        text: "智能体暂时无法连接，请检查后端服务。",
        type: "error",
        files: [],
        recommendations: [],
      },
      state_snapshot: stateSnapshot,
      metadata: { status: "error" },
    };
  }
}
