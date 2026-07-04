# Medical AI Segmentation Platform

This project packages an MMRSG-UNet medical image segmentation model into a FastAPI-based AI platform demo.

## DevOps & Quality Highlights

- FastAPI inference API with frontend upload workflow.
- `/health` endpoint for operational readiness checks.
- `/version` endpoint for release tracking.
- Configurable model path through `MODEL_PATH`.
- UAT checklist for acceptance testing.
- Pytest regression tests for core API behavior.
- GitHub Actions CI quality gate.
- Dockerfile for containerized deployment.
- Runbook for common production and support issues.

## Why this project matters

The goal is not only to make the AI model runnable, but also to make the platform testable, maintainable, observable, and ready for release validation.

## Local-PDF Authority RAG

The platform includes a MedResearch-Agent that generates research-assistance analysis from two evidence sources only:

- real `/predict` segmentation output facts, including overlay, organ names, `pixel_count`, and `percentage`;
- local authority PDFs that the user manually places under `authority_knowledge/pdfs/` or the existing `知识库书籍/` directory.

The program does not search the web, download medical material, or treat webpage summaries as authoritative evidence. The knowledge pipeline is explicit:

1. `authority_knowledge/pdfs/*.pdf` contains the original authority PDFs manually provided by the user.
2. `authority_knowledge/chunks/authority_chunks.jsonl` is only a chunk backup/intermediate file, not the formal vector knowledge base.
3. `data/chroma_db/` is the formal ChromaDB vector knowledge base.
4. `scripts/ingest_local_authority_pdfs.py` runs PDF parsing, chunking, JSONL backup writing, offline embedding, and ChromaDB persistence.
5. Agent retrieval uses ChromaDB first and falls back to JSONL keyword retrieval only when ChromaDB, embedding, or `data/chroma_db/` is unavailable.

Each answer cites PDF chunk metadata: title, publisher, `source_url`, `page_start`, and `page_end`. If no local PDF evidence is retrieved, the Agent explicitly states that the local authority PDF knowledge base has insufficient evidence and only describes model-output facts.

Safety boundary: the Agent does not provide clinical diagnosis, treatment advice, or clinical conclusions. Every report includes:

> 本结果仅用于科研辅助分析和模型输出解释，不代表临床诊断或治疗建议。

### PDF Download Checklist

Place these PDFs manually in `authority_knowledge/pdfs/`. This project also supports the current local directory `知识库书籍/` through `local_filenames` in `authority_knowledge/source_registry.yml`.

- `idkd_abdomen_pelvis_2018_2021.pdf`
- `idkd_abdomen_pelvis_2023_2026.pdf`
- `medical_segmentation_decathlon.pdf`
- `metrics_3d_medical_image_segmentation_taha_2015.pdf`
- `guideline_segmentation_metrics_mueller_2022.pdf`
- `totalsegmentator_ct_segmentation.pdf`
- `amos_abdominal_multi_organ_segmentation.pdf`
- `word_abdominal_organ_segmentation.pdf`

### Authority Knowledge Commands

```bash
python scripts/ingest_local_authority_pdfs.py
uvicorn app:app --reload
cd frontend && npm run dev
```

`authority_knowledge/pdfs/*.pdf`, `authority_knowledge/chunks/*.jsonl`, `authority_knowledge/manifest.json`, and `data/chroma_db/` are ignored by Git. `authority_knowledge/source_registry.yml` remains tracked as the auditable source list.

### Authority Agent APIs

- `GET /api/agent/authority/status`
- `POST /api/agent/authority/reindex`
- `POST /api/agent/segmentation/analyze`

Example request:

```json
{
  "message": "请结合本地权威 PDF 知识库分析这张切片的分割结果，并生成科研汇报",
  "segmentation_result": {
    "status": "success",
    "model_name": "MMRSG-UNet epoch_241.pth",
    "results": [
      {
        "filename": "case0003_slice_124_img.png",
        "metrics": [
          {"organ": "肝脏", "pixel_count": 1200, "percentage": "12.00%"}
        ]
      }
    ]
  },
  "top_k": 8,
  "authority_only": true,
  "min_authority_level": 4
}
```

### Demo Flow

1. Open the segmentation workbench.
2. Upload `case0003_slice_124_img.png` or another PNG/JPG slice.
3. Run `/predict` from the UI and get the real MMRSG-UNet output.
4. Click “结合本地权威 PDF 知识库分析”.
5. The Research Agent combines organ pixel percentages with local PDF citations and generates a research report.
