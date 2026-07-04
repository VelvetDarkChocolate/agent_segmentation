# MedResearch-Agent

## Local-PDF Authority RAG Design

MedResearch-Agent is a Local-PDF Authority Segmentation-Grounded RAG Agent. It uses two evidence channels only:

1. `/predict` model output facts, including filename, organ name, `pixel_count`, and `percentage`.
2. Local PDF chunks parsed from files registered in `authority_knowledge/source_registry.yml`.

Codex and the application must not search the web for medical material, scrape webpage summaries, or use self-written medical notes as authoritative evidence. The user manually places PDF files under `authority_knowledge/pdfs/`; this project also supports the current `知识库书籍/` directory.

## Source Registry

`authority_knowledge/source_registry.yml` records each allowed PDF source. Required fields include `id`, `filename`, `title`, `publisher`, `source_url`, `pdf_url`, `source_type`, `license_note`, `authority_level`, `domain`, and `allowed_for_rag`.

The optional `local_filenames` field maps already-downloaded files such as `1002110.pdf` to the canonical registry entry without requiring the user to rename files.

## PDF Chunk Metadata

Each chunk in `authority_knowledge/chunks/authority_chunks.jsonl` contains:

- `chunk_id`, `source_id`, `title`, `filename`
- `source_url`, `pdf_url`, `publisher`, `source_type`
- `authority_level`, `domain`, `license_note`
- `page_start`, `page_end`, `section_title`
- `content_sha256`, `created_at`, `preview`, and full `text`

The MVP uses `fallback_json` retrieval. Chroma can be added later, but JSONL remains the required fallback so local and CI runs do not depend on a vector service.

## Citation Schema

Each citation returned by `/api/agent/segmentation/analyze` contains `source_id`, `title`, `publisher`, `source_url`, `pdf_url`, `page_start`, `page_end`, `chunk_id`, `preview`, `authority_level`, and `score`.

## Segmentation-Driven Query

The retrieval query combines the user question with model facts:

- detected organs;
- abdominal CT and multi-organ segmentation;
- `pixel_count` and `percentage`;
- single-slice limitation and manual review;
- Dice, IoU, Jaccard, HD95, Hausdorff, surface distance, and ground truth.

## Safety Boundary

The Agent may explain model outputs, single-slice limitations, metric meaning, and quality-control review points. It must not output clinical diagnosis, treatment advice, disease judgment, or phrases such as “诊断为”, “患有”, “治疗建议”, or “临床结论”.

Every report must include a safety statement that the result is only for research-assistance analysis and model-output interpretation, not clinical diagnosis.

## Resume Wording

Built a Local-PDF Authority RAG agent for a medical image segmentation platform: `/predict` outputs are transformed into model facts, user-provided authority PDFs are chunked with page-level citation metadata, and the agent generates segmentation-grounded research reports with strict medical safety boundaries.
