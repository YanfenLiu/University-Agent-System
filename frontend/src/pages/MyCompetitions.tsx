import { Table, Typography, Tag, Button, message } from 'antd';

import { useCompetitions } from '../contexts/CompetitionsContext';


export function MyCompetitions() {

  const { myCompetitions, removeCompetition } = useCompetitions();

  const handleRemove = (id: number) => {
    removeCompetition(id);
    message.success('已移除该竞赛');
  };





  return (

    <>

      <Typography.Title level={3}>
        我的竞赛
      </Typography.Title>



      <Typography.Paragraph>

        查看你已经加入的竞赛，管理报名时间和备赛计划。

      </Typography.Paragraph>





      <Table

        rowKey="id"

        dataSource={myCompetitions}


        locale={{
          emptyText:'你还没有加入任何竞赛'
        }}



        columns={[



          {
            title:'竞赛名称',
            dataIndex:'name',
          },



          {
            title:'难度',
            dataIndex:'difficulty',

            render:(difficulty)=>(

              <Tag>
                {difficulty}
              </Tag>

            )

          },




          {
            title:'状态',
            dataIndex:'status',

            render:(status)=>(

              <Tag color="blue">
                {status}
              </Tag>

            )

          },




          {
            title:'截止时间',
            dataIndex:'deadline',
          },





          {
            title:'AI推荐理由',
            dataIndex:'reason',
          },





                    {
            title:'操作',
            render:(_,record)=>(
              <div style={{ display:'flex', gap:8 }}>
                <Button
                  href={record.officialUrl}
                  target="_blank"
                  size="small"
                  style={{ borderRadius:8 }}
                >
                  查看详情
                </Button>
                <Button
                  danger
                  size="small"
                  style={{ borderRadius:8 }}
                  onClick={() => handleRemove(record.id)}
                >
                  移除竞赛
                </Button>
              </div>
            )
          }


        ]}

      />


    </>

  );

}
