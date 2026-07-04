import json
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from agent.authority_retriever import CHUNKS_PATH, search_authority_pdf_chunks
from app import app


client = TestClient(app)


def test_source_registry_can_be_loaded():
    data = yaml.safe_load(Path("authority_knowledge/source_registry.yml").read_text(encoding="utf-8"))
    assert data["sources"]


def test_all_pdf_sources_have_required_fields():
    data = yaml.safe_load(Path("authority_knowledge/source_registry.yml").read_text(encoding="utf-8"))
    required = {"id", "filename", "title", "source_url", "pdf_url", "publisher", "authority_level", "allowed_for_rag"}
    for source in data["sources"]:
        assert required.issubset(source.keys())


def test_authority_status_handles_missing_pdfs():
    response = client.get("/api/agent/authority/status")
    assert response.status_code == 200
    data = response.json()
    assert {"registered_sources", "available_pdfs", "missing_pdfs", "indexed_chunks", "manifest_path"}.issubset(data.keys())
    assert isinstance(data["missing_pdfs"], list)


def test_search_authority_pdf_chunks_filters_min_level():
    original = CHUNKS_PATH.read_text(encoding="utf-8") if CHUNKS_PATH.exists() else None
    CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    chunks = [
        {
            "chunk_id": "high-1",
            "source_id": "metrics_3d_segmentation_taha_2015",
            "title": "Metrics for evaluating 3D medical image segmentation",
            "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC4533825/",
            "pdf_url": "https://example.test/high.pdf",
            "publisher": "BMC Medical Imaging / PMC",
            "source_type": "peer_reviewed_open_access_paper",
            "authority_level": 5,
            "allowed_for_rag": True,
            "domain": ["segmentation_metrics"],
            "page_start": 3,
            "page_end": 3,
            "section_title": "Dice",
            "preview": "Dice and Hausdorff metrics for segmentation evaluation.",
            "text": "Dice and Hausdorff metrics for segmentation evaluation.",
            "organ_tags": [],
            "metric_tags": ["dice", "hd95"],
            "task_tags": ["segmentation"],
        },
        {
            "chunk_id": "low-1",
            "source_id": "low_source",
            "title": "Low Source",
            "source_url": "https://example.test/low",
            "pdf_url": "https://example.test/low.pdf",
            "publisher": "Example",
            "source_type": "research_paper_or_preprint",
            "authority_level": 3,
            "allowed_for_rag": True,
            "domain": ["benchmark"],
            "page_start": 1,
            "page_end": 1,
            "section_title": "Benchmark",
            "preview": "Abdominal segmentation benchmark.",
            "text": "Abdominal segmentation benchmark.",
            "organ_tags": [],
            "metric_tags": [],
            "task_tags": ["segmentation"],
        },
    ]
    CHUNKS_PATH.write_text("\n".join(json.dumps(item) for item in chunks), encoding="utf-8")
    try:
        results = search_authority_pdf_chunks("Dice HD95 segmentation", min_authority_level=4)
        assert results
        assert all(item["authority_level"] >= 4 for item in results)
        assert {"source_url", "pdf_url", "page_start", "page_end", "preview"}.issubset(results[0].keys())
    finally:
        if original is None:
            CHUNKS_PATH.unlink(missing_ok=True)
        else:
            CHUNKS_PATH.write_text(original, encoding="utf-8")


def test_segmentation_analyze_without_llm_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    payload = {
        "message": "请结合本地权威 PDF 知识库分析这张切片的分割结果，并生成科研汇报",
        "segmentation_result": {
            "status": "success",
            "model_name": "MMRSG-UNet epoch_241.pth",
            "results": [
                {
                    "filename": "case0003_slice_124_img.png",
                    "metrics": [
                        {"organ": "肝脏", "pixel_count": 1200, "percentage": "12.00%"},
                        {"organ": "脾脏", "pixel_count": 200, "percentage": "2.00%"},
                    ],
                }
            ],
        },
        "top_k": 8,
        "authority_only": True,
        "min_authority_level": 4,
    }
    response = client.post("/api/agent/segmentation/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert {"answer", "citations", "segmentation_facts", "authority_context"}.issubset(data.keys())
    assert "科研辅助" in data["answer"] or "不代表临床诊断" in data["answer"]
    forbidden = ["诊断为", "患有", "治疗建议", "临床结论"]
    assert not any(term in data["answer"] for term in forbidden)
    if not data["citations"]:
        assert "本地权威 PDF 知识库证据不足" in data["answer"]
