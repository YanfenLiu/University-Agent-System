// 快捷提示词
export const SUGGESTIONS = [
  "我是计算机专业大二学生，对AI感兴趣",
  "推荐几个适合新手的入门竞赛",
  "我想找团队赛，有创新类推荐吗",
  "数学专业，想参加建模类竞赛"
];

// 从用户输入中提取关键词（增强版：支持更多专业/兴趣/目标关键词）
export function extractKeywords(text: string): { major: string; interests: string[]; goal: string } {
  // 常见专业（支持模糊匹配）
  const majorMap: Record<string, string> = {
    "计算机": "计算机", "软件": "软件工程", "数学": "数学", "应用数学": "数学",
    "物理": "物理", "电子": "电子", "机械": "机械", "土木": "土木",
    "化工": "化工", "生物": "生物", "医学": "医学", "金融": "金融",
    "经济": "经济", "管理": "管理学", "文学": "文学", "法学": "法学",
    "艺术": "艺术", "设计": "设计", "人工智能": "人工智能", "大数据": "大数据",
    "统计": "统计学", "会计": "会计", "通信": "通信", "自动化": "自动化",
    "电气": "电气", "材料": "材料", "环境": "环境", "建筑": "建筑"
  };

  // 兴趣关键词（覆盖更多方向）
  const interestKeywords = [
    "AI", "人工智能", "算法", "编程", "创新", "创业", "建模", "大数据",
    "安全", "游戏", "前端", "后端", "全栈", "产品", "设计", "开发",
    "机器学习", "深度学习", "数据挖掘", "视觉", "自然语言", "物联网",
    "区块链", "云计算", "嵌入式", "机器人", "图像", "音频", "视频"
  ];

  // 目标关键词分类匹配（返回更友好的展示文本）
  // 按优先级排序：国奖类 > 省奖类 > 名次类 > 能力提升类 > 入门前置类
  const goalRules: { keywords: string[]; label: string; priority: number }[] = [
    { keywords: ["国奖", "国家级", "国家一等奖", "国家二等奖", "国家三等奖", "全国一等奖", "全国二等奖", "全国三等奖"], label: "国家级奖项", priority: 1 },
    { keywords: ["省奖", "省级", "省一", "省二", "省三", "省级一等奖", "省级二等奖", "省级三等奖"], label: "省级奖项", priority: 2 },
    { keywords: ["一等奖", "二等奖", "三等奖", "金奖", "银奖", "铜奖", "最高奖", "特等奖"], label: "高名次奖项", priority: 3 },
    { keywords: ["保研", "综测", "加分", "奖学金", "简历", "留学", "考研", "就业", "找工作"], label: "升学就业", priority: 4 },
    { keywords: ["提升经验", "参与", "体验", "锻炼", "能力", "技能", "实践机会", "增长见识", "涨经验"], label: "能力提升", priority: 5 },
    { keywords: ["奖金", "奖励", "奖品", "现金"], label: "奖金奖励", priority: 6 },
    { keywords: ["入门", "新手", "小白", "零基础", "初级", "基础", "尝试"], label: "入门尝试", priority: 7 },
    { keywords: ["进阶", "挑战", "突破", "提升", "拔高", "高难度"], label: "进阶挑战", priority: 8 },
  ];

  // 匹配专业（从长到短匹配，避免"计算"误匹配"计算机"）
  let major = "";
  const sortedMajors = Object.entries(majorMap).sort((a, b) => b[0].length - a[0].length);
  for (const [key, value] of sortedMajors) {
    if (text.includes(key)) {
      major = value;
      break;
    }
  }

  // 以"专业"、"系"等结尾的词也尝试提取
  const majorPattern = /([\u4e00-\u9fa5]{2,6})(?:专业|系|方向)/;
  const majorMatch = text.match(majorPattern);
  if (!major && majorMatch) {
    const potential = majorMatch[1];
    for (const [key, value] of sortedMajors) {
      if (potential.includes(key) || key.includes(potential)) {
        major = value;
        break;
      }
    }
  }

  // 兴趣匹配（大小写不敏感）
  const interests = interestKeywords.filter(k => {
    if (k === "AI") return text.includes("AI") || text.includes("人工智能");
    return text.includes(k);
  });

  // 目标匹配（按优先级返回最匹配的目标类别）
  let goal = "";
  for (const rule of goalRules) {
    if (rule.keywords.some(k => text.includes(k))) {
      goal = rule.label;
      break;
    }
  }

  return { major, interests, goal };
}
