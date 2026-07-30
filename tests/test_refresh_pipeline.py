from types import SimpleNamespace
from datetime import datetime, timezone

import api
from agents.main_agent import MainAgent
from agents.refresh_service import RefreshService
from agents.info_collect.supabase_store import SupabaseStore


def test_recommendation_skips_collect_and_extract_without_raw_text():
    agent = MainAgent(config={})
    selected = agent.select_agents({
        "task_type": "recommendation",
        "user_input": "推荐人工智能竞赛",
        "input_data": {},
    })
    assert selected == ["recommendation"]


def test_recommendation_keeps_extract_for_pasted_notice():
    agent = MainAgent(config={})
    selected = agent.select_agents({
        "task_type": "recommendation",
        "user_input": "分析这份通知并判断是否适合我",
        "input_data": {"raw_text": "竞赛通知正文" * 20},
    })
    assert selected == ["info_extract", "recommendation"]


def test_refresh_service_extracts_only_changed_ids(monkeypatch):
    class FakeStorage:
        def __init__(self):
            self.updated = []
            self.saved = []

        def update_refresh_job(self, job_id, **values):
            self.updated.append((job_id, values))

        def get_full_items_by_ids(self, ids):
            return [
                {
                    "id": value,
                    "title": f"Competition {value}",
                    "url": f"https://example.com/{value}",
                    "source": "saikr",
                    "raw_text": "notice",
                    "organizer": "University",
                }
                for value in ids
            ]

        def save_extraction_result(self, record_id, structured, error=None):
            self.saved.append((record_id, structured, error))

        def delete_expired(self):
            return 2

    class FakeCrawlService:
        def __init__(self, _config):
            pass

        def crawl(self, **kwargs):
            source = kwargs["sources"][0]
            return {
                "status": "completed",
                "stats": {
                    "items_found": 3,
                    "items_new": 1 if source == "saikr" else 0,
                    "items_changed": 1 if source == "saikr" else 0,
                    "items_unchanged": 1,
                    "extraction_ids": [1, 2] if source == "saikr" else [],
                },
            }

    class FakeExtractor:
        def __init__(self, _config):
            pass

        def run(self, request):
            return {
                "status": "success",
                "data": {
                    "structured_items": [
                        {
                            "title": row["title"],
                            "source_url": row["url"],
                            "_source": row["source"],
                        }
                        for row in request["input_data"]["raw_items"]
                    ]
                },
            }

    monkeypatch.setattr("agents.refresh_service.CrawlService", FakeCrawlService)
    monkeypatch.setattr("agents.refresh_service.InfoExtractAgent", FakeExtractor)
    monkeypatch.setattr(
        "agents.refresh_service.SourceRegistry.list_all",
        lambda: ["saikr", "heywhale"],
    )

    service = RefreshService.__new__(RefreshService)
    service.config = {}
    service.storage = FakeStorage()
    result = service.run(job_id=7)

    assert result["status"] == "completed"
    assert result["items_new"] == 1
    assert result["items_changed"] == 1
    assert result["items_unchanged"] == 2
    assert result["items_extracted"] == 2
    assert result["items_deleted"] == 2
    assert [row[0] for row in service.storage.saved] == [1, 2]


def test_refresh_api_returns_existing_job_without_dispatch(monkeypatch):
    class FakeStore:
        def get_active_refresh_job(self):
            return {
                "id": 9,
                "status": "running",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }

    dispatched = []
    monkeypatch.setattr(api, "_refresh_store", lambda: FakeStore())
    monkeypatch.setattr(api, "_dispatch_refresh_workflow", dispatched.append)
    request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))

    result = api.start_competition_refresh(request)

    assert result.status == "already_running"
    assert result.job_id == 9
    assert dispatched == []


def test_local_embedding_is_disabled_by_default(monkeypatch):
    class FailingWorker:
        def compute(self, *_args, **_kwargs):
            raise AssertionError("the heavyweight worker must not start by default")

    monkeypatch.delenv("ENABLE_LOCAL_EMBEDDING", raising=False)
    store = SupabaseStore.__new__(SupabaseStore)
    store._embed_worker = FailingWorker()

    assert store._try_local_embedding([{"title": "AI competition"}], "AI") is None


def test_local_embedding_can_be_enabled_explicitly(monkeypatch):
    class FakeWorker:
        def compute(self, *_args, **_kwargs):
            return [88.0]

    monkeypatch.setenv("ENABLE_LOCAL_EMBEDDING", "true")
    store = SupabaseStore.__new__(SupabaseStore)
    store._embed_worker = FakeWorker()

    assert store._try_local_embedding([{"title": "AI competition"}], "AI") == [88.0]
