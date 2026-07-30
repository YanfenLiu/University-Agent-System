import { Card, Space, Tag, Typography, Divider } from "antd";
import { UserOutlined } from "@ant-design/icons";

interface UserProfile {
  major: string;
  interests: string[];
  goal: string;
  matched: boolean;
}

interface UserProfileCardProps {
  profile: UserProfile;
  colorPrimary: string;
  borderRadius: number | string;
}

function getRecommendationType(profile: UserProfile): string {
  const { interests, major } = profile;
  if (interests.includes("AI") || interests.includes("人工智能")) return "AI创新类";
  if (interests.includes("创业") || interests.includes("创新")) return "创新创业类";
  if (interests.some((i) => ["建模", "算法", "大数据"].includes(i))) return "数理建模类";
  if (major.includes("数学") || major.includes("统计")) return "数理建模类";
  return "综合实践类";
}

export function UserProfileCard({ profile, colorPrimary, borderRadius }: UserProfileCardProps) {
  const placeholder = profile.matched ? "AI 分析中..." : "等待输入...";

  return (
    <Card
      title={
        <Space align="center" size={8}>
          <UserOutlined style={{ color: colorPrimary }} />
          <span>用户画像</span>
        </Space>
      }
      styles={{ body: { padding: "12px 16px" } }}
      style={{
        borderRadius,
        boxShadow: "0 12px 40px rgba(15, 23, 42, 0.08)",
        border: "1px solid rgba(22, 119, 255, 0.08)",
        flex: 1,
      }}
    >
      <Space direction="vertical" size="small" style={{ width: "100%" }}>
        <div>
          <Typography.Text style={{ fontSize: 13, color: "rgba(15,23,42,0.5)" }}>
            专业
          </Typography.Text>
          <div style={{ marginTop: 2 }}>
            <Tag
              color={profile.major ? "blue" : "default"}
              style={{ borderRadius: 6, fontSize: 12, padding: "2px 10px" }}
            >
              {profile.major || placeholder}
            </Tag>
          </div>
        </div>

        <Divider style={{ margin: "6px 0" }} />

        <div>
          <Typography.Text style={{ fontSize: 13, color: "rgba(15,23,42,0.5)" }}>
            兴趣方向
          </Typography.Text>
          <div style={{ marginTop: 2, display: "flex", flexWrap: "wrap", gap: 4 }}>
            {profile.interests.length > 0
              ? profile.interests.map((tag, i) => (
                  <Tag
                    key={i}
                    color="green"
                    style={{ borderRadius: 6, fontSize: 12, padding: "2px 10px" }}
                  >
                    {tag}
                  </Tag>
                ))
              : (
                <Tag
                  color="default"
                  style={{ borderRadius: 6, fontSize: 12, padding: "2px 10px" }}
                >
                  {placeholder}
                </Tag>
              )}
          </div>
        </div>

        <Divider style={{ margin: "6px 0" }} />

        <div>
          <Typography.Text style={{ fontSize: 13, color: "rgba(15,23,42,0.5)" }}>
            竞赛目标
          </Typography.Text>
          <div style={{ marginTop: 2 }}>
            <Tag
              color={profile.goal ? "purple" : "default"}
              style={{ borderRadius: 6, fontSize: 12, padding: "2px 10px" }}
            >
              {profile.goal || placeholder}
            </Tag>
          </div>
        </div>

        <Divider style={{ margin: "6px 0" }} />

        <div>
          <Typography.Text style={{ fontSize: 13, color: "rgba(15,23,42,0.5)" }}>
            推荐倾向
          </Typography.Text>
          <div style={{ marginTop: 2 }}>
            <Tag
              color="gold"
              style={{ borderRadius: 6, fontSize: 12, padding: "2px 10px" }}
            >
              {getRecommendationType(profile)}
            </Tag>
          </div>
        </div>
      </Space>
    </Card>
  );
}
