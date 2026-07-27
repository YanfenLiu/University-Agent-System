import {
  Card,
  Col,
  Row,
  Space,
  Typography,
  Input,
  Button,
  Tag,
  message
} from "antd";

import {
  SendOutlined,
  RobotOutlined,
  BulbOutlined
} from "@ant-design/icons";

import { CompetitionCard } from "../components/CompetitionCard";
import { useCompetitions } from "../contexts/CompetitionsContext";
import { designTokens } from "../styles/tokens";
import { useAgentChat } from "../features/ai-agent/hooks/useAgentChat";
import { ChatSuggestions } from "../features/ai-agent/components/ChatSuggestions";
import { ChatMessage } from "../features/ai-agent/components/ChatMessage";
import { ChatLoading } from "../features/ai-agent/components/ChatLoading";
import { AgentStatusCard } from "../features/ai-agent/components/AgentStatusCard";
import { UserProfileCard } from "../features/ai-agent/components/UserProfileCard";


export function AIRecommendation() {
  const {
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
  } = useAgentChat();
  const { isJoined, addCompetition } = useCompetitions();
  const { colorPrimary, borderRadius } = designTokens;

  return (
    <Space
      direction="vertical"
      size="large"
      style={{ width: "100%" }}
    >
      {/* 页面标题 */}
      <div>
        <Typography.Title level={2} style={{ marginBottom: 4, display: "flex", alignItems: "center", gap: 8 }}>
          <RobotOutlined style={{ color: colorPrimary }} />
          赛智通 AI竞赛智能体
        </Typography.Title>
        <Typography.Text type="secondary" style={{ fontSize: 15 }}>
          智能分析你的背景，自动规划最优竞赛路线
        </Typography.Text>
      </div>

      {/* 主区域：左右两列等高 */}
      <Row gutter={24} style={{ minHeight: 580 }}>
        {/* 左侧：对话区 */}
        <Col xs={24} md={16}>
          <div
            style={{
              height: "100%",
              display: "flex",
              flexDirection: "column",
              background: "#fff",
              borderRadius: borderRadius,
              boxShadow: "0 12px 40px rgba(15, 23, 42, 0.08)",
              overflow: "hidden",
              border: "1px solid rgba(22, 119, 255, 0.08)"
            }}
          >
            {/* 对话头部 */}
            <div
              style={{
                padding: "16px 20px",
                borderBottom: "1px solid rgba(15, 23, 42, 0.06)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                background: "linear-gradient(135deg, rgba(22,119,255,0.03) 0%, rgba(22,119,255,0.08) 100%)"
              }}
            >
              <Space align="center" size={10}>
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 8,
                    background: `linear-gradient(135deg, ${colorPrimary}, #4096ff)`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center"
                  }}
                >
                  <RobotOutlined style={{ color: "#fff", fontSize: 16 }} />
                </div>
                <div>
                  <Typography.Text strong style={{ fontSize: 15 }}>AI 智能对话</Typography.Text>
                  <div>
                    <Tag
                      color={loading ? "processing" : "success"}
                      style={{ fontSize: 11, lineHeight: "18px", padding: "0 6px", margin: 0 }}
                    >
                      {loading ? "AI 正在推理中" : "等待输入"}
                    </Tag>
                  </div>
                </div>
              </Space>
              <BulbOutlined style={{ color: colorPrimary, fontSize: 18, opacity: 0.6 }} />
            </div>

            {/* 消息区域 */}
            <div
              ref={messagesContainerRef}
              style={{
                flex: 1,
                overflowY: "auto",
                padding: "20px",
                background: "#f8faff"
              }}
            >
              <ChatSuggestions
                visible={showSuggestions}
                messageCount={messages.length}
                colorPrimary={colorPrimary}
                onSelect={handleSuggestionClick}
              />

              {messages.map((msg, index) => (
                <ChatMessage key={index} message={msg} colorPrimary={colorPrimary} />
              ))}

              {loading && <ChatLoading colorPrimary={colorPrimary} />}

            </div>

            {/* 输入区域 */}
            <div style={{ padding: "16px 20px", borderTop: "1px solid rgba(15, 23, 42, 0.06)", background: "#fff" }}>
              <Input.TextArea
                ref={inputRef}
                value={input}
                rows={2}
                placeholder="输入你的专业、兴趣和竞赛目标..."
                onChange={e => setInput(e.target.value)}
                onPressEnter={e => {
                  if (!e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                style={{
                  borderRadius: 12,
                  resize: "none",
                  fontSize: 14,
                  padding: "10px 14px"
                }}
              />
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  loading={loading}
                  style={{ borderRadius: 10, height: 38, padding: "0 20px" }}
                  onClick={handleSend}
                >
                  {loading ? "AI 分析中" : "发送"}
                </Button>
              </div>
            </div>
          </div>
        </Col>

        {/* 右侧：Agent 状态 + 用户画像 */}
        <Col xs={24} md={8}>
          <div
            style={{
              height: "100%",
              display: "flex",
              flexDirection: "column",
              gap: 16
            }}
          >
            <AgentStatusCard
              steps={agentSteps}
              colorPrimary={colorPrimary}
              borderRadius={borderRadius}
            />

            <UserProfileCard
              profile={userProfile}
              colorPrimary={colorPrimary}
              borderRadius={borderRadius}
            />
          </div>
        </Col>
      </Row>

      {/* 推荐竞赛方案区域 */}
      <Card
        title={
          <div>
            <Typography.Title level={4} style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
              <BulbOutlined style={{ color: colorPrimary }} />
              AI 为你推荐的竞赛方案
            </Typography.Title>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              {userProfile.matched
                ? `基于你的背景（${[userProfile.major, ...userProfile.interests].filter(Boolean).join("、")}），已为你筛选出最契合的竞赛`
                : "完成对话后，AI将根据你的情况推荐最适合的竞赛"}
            </Typography.Text>
          </div>
        }
        style={{
          borderRadius: borderRadius,
          boxShadow: "0 12px 40px rgba(15, 23, 42, 0.08)",
          border: "1px solid rgba(22, 119, 255, 0.08)"
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
            gap: 16
          }}
        >
          {recommendedCompetitions.slice(0, 10).map((item, index) => (
            <div key={item.id} style={{ position: "relative" }}>
              {/* AI 匹配度标签 */}
              {userProfile.matched && (
                <div
                  style={{
                    position: "absolute",
                    top: -6,
                    right: -6,
                    zIndex: 10,
                    background: `linear-gradient(135deg, ${colorPrimary}, #4096ff)`,
                    color: "#fff",
                    fontSize: 11,
                    padding: "2px 10px",
                    borderRadius: 12,
                    boxShadow: "0 2px 8px rgba(22, 119, 255, 0.3)"
                  }}
                >
                  AI 推荐 #{index + 1}
                </div>
              )}
              <CompetitionCard
                competition={item}
                joined={isJoined(item.id)}
                onAdd={() => {
                  addCompetition(item);
                  message.success('已加入我的竞赛');
                }}
              />
            </div>
          ))}
        </div>
      </Card>
    </Space>
  );
}
