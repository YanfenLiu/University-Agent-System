import json
from pathlib import Path
from unittest.mock import patch

from agents.info_collect_agent import InfoCollectAgent
from agents.info_collect.registry import SourceRegistry
from agents.main_agent import MainAgent


REQUIRED_OUTPUT_FIELDS = {
    "task_id", "agent_name", "status", "data", "message",
    "error", "next_action", "metadata",
}


def build_input(**business_overrides):
    business = {"sources": [], "keywords": [], **business_overrides}
    return {
        "task_id": "collect_test_001",
        "user_input": "查找人工智能竞赛",
        "task_type": "info_collect",
        "user_profile": {"interests": ["人工智能"]},
        "context": {},
        "input_data": business,
        "history": [],
        "required_output": "json",
        "metadata": {},
    }


def test_output_schema_on_need_input():
    result = InfoCollectAgent(config={}).run(build_input())
    assert REQUIRED_OUTPUT_FIELDS <= result.keys()
    assert result["status"] == "need_input"
    assert result["agent_name"] == "info_collect_agent"


def test_invalid_source_is_caught():
    result = InfoCollectAgent(config={}).run(
        build_input(sources=["not_a_real_source"], keywords=["test"])
    )
    assert result["status"] == "failed"
    assert isinstance(result["error"], dict)


def test_registry_has_all_five_web_sources():
    """验证 SourceRegistry 包含全部 5 个 web 数据源。"""
    sources = SourceRegistry.list_all()
    assert "saikr" in sources
    assert "52jingsai" in sources
    assert "ali_tianchi" in sources
    assert "heywhale" in sources
    assert "datafountain" in sources
    assert len(sources) == 5


def test_registry_get_unknown_returns_none():
    """未注册的数据源应返回 None。"""
    assert SourceRegistry.get("nonexistent") is None


def test_local_txt_file_is_parsed(tmp_path: Path):
    notice = tmp_path / "test_notice.txt"
    notice.write_text("温州大学人工智能竞赛报名通知", encoding="utf-8")
    config = {"storage": {"raw_data_path": str(tmp_path / "raw")}}
    result = InfoCollectAgent(config=config).run(
        build_input(sources=["local_file"], file_paths=[str(notice)])
    )

    assert result["status"] == "success"
    assert len(result["data"]["raw_items"]) == 1
    item = result["data"]["raw_items"][0]
    assert item["source"] == "local_file"
    assert item["file_type"] == ".txt"
    assert "温州大学" in item["raw_text"]


def test_main_agent_adapts_saikr_web_input():
    main_agent = MainAgent(config={})
    original = build_input(
        sources=[], data_source="web", source_url="https://www.saikr.com/"
    )
    adapted = main_agent._adapt_info_collect_input(original)

    # 现在默认爬取所有注册的 web 数据源
    from agents.info_collect.registry import SourceRegistry
    all_sources = SourceRegistry.list_all()
    assert sorted(adapted["sources"]) == sorted(all_sources)
    # keywords 按用户输入为准，不自动填充
    assert adapted["keywords"] == []


def test_main_agent_does_not_mislabel_unknown_websites():
    main_agent = MainAgent(config={})
    original = build_input(
        sources=[], data_source="web", source_url="https://example.com/competition"
    )
    adapted = main_agent._adapt_info_collect_input(original)

    # 现在 data_source="web" 默认爬全部注册的 web 源，不依赖 URL
    from agents.info_collect.registry import SourceRegistry
    assert len(adapted["sources"]) >= 1
    assert all(s in SourceRegistry.list_all() for s in adapted["sources"] if s != "local_file")


def test_main_agent_runs_local_collection_end_to_end(tmp_path: Path):
    notice = tmp_path / "main_agent_notice.txt"
    notice.write_text("温州大学程序设计竞赛通知", encoding="utf-8")
    main_agent = MainAgent(
        config={"storage": {"raw_data_path": str(tmp_path / "main_raw")}}
    )
    original = build_input(
        sources=["local_file"],
        file_paths=[str(notice)],
    )

    result = main_agent.run(original)

    assert result["status"] == "success"
    agent_result = result["data"]["agent_results"][0]
    assert agent_result["agent_name"] == "info_collect_agent"
    assert agent_result["status"] == "success"
    assert "温州大学" in agent_result["data"]["raw_items"][0]["raw_text"]


# ---- Parser 单元测试 ----


