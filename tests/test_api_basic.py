from fastapi.testclient import TestClient
from app import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "ok"
    assert "model_loaded" in data
    assert "device" in data


def test_version():
    response = client.get("/version")
    assert response.status_code == 200

    data = response.json()
    assert data["app_name"] == "medical-ai-segmentation-platform"
    assert "version" in data


def test_predict_without_model_should_return_503():
    response = client.post("/predict")
    assert response.status_code in [422, 503]


def test_agent_chat_without_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    response = client.post("/api/agent/chat", json={"message": "解释一下 Dice 指标"})
    assert response.status_code == 200

    data = response.json()
    assert "answer" in data
    assert data["configured"] is False


def test_case_upload_persists_to_repository():
    response = client.post(
        "/api/cases/upload",
        files={"files": ("slice.png", b"not-a-real-image-yet", "image/png")},
        data={"modality": "CT", "body_part": "肝脏"},
    )
    assert response.status_code == 200
    created = response.json()
    assert created["case_id"].startswith("CASE-")
    assert created["status"] == "uploaded"
    assert created["file_count"] == 1
    assert created["object_keys"][0].startswith("cases/")

    list_response = client.get("/api/cases")
    assert list_response.status_code == 200
    assert any(item["case_id"] == created["case_id"] for item in list_response.json())


def test_create_segmentation_for_missing_case_returns_404():
    response = client.post(
        "/api/v1/segmentations",
        json={"case_id": "CASE-NOT-FOUND", "model_name": "Seg-Model v2.0", "threshold": 0.5},
    )
    assert response.status_code == 404
