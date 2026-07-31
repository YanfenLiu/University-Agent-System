import { Table, Typography, Tag, Button, message, Result, Spin } from 'antd';

import { useCompetitions } from '../contexts/CompetitionsContext';
import { useAuth } from '../contexts/AuthContext';

export function MyCompetitions() {
  const { myCompetitions, removeCompetition, loading } = useCompetitions();
  const { user } = useAuth();

  const handleRemove = (id: number) => {
    removeCompetition(id);
    message.success('已移除该竞赛');
  };

  if (!user) {
    return (
      <Result
        status="info"
        title="我的竞赛"
        subTitle="登录后可查看和同步你的竞赛收藏"
      />
    );
  }

  if (loading) {
    return <Spin size="large" style={{ display: 'block', margin: '80px auto' }} />;
  }

  return (
    <>
      <Typography.Title level={3}>我的竞赛</Typography.Title>
      <Typography.Paragraph>
        查看你已经加入的竞赛，管理报名时间和备赛计划。
      </Typography.Paragraph>

      <Table
        rowKey="id"
        dataSource={myCompetitions}
        locale={{ emptyText: '你还没有加入任何竞赛' }}
        columns={[
          { title: '竞赛名称', dataIndex: 'name' },
          {
            title: '难度',
            dataIndex: 'difficulty',
            render: (difficulty: string) => <Tag>{difficulty}</Tag>,
          },
          {
            title: '状态',
            dataIndex: 'status',
            render: (status: string) => <Tag color="blue">{status}</Tag>,
          },
          { title: '截止时间', dataIndex: 'deadline' },
          {
            title: '操作',
            render: (_: unknown, record: any) => (
              <div style={{ display: 'flex', gap: 8 }}>
                <Button
                  href={record.officialUrl}
                  target="_blank"
                  size="small"
                  style={{ borderRadius: 8 }}
                >
                  查看详情
                </Button>
                <Button
                  danger
                  size="small"
                  style={{ borderRadius: 8 }}
                  onClick={() => handleRemove(record.id)}
                >
                  移除竞赛
                </Button>
              </div>
            ),
          },
        ]}
      />
    </>
  );
}