def test_saikr_parser_parse_list_json():
    from agents.info_collect.parsers.saikr import SaikrParser
    parser = SaikrParser({})
    api_response = {
        "list": [
            {
                "contest_name": "测试数学建模大赛",
                "contest_url": "/vse/12345",
                "organiser_name": "教育部",
                "regist_start_time": "1700000000",
                "contest_class_second_id": "1",
                "level_name": "国家级",
            }
        ]
    }
    result = parser.parse_list(api_response)
    assert len(result) == 1
    assert result[0]["title"] == "测试数学建模大赛"
    assert result[0]["source"] == "saikr"
    assert "12345" in result[0]["url"]


def test_saikr_parser_parse_detail():
    from agents.info_collect.parsers.saikr import SaikrParser
    parser = SaikrParser({})
    detail = {
        "content": "<p>本竞赛旨在培养学生创新能力</p>",
        "organiser": [{"organizer": "教育部"}],
        "other_organiser": [],
        "sup_organizer": [],
        "regist_start_time": "2026-03-01 10:00:00",
        "regist_end_time": "2026-05-01 18:00:00",
        "attachment": [],
        "contest_stage": {"初赛": "2026-06-01", "决赛": "2026-08-01"},
    }
    result = parser.parse_detail(detail)
    assert "培养学生创新能力" in result["description"]
    assert "教育部" in result["organizer"]
    assert result["regist_start"] == "2026-03-01"
    assert result["regist_end"] == "2026-05-01"
    assert len(result["contest_stage"]) == 2


def test_jingsai52_parser_json_list():
    from agents.info_collect.parsers.jingsai52 import Jingsai52Parser
    parser = Jingsai52Parser({})
    api_response = {
        "data": {
            "list": [
                {
                    "title": "全国大学生英语竞赛",
                    "url": "/competition/100",
                    "publish_date": "2026-03-01",
                    "organizer": "外语教学指导委员会",
                }
            ]
        }
    }
    result = parser.parse_list(api_response)
    assert len(result) == 1
    assert result[0]["title"] == "全国大学生英语竞赛"
    assert result[0]["source"] == "52jingsai"
    assert "52jingsai.com" in result[0]["url"]


def test_jingsai52_parser_html_list():
    from agents.info_collect.parsers.jingsai52 import Jingsai52Parser
    parser = Jingsai52Parser({})
    # 模拟 /bisai/ 页面实际的 dl.bbda.list_bbda 结构
    html = """
    <dl class="bbda list_bbda cl">
        <dt class="xs2_tit">
            <a class="xi2" href="article-23901-1.html">全国大学生数学竞赛报名通知</a>
        </dt>
        <dd class="xs2 cl">
            竞赛官网：www.test.com || 报名时间：即日起至8月6日 || 主办单位：教育部
            <div class="list_info">分类:<label><a>学科技能</a></label>2026-08-01 12:00</div>
        </dd>
    </dl>
    <dl class="bbda list_bbda cl">
        <dt class="xs2_tit">
            <a class="xi2" href="article-23900-1.html">“挑战杯”创新创业大赛</a>
        </dt>
        <dd class="xs2 cl">
            摘要内容 || 截止时间：2026-12-31 || 主办方：团中央
            <div class="list_info">分类:<label><a>创业大赛</a></label>2026-06-01 10:00</div>
        </dd>
    </dl>
    """
    result = parser.parse_list(html)
    assert len(result) == 2
    assert result[0]["title"] == "全国大学生数学竞赛报名通知"
    assert result[0]["source"] == "52jingsai"
    assert result[0]["category"] == "学科技能"
    assert result[0]["organizer"] == "教育部"
    assert result[0]["regist_end"] == "2026-08-06"
    assert result[1]["organizer"] == "团中央"
    assert result[1]["regist_end"] == "2026-12-31"


