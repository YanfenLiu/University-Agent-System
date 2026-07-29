import { Button, Card, Col, Row, Space, Tag, Typography, message } from 'antd';
import { useState, useEffect, useRef } from 'react';

import {
  TrophyOutlined,
  RobotOutlined,
  ThunderboltOutlined,
  ArrowRightOutlined,
  FireOutlined,
  RocketOutlined,
} from '@ant-design/icons';

import { CompetitionCard } from '../components/CompetitionCard';
import { useNavigation } from '../contexts/NavigationContext';
import { useCompetitionsData } from '../contexts/CompetitionsDataContext';
import { useCompetitions } from '../contexts/CompetitionsContext';
import { designTokens } from '../styles/tokens';


const CARD_STYLE = {
  borderRadius: designTokens.borderRadius,
  border: '1px solid rgba(22,119,255,0.08)',
  boxShadow: '0 4px 16px rgba(15,23,42,0.06)',
};
const CARD_BODY = { padding: '20px 24px' };

const SEC_GAP = { marginBottom: designTokens.spacing.xxl };


function SectionHeader({ icon, title, sub, action }: { icon: React.ReactNode; title: string; sub?: string; action?: React.ReactNode; }) {
  return (
    <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom: designTokens.spacing.md }}>
      <div>
        <Typography.Title level={4} style={{ margin:0, display:'flex', alignItems:'center', gap:8, fontSize:18 }}>
          {icon}{title}
        </Typography.Title>
        {sub && <Typography.Text type='secondary' style={{ fontSize:13, marginTop:2, display:'block' }}>{sub}</Typography.Text>}
      </div>
      {action}
    </div>
  );
}

const WORKFLOW_NODES = [
  { step: '01', label: '输入需求', desc: '描述专业、兴趣与目标', color: '#60a5fa' },
  { step: '02', label: '分析画像', desc: 'AI 提取关键信息', color: '#34d399' },
  { step: '03', label: '匹配数据库', desc: '搜索最契合的赛事', color: '#fbbf24' },
  { step: '04', label: '评估匹配度', desc: '综合打分与排序', color: '#f472b6' },
  { step: '05', label: '生成方案', desc: '输出个性化推荐路线', color: '#a78bfa' },
];

// 工作流提示文字
const STATUS_TEXTS = [
  '正在等待输入你的需求…',
  'AI 正在分析你的画像特征…',
  '正在搜索最契合的赛事资源…',
  'AI 正在综合评分与排序…',
  '个性化方案生成完毕，点击开始查看！',
];

