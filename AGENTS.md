# Repository Agent Rules

- Do not use self-written medical Markdown as authoritative medical evidence.
- Do not use network scraping, webpage summaries, or auto-downloaded medical pages as authoritative medical evidence.
- Medical explanations must come from local PDF chunks registered in `authority_knowledge/source_registry.yml`.
- If no local PDF chunk is retrieved, state that the local authority PDF knowledge base evidence is insufficient.
- Do not provide clinical diagnosis, treatment advice, disease judgment, or physician replacement claims.
- All medical RAG answers must include PDF citations and page numbers when evidence is available.
- Segmentation results must be described as model predictions from `/predict`, not doctor labels or ground truth.
- Single-slice area percentage must not be interpreted as organ volume or disease severity.
- Keep `/health`, `/version`, `/predict`, `/api/cases`, `/api/reports`, `/api/agent/chat`, and `/api/agent/documents/upload` compatible.
- Never commit API keys, local PDFs, generated JSONL chunks, manifests, or vector stores.