def test_tianchi_parser_json_list():
    from agents.info_collect.parsers.tianchi import TianchiParser
    parser = TianchiParser({})
    # 天池实际 API 格式: {data: {list: [{raceId, name, isSeries, raceStartTime, ...}]}}
    api_response = {
        "data": {
            "list": [
                {
                    "raceId": 532503,
                    "name": "天池大数据挑战赛",
                    "isSeries": 0,
                    "raceStartTime": "2026-03-15 00:00:00",
                    "raceEndTime": "2026-08-30 00:00:00",
                    "signupEndTime": "2026-07-31 00:00:00",
                    "introduction": "阿里云天池经典赛事",
                    "bonus": 500000,
                    "teamCount": 2000,
                    "tagsList": [
                        {"tagNameCn": "数据分析", "tagId": 1},
                        {"tagNameCn": "机器学习", "tagId": 2},
                    ],
                    "visualTab": 1,
                }
            ]
        }
    }
    result = parser.parse_list(api_response)
    assert len(result) == 1
    assert result[0]["title"] == "天池大数据挑战赛"
    assert result[0]["source"] == "ali_tianchi"
    assert result[0]["publish_date"] == "2026-03-15"
    assert result[0]["regist_end"] == "2026-07-31"
    assert result[0]["category"] == "数据分析, 机器学习"
    assert result[0]["bonus"] == 500000


def test_tianchi_series_race_expand():
    from agents.info_collect.parsers.tianchi import TianchiParser
    parser = TianchiParser({})
    # 系列赛展开为子赛道
    api_response = {
        "data": {
            "list": [
                {
                    "raceId": 38,
                    "name": "系列赛主标题",
                    "isSeries": 1,
                    "raceStartTime": "2026-07-17 00:00:00",
                    "raceEndTime": "2026-10-27 00:00:00",
                    "bonus": 200000,
                    "tagsList": [{"tagNameCn": "多模态"}],
                    "visualTab": 1,
                    "trackList": [
                        {"raceId": 532503, "name": "子赛道1", "signupEndTime": "2026-10-20 00:00:00", "introduction": "子赛道1描述"},
                        {"raceId": 532504, "name": "子赛道2", "signupEndTime": "2026-10-20 00:00:00", "introduction": ""},
                    ]
                }
            ]
        }
    }
    result = parser.parse_list(api_response)
    assert len(result) == 2
    assert result[0]["title"] == "系列赛主标题 - 子赛道1"
    assert result[1]["title"] == "系列赛主标题 - 子赛道2"
    assert result[0]["regist_end"] == "2026-10-20"
    assert result[0]["description"] == "子赛道1描述"


def test_heywhale_parser_json_list():
    from agents.info_collect.parsers.heywhale import HeywhaleParser
    parser = HeywhaleParser({})
    # 和鲸实际 API 格式: {"data": [{_id, Name, StartDate, EndDate, DetailType, ...}, ...]}
    api_response = {
        "totalNum": 2,
        "data": [
            {
                "_id": "69c0dfa34f302f8f0122e1bb",
                "Name": "和鲸大数据挑战赛",
                "StartDate": "2026-03-26T02:00:00.000Z",
                "EndDate": "2026-09-29T16:00:00.000Z",
                "RegisterEndDate": "2026-07-15T04:00:00.000Z",
                "DetailType": "ALGORITHM",
                "ShortDescription": "大数据挑战赛",
                "UsersNumber": 5457,
                "TeamsNumber": 3393,
            }
        ]
    }
    result = parser.parse_list(api_response)
    assert len(result) == 1
    assert result[0]["title"] == "和鲸大数据挑战赛"
    assert result[0]["source"] == "heywhale"
    assert result[0]["regist_end"] == "2026-07-15"
    assert result[0]["category"] == "算法赛"


def test_datafountain_parser_json_list():
    from agents.info_collect.parsers.datafountain import DatafountainParser
    parser = DatafountainParser({})
    # 使用 DataFountain 实际 API 格式: {"cmpt": {"competitions": [...]}}
    # DF 实际 API 格式: {cmpt: {competitions: [{id, title, start/endTime,
    #   organizers: [{name, roleName}], tags: [{nameCn}], typeLabel, ...}]}}
    api_response = {
        "cmpt": {
            "competitions": [
                {
                    "id": 800,
                    "title": "DF数据挖掘大赛",
                    "subTitle": "赛题描述",
                    "startTime": "2026-03-01T00:00:00.000Z",
                    "endTime": "2026-06-01T00:00:00.000Z",
                    "orderTime": "2026-03-01T00:00:00.000Z",
                    "tags": [{"nameCn": "数据挖掘"}, {"nameCn": "AI"}],
                    "typeLabel": "智能算法",
                    "organizers": [{"name": "中国计算机学会", "roleName": "主办单位"}],
                    "race": {"startTime": "2026-04-01T00:00:00.000Z", "endTime": "2026-07-01T00:00:00.000Z"},
                    "reward": "100000",
                    "teams": 500,
                    "users": 1200,
                }
            ]
        }
    }
    result = parser.parse_list(api_response)
    assert len(result) == 1
    assert result[0]["title"] == "DF数据挖掘大赛"
    assert result[0]["source"] == "datafountain"
    assert result[0]["publish_date"] == "2026-03-01"
    assert result[0]["regist_end"] == "2026-06-01"
    assert result[0]["contest_start"] == "2026-04-01"
    assert result[0]["category"] == "智能算法, 数据挖掘, AI"
    assert result[0]["organizer"] == "中国计算机学会"
    assert result[0]["organizer_list"] == ["中国计算机学会"]
    assert result[0]["reward"] == "100000"
    assert "datafountain.cn/competitions/800" in result[0]["url"]


