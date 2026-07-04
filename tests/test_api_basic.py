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