// 赛智通首页
export function Home() {
    const competitions = useCompetitionsData();
  const hot = competitions.slice(0,3);
  const { navigateTo } = useNavigation();
  const { addCompetition, isJoined } = useCompetitions();
    const [aiLoading, setAiLoading] = useState(false);
    // 工作流动态轮播
    const [activeStep, setActiveStep] = useState(0);
    const [visibleNodes, setVisibleNodes] = useState<number[]>([]);
    const flowIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

    // 节点逐个出现动画
    useEffect(() => {
      const timers: ReturnType<typeof setTimeout>[] = [];
      WORKFLOW_NODES.forEach((_, i) => {
        timers.push(setTimeout(() => {
          setVisibleNodes(prev => [...prev, i]);
        }, i * 200));
      });
      return () => timers.forEach(t => clearTimeout(t));
    }, []);

    // 步骤循环轮播
    useEffect(() => {
      flowIntervalRef.current = setInterval(() => {
        setActiveStep(prev => (prev + 1) % WORKFLOW_NODES.length);
      }, 2500);
      return () => {
        if (flowIntervalRef.current) clearInterval(flowIntervalRef.current);
      };
    }, []);

    const goAI = () => {
      setAiLoading(true);
      navigateTo('ai');
      setTimeout(() => setAiLoading(false), 3000);
    };
    const goMine = () => navigateTo('mine');
    const goLibrary = () => navigateTo('library');

    return (
    <div className="fade-in">

      {/* ===== HERO SECTION ===== */}
      <div style={{ position:'relative', overflow:'hidden', borderRadius: designTokens.borderRadius, background:'linear-gradient(135deg,#0c1833 0%,#132952 40%,#1a3a6b 100%)', padding:'72px 52px', ...SEC_GAP }}>
        <div style={{ position:'absolute', inset:0, opacity:0.04, backgroundImage:'linear-gradient(rgba(255,255,255,0.3) 1px,transparent 1px), linear-gradient(90deg,rgba(255,255,255,0.3) 1px,transparent 1px)', backgroundSize:'48px 48px' }} />
        <div style={{ position:'absolute', top:-80, right:'40%', width:400, height:400, borderRadius:'50%', background:'radial-gradient(circle, rgba(22,119,255,0.18) 0%, transparent 70%)', animation:'glowPulse 4s ease-in-out infinite' }} />
        <div style={{ position:'absolute', bottom:-40, left:-40, width:200, height:200, borderRadius:'50%', background:'radial-gradient(circle, rgba(82,196,26,0.10) 0%, transparent 70%)' }} />

        <Row gutter={48} align="middle" style={{ position:'relative', zIndex:1 }}>

          {/* LEFT: 文案 */}
          <Col xs={24} lg={14}>
            <div style={{ maxWidth:620 }}>
              <div style={{ marginBottom: designTokens.spacing.md }}>
                <Tag style={{ borderRadius:20, padding:'4px 14px', fontSize:13, margin:0, background:'rgba(255,255,255,0.10)', color:'rgba(255,255,255,0.85)', border:'1px solid rgba(255,255,255,0.15)', fontWeight:500 }}>
                  <RocketOutlined style={{ marginRight:6 }} /> 基于 AI Agent 的竞赛规划平台
                </Tag>
              </div>

              <Typography.Title level={1} style={{ color:'#fff', margin:0, marginBottom: designTokens.spacing.md, fontSize:40, fontWeight:700, letterSpacing:'-0.5px', lineHeight:1.2 }}>
                让 AI 智能体为你找到<br />最适合的竞赛
              </Typography.Title>

              <Typography.Paragraph style={{ color:'rgba(255,255,255,0.85)', fontSize:16, margin:0, marginBottom: designTokens.spacing.xl, lineHeight:1.8 }}>
                描述你的专业、兴趣和目标，AI 自动分析画像，精准匹配赛事库，生成个性化参赛规划。从选择到备赛，全程智能辅助。
              </Typography.Paragraph>

              <div style={{ display:'flex', gap:12, alignItems:'center' }}>
                <Button
                  type='primary' size='large' icon={<RobotOutlined />} onClick={goAI} loading={aiLoading}
                  style={{ height:50, padding:'0 32px', borderRadius:12, fontSize:15, fontWeight:500, border:'none', boxShadow:'0 8px 24px rgba(22,119,255,0.35)', display:'flex', alignItems:'center' }}
                >
                  {aiLoading ? 'AI 分析中...' : '开始 AI 竞赛规划'}
                  {!aiLoading && <ArrowRightOutlined style={{ marginLeft:8, fontSize:14 }} />}
                </Button>
                <Button size='large' ghost icon={<TrophyOutlined />} onClick={goMine}
                  style={{ height:50, padding:'0 24px', borderRadius:12, fontSize:14, color:'rgba(255,255,255,0.8)', borderColor:'rgba(255,255,255,0.2)' }}>
                  查看我的竞赛
                </Button>
              </div>

              {/* 价值亮点 */}
              <div style={{ marginTop:36, display:'flex', gap:28, flexWrap:'wrap' }}>
                {[
                  { label: '竞赛收录', value: competitions.length + ' 个', color: '#1677ff' },
                  { label: '智能匹配', value: 'AI 精准推荐', color: '#52c41a' },
                  { label: '自动规划', value: '5 步完成', color: '#fa8c16' },
                ].map((item, i) => (
                  <div key={i} style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <div style={{ width:6, height:6, borderRadius:'50%', background:item.color, opacity:0.7 }} />
                    <div>
                      <Typography.Text style={{ color:'#fff', fontSize:16, fontWeight:600, display:'block', lineHeight:1.3 }}>{item.value}</Typography.Text>
                      <Typography.Text style={{ color:'rgba(255,255,255,0.8)', fontSize:12 }}>{item.label}</Typography.Text>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Col>

          {/* RIGHT: AI Agent 工作流可视化 */}
          <Col xs={24} lg={10}>
            <div style={{ position:'relative', padding:'32px 24px', background:'rgba(255,255,255,0.04)', borderRadius:16, border:'1px solid rgba(255,255,255,0.08)', backdropFilter:'blur(8px)' }}>
              <div style={{ textAlign:'center', marginBottom:28 }}>
                <Typography.Text style={{ color:'rgba(255,255,255,0.7)', fontSize:11, textTransform:'uppercase', letterSpacing:1.5, fontWeight:500 }}>
                  AI Agent Workflow
                </Typography.Text>
                <Typography.Text style={{ color:'#fff', fontSize:13, display:'block', marginTop:4, opacity:0.75 }}>
                  从输入需求到获得方案，全程自动化
                </Typography.Text>
              </div>

                            {WORKFLOW_NODES.map((node, i) => {
                const isActive = i === activeStep;
                const isPast = i < activeStep;
                const isVisible = visibleNodes.includes(i);
                const isLast = i === WORKFLOW_NODES.length - 1;

                return (
                <div key={i} style={{
                  display:'flex', alignItems:'center', gap:14,
                  marginBottom: isLast ? 0 : 18,
                  position:'relative',
                  opacity: isVisible ? 1 : 0,
                  transform: isVisible ? 'translateX(0)' : 'translateX(-20px)',
                  transition: 'opacity 0.5s ease-out, transform 0.5s ease-out',
                  transitionDelay: i * 0.05 + 's',
                }}>
                  {!isLast && (
                    <div style={{
                      position:'absolute', left:15, top:34, width:2, height:26,
                      background: isPast
                        ? 'linear-gradient(to bottom, ' + node.color + ', ' + WORKFLOW_NODES[i+1].color + ')'
                        : isActive
                          ? 'linear-gradient(to bottom, ' + node.color + '80, ' + WORKFLOW_NODES[i+1].color + '20)'
                          : 'linear-gradient(to bottom, ' + node.color + '20, ' + WORKFLOW_NODES[i+1].color + '20)',
                      transition: 'background 0.8s ease',
                      boxShadow: isPast ? '0 0 6px ' + node.color + '60' : 'none',
                    }} />
                  )}
                  <div style={{
                    width:32, height:32, borderRadius:'50%',
                    background: isActive
                      ? 'linear-gradient(135deg, ' + node.color + ', ' + node.color + '80)'
                      : 'linear-gradient(135deg, ' + node.color + '30, ' + node.color + '10)',
                    border: isActive
                      ? '2px solid ' + node.color
                      : '1px solid ' + node.color + '50',
                    display:'flex', alignItems:'center', justifyContent:'center',
                    color: isActive ? '#fff' : node.color,
                    fontSize:11, fontWeight:600, flexShrink:0,
                    position:'relative', zIndex:1,
                    transform: isActive ? 'scale(1.15)' : 'scale(1)',
                    transition: 'all 0.4s ease',
                    boxShadow: isActive ? '0 0 20px ' + node.color + '80' : 'none',
                  }}>
                    {isActive ? (
                      <div style={{
                        width:14, height:14, borderRadius:'50%',
                        border:'2px solid rgba(255,255,255,0.6)',
                        borderTopColor:'#fff',
                        animation:'spinnerRotate 0.8s linear infinite',
                      }} />
                    ) : isPast ? '✓' : node.step}
                  </div>
                  <div style={{ flex:1 }}>
                    <Typography.Text style={{
                      color: isActive ? '#fff' : isPast ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.5)',
                      fontSize: isActive ? 14 : 13,
                      fontWeight: isActive ? 600 : 500,
                      display:'block',
                      transition: 'all 0.4s ease',
                    }}>{node.label}</Typography.Text>
                    <Typography.Text style={{
                      color: isActive ? node.color : isPast ? 'rgba(255,255,255,0.6)' : 'rgba(255,255,255,0.4)',
                      fontSize:12,
                      transition: 'all 0.4s ease',
                    }}>{isActive ? node.desc + '…' : node.desc}</Typography.Text>
                  </div>
                  <div style={{
                    width:8, height:8, borderRadius:'50%',
                    background: isActive ? node.color : isPast ? node.color + '80' : 'rgba(255,255,255,0.1)',
                    boxShadow: isActive ? '0 0 14px ' + node.color : isPast ? '0 0 6px ' + node.color + '40' : 'none',
                    animation: isActive ? 'nodePulse 1.5s ease-in-out infinite' : 'none',
                    transition: 'all 0.4s ease',
                  }} />
                </div>
                );
              })}

              <div style={{
                marginTop:24, padding:'12px 16px',
                background: 'linear-gradient(135deg, rgba(22,119,255,0.12), rgba(22,119,255,0.05))',
                borderRadius:10, border:'1px solid rgba(22,119,255,0.2)',
                display:'flex', alignItems:'center', gap:10,
              }}>
                <div style={{
                  width:22, height:22, borderRadius:'50%',
                  border:'2.5px solid rgba(22,119,255,0.25)',
                  borderTopColor:'#1677ff',
                  borderRightColor:'#1677ff',
                  animation:'spinnerRotate 0.8s linear infinite',
                  flexShrink:0,
                }} />
                <Typography.Text style={{
                  color:'rgba(255,255,255,0.85)', fontSize:12,
                  animation:'textBlink 2s ease-in-out infinite',
                }}>
                  {STATUS_TEXTS[activeStep]}
                </Typography.Text>
              </div>
            </div>
          </Col>

        </Row>
      </div>

      {/* ===== 产品功能介绍卡片 ===== */}
      <Row gutter={[designTokens.spacing.lg, designTokens.spacing.md]} style={SEC_GAP}>
        {[
          {
            icon: <RobotOutlined style={{ color:'#fff', fontSize:20 }} />,
            gradient:'linear-gradient(135deg,#1677ff,#4096ff)',
            title:'AI 智能规划',
            desc:'输入你的专业背景、兴趣爱好和竞赛目标，AI 自动分析并匹配最适合你的赛事。',
            arrowColor:'#1677ff',
            onClick:goAI,
            metric:'5 步完成匹配'
          },
                    {
            icon: <TrophyOutlined style={{ color:'#fff', fontSize:20 }} />,
            gradient:'linear-gradient(135deg,#52c41a,#73d13d)',
            title:'浏览竞赛库',
            desc: competitions.length + ' 个赛事资源，涵盖 AI、算法、创新创业、数理建模等多元方向，清晰分类。',
            arrowColor:'#52c41a',
            onClick: goLibrary,
            metric:'覆盖 8 大方向'
          },
          {
            icon: <ThunderboltOutlined style={{ color:'#fff', fontSize:20 }} />,
            gradient:'linear-gradient(135deg,#fa8c16,#ffa940)',
            title:'管理参赛计划',
            desc:'一键收藏心仪竞赛，跟踪备赛进度与截止日期，让你的竞赛之路有条不紊。',
            arrowColor:'#fa8c16',
            onClick: goMine,
            metric:'全程进度追踪'
          },
        ].map((item, i) => (
          <Col xs={24} md={8} key={i}>
            <Card
              hoverable
              style={{ ...CARD_STYLE, height:'100%', cursor: 'pointer' }}
              bodyStyle={{ padding:'24px', height:'100%' }}
              onClick={item.onClick}
            >
              <div style={{ display:'flex', flexDirection:'column', height:'100%' }}>
                <div style={{ display:'flex', alignItems:'center', gap:14, marginBottom:12 }}>
                  <div style={{ width:44, height:44, borderRadius:12, background: item.gradient, display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0, boxShadow:'0 4px 12px rgba(0,0,0,0.08)' }}>
                    {item.icon}
                  </div>
                  <div style={{ flex:1 }}>
                    <Typography.Text strong style={{ fontSize:15, display:'block', marginBottom:2 }}>{item.title}</Typography.Text>
                    <Tag style={{ borderRadius:4, fontSize:11, padding:'0 8px', lineHeight:'20px', border:'none', background: item.arrowColor + '20', color: item.arrowColor, margin:0 }}>{item.metric}</Tag>
                  </div>
                  <ArrowRightOutlined style={{ color: item.arrowColor, fontSize:14, flexShrink:0 }} />
                </div>
                <Typography.Text type='secondary' style={{ fontSize:13, lineHeight:1.6, flex:1 }}>{item.desc}</Typography.Text>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* ===== 热门竞赛 ===== */}
      <div style={SEC_GAP}>
        <SectionHeader
          icon={<FireOutlined style={{ color: designTokens.colorPrimary, fontSize:18 }} />}
          title='热门竞赛'
          sub='当前推荐赛事，AI 将根据你的背景自动匹配'
        />
                <Row gutter={[designTokens.spacing.lg, designTokens.spacing.md]}>
          {hot.map(item => (
            <Col xs={24} md={8} key={item.id}>
              <CompetitionCard
                competition={item}
                showActions={true}
                joined={isJoined(item.id)}
                onAdd={() => {
                  addCompetition(item);
                  message.success('✓ 已加入「' + item.name.slice(0, 16) + '…」');
                }}
              />
            </Col>
          ))}
        </Row>
      </div>

      {/* ===== 页脚 ===== */}
      <div style={{ borderTop:'1px solid rgba(15,23,42,0.06)', paddingTop: designTokens.spacing.xxl, paddingBottom: designTokens.spacing.xl, display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:12 }}>
        <Space size={12} align="center">
          <div style={{ width:32, height:32, borderRadius:8, background:'linear-gradient(135deg, ' + designTokens.colorPrimary + ', #4096ff)', display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontSize:16 }}>
            <RobotOutlined />
          </div>
          <div>
            <Typography.Text strong style={{ fontSize:14, display:'block' }}>赛智通</Typography.Text>
            <Typography.Text type='secondary' style={{ fontSize:12 }}>基于 AI 的大学生竞赛规划平台</Typography.Text>
          </div>
        </Space>
        <Space size={20}>
          <Typography.Link style={{ fontSize:13, color: designTokens.colorTextSecondary }}>首页</Typography.Link>
          <Typography.Link style={{ fontSize:13, color: designTokens.colorTextSecondary }} onClick={goAI}>AI推荐</Typography.Link>
          <Typography.Link style={{ fontSize:13, color: designTokens.colorTextSecondary }} onClick={goMine}>我的竞赛</Typography.Link>
        </Space>
      </div>

    </div>
  );
}