def test_new_parsers_handle_empty_data():
    """所有 parser 应对空数据返回空列表或空字段 dict。"""
    from agents.info_collect.parsers.jingsai52 import Jingsai52Parser
    from agents.info_collect.parsers.tianchi import TianchiParser
    from agents.info_collect.parsers.heywhale import HeywhaleParser
    from agents.info_collect.parsers.datafountain import DatafountainParser

    for ParserClass in [Jingsai52Parser, TianchiParser, HeywhaleParser, DatafountainParser]:
        parser = ParserClass({})
        assert parser.parse_list({}) == []
        assert parser.parse_list("") == []
        detail = parser.parse_detail({})
        assert isinstance(detail, dict)
        # detail 应返回标准字段的 dict（值可能为空或默认值）
        assert "description" in detail
        assert "organizer" in detail
        assert "attachments" in detail


def test_datafountain_parser_detail():
    from agents.info_collect.parsers.datafountain import DatafountainParser
    parser = DatafountainParser({})
    detail = {
        "id": 1169,
        "title": "AI人才-星探计划",
        "cmptDescription": "<p>本竞赛旨在发现AI人才</p>",
        "cmptDataDescription": "**附录**\\n\\n提交要求...",
        "startTime": "2026-04-06T16:00:00.000Z",
        "endTime": "2026-08-31T15:59:59.000Z",
        "reward": "¥90,000",
        "totalBonus": 90000,
        "organizers": [{"name": "烟台睿创微纳技术股份有限公司", "roleName": "主办单位"}],
        "schedules": [
            {"title": "第一阶段", "startTime": "2026-04-07T00:00:00+08:00", "endTime": "2026-06-10T23:59:59+08:00"},
            {"title": "第二阶段", "startTime": "2026-06-20T00:00:00+08:00", "endTime": "2026-08-20T23:59:59+08:00"},
        ],
    }
    result = parser.parse_detail(detail)
    assert "发现AI人才" in result["description"]
    assert "附录" in result["description"]  # cmptDataDescription merged in
    assert result["regist_start"] == "2026-04-06"
    assert result["organizer"] == "烟台睿创微纳技术股份有限公司"
    assert result["reward"] == "¥90,000"
    assert len(result["stages"]) == 2

    # merge_detail should NOT overwrite list values
    list_item = {"description": "简短摘要", "organizer": "列表中的主办方", "regist_end": "2026-08-31"}
    merged = parser.merge_detail(list_item, result)
    assert merged["description"] == result["description"]  # detail更完整，替换
    assert merged["organizer"] == "列表中的主办方"  # 列表已有，不覆盖
    assert merged["regist_end"] == "2026-08-31"  # 列表已有，不覆盖


def test_base_client_has_retry_config():
    """BaseSourceClient 默认应有重试配置。"""
    from agents.info_collect.clients.base import BaseSourceClient

    class TestClient(BaseSourceClient):
        def get_contests(self, page=1, limit=20):
            return {}
        def get_contest_detail(self, contest_id):
            return {}

    client = TestClient(timeout=5)
    assert client.max_retries == 3
    assert client.retry_backoff_base == 2.0
    assert client.timeout == 5
    # 验证 transport 能正常构建
    c = client.client  # 触发 lazy init
    assert c is not None
    client.close()


def test_source_registry_triggers_on_import():
    """验证 import info_collect_agent 即完成所有数据源注册。"""
    # SourceRegistry 应该已通过 info_collect.__init__ → parsers.__init__ 完成注册
    registered = SourceRegistry.list_all()
    assert len(registered) == 5, f"Expected 5 sources, got {len(registered)}: {registered}"
    for name in registered:
        spec = SourceRegistry.get(name)
        assert spec is not None
        assert spec.client_class is not None
        assert spec.parser_class is not None
