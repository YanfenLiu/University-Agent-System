from api import (
    _context_recommendations,
    _material_project_info,
    _resolve_api_task_type,
    _select_context_recommendation,
)


def test_pages_full_process_defaults_to_recommendation():
    assert _resolve_api_task_type("full_process", "推荐几个AI比赛", None) == "recommendation"


def test_material_request_does_not_run_full_process_again():
    assert (
        _resolve_api_task_type(
            "full_process",
            "能否帮我生成AI推荐的材料呢？",
            {"intent": "material"},
        )
        == "material"
    )


def test_material_keyword_fallback_works_without_llm():
    assert _resolve_api_task_type("full_process", "帮我写申报书", None) == "material"


def test_prior_recommendation_can_be_selected_by_ordinal():
    recommendations = [
        {"name": "人工智能挑战赛", "officialUrl": "https://example.com/1"},
        {"name": "数学建模竞赛", "officialUrl": "https://example.com/2"},
    ]
    selected = _select_context_recommendation("给第二个生成材料", recommendations)
    assert selected == recommendations[1]


def test_prior_recommendation_can_be_selected_by_title():
    recommendations = [
        {"name": "人工智能挑战赛"},
        {"name": "数学建模竞赛"},
    ]
    selected = _select_context_recommendation("为数学建模竞赛准备材料", recommendations)
    assert selected == recommendations[1]


def test_pages_recommendation_shape_maps_to_material_project():
    project = _material_project_info(
        {
            "name": "人工智能挑战赛",
            "summary": "面向高校学生",
            "officialUrl": "https://example.com",
        }
    )
    assert project["title"] == "人工智能挑战赛"
    assert project["source_url"] == "https://example.com"


def test_invalid_context_recommendations_are_ignored():
    context = {"last_recommendations": ["bad", {"name": "有效竞赛"}]}
    assert _context_recommendations(context) == [{"name": "有效竞赛"}]
