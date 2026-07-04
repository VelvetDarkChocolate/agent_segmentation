# Project Tracking

| Milestone | Task | Owner | Status | Risk | Notes |
|---|---|---|---|---|---|
| M1 | Add health check API | Dev | Done | Low | Supports operations |
| M1 | Add version API | Dev | Done | Low | Supports release tracking |
| M2 | Add UAT checklist | QA | Done | Low | Supports acceptance testing |
| M2 | Add regression tests | QA | Done | Medium | Model inference test needs sample image |
| M3 | Add CI workflow | DevOps | Done | Medium | Heavy ML dependencies excluded from CI |
| M3 | Add Dockerfile | DevOps | Done | Medium | Model file mounted by env path |
| M4 | Improve frontend error handling | Product/Dev | Pending | Medium | Needed before demo |

| 模块           | Owner    | 当前状态        | 里程碑  | 依赖     | 风险          | 下一步     |
| ------------ | -------- | ----------- | ---- | ------ | ----------- | ------- |
| FastAPI 推理接口 | Backend  | Done        | v0.1 | 模型权重   | 模型未加载返回 503 | 增加异常提示  |
| React 前端     | Frontend | In Progress | v0.2 | API 联调 | 错误展示不足      | 增加错误状态页 |
| Celery 异步任务  | Backend  | Demo        | v0.2 | Redis  | 当前为模拟任务     | 接入真实推理  |
| UAT 验收       | QA/PM    | In Progress | v0.2 | 测试样例   | 缺少真实医学样例    | 增加测试数据  |

## Owner Matrix

| Area | Owner | Responsibilities | Escalation Trigger |
|---|---|---|---|
| Frontend | Frontend owner | React pages, upload UX, task progress display, report view | blank page, unreadable error, layout issue |
| Backend | Backend owner | FastAPI APIs, request validation, task status API, error handling | API 5xx, upload parsing, task status wrong |
| Model | Model owner | checkpoint compatibility, segmentation quality, class mapping | low quality result, model load failure, CUDA op error |
| Infra | Infra owner | Redis, Celery worker, Docker, GPU runtime | queue backlog, worker down, GPU unavailable |
| QA/PM | QA/PM owner | UAT, issue triage, release decision, user feedback | acceptance blocked, unclear requirement |

## Operational Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Model not loaded | `/predict` unavailable | Health check, default model path, runbook escalation |
| Upload failure | Case cannot be created | Validate file type and multipart field, log issue details |
| Task stuck | Report not generated | Check Redis/Celery, keep GPU worker `--concurrency=1` |
| GPU overload | Slow or failed inference | Queue requests through Celery and scale only after capacity testing |
| Frontend/API mismatch | User sees stale or wrong status | Drive environment state from `/health` and API responses |

## High Concurrency Validation

| Test | Tool | Success Signal |
|---|---|---|
| Queue burst | `scripts/load_test_queue.py --requests 20 --concurrency 20` | requests receive task ids quickly |
| Worker stability | Celery log | tasks process sequentially with `--concurrency=1` |
| Completion | `/api/tasks/{task_id}` polling | final state reaches `SUCCESS` |
| Release evidence | terminal output | record `states`, `total_seconds`, `api_enqueue_qps` |
