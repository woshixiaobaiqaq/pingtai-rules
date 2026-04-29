from __future__ import annotations


def test_web_homepage_is_available(client) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "全平台规则库" in response.text
    assert "Platform Content Audit" in response.text
    assert "小红书" in response.text
    assert "上传文档" in response.text
    assert "document-input" in response.text


def test_audit_api_returns_structured_json(client) -> None:
    response = client.post(
        "/api/audit",
        json={
            "content": "这个方法保证你7天回本，评论区留言领取资料。",
            "platforms": ["抖音"],
            "persist": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "report" in payload
    assert payload["report"]["task"]["status"] == "completed"
    assert payload["report"]["platform_results"][0]["platform"] == "douyin"
    assert isinstance(payload["report"]["platform_results"][0]["rewrite_options"], dict)


def test_rules_endpoints_return_structured_json(client) -> None:
    list_response = client.get("/api/rules")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["items"][0]["rule_id"] == "DY-001"

    import_response = client.post(
        "/api/rules/import",
        json={
            "rules": [
                {
                    "platform": "douyin",
                    "rule_id": "DY-001",
                    "title": "禁止绝对化收益承诺",
                    "content": "不得使用保证收益、稳赚不赔等表达。",
                    "severity": "high",
                    "tags": ["financial_promise"],
                    "keywords": ["保证收益"],
                    "regex_patterns": ["\\d+天回本"],
                    "metadata": {},
                }
            ]
        },
    )
    assert import_response.status_code == 200
    import_payload = import_response.json()
    assert import_payload["inserted"] == 1
    assert import_payload["items"][0]["platform"] == "douyin"
