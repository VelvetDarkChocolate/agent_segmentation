# UAT Checklist - Medical AI Segmentation Platform

## Scope
This UAT checklist validates the FastAPI-based AI segmentation platform before release.

## Acceptance Criteria Template

Good acceptance criteria should include scenario, input, expected behavior, success standard, and error handling.

Example:

> When a user uploads PNG/JPG medical slices, the system should return a segmentation overlay and metrics. If the model is not loaded, the API should return a clear 503 error and the frontend should show a readable message without crashing.

## Test Cases

| ID | Scenario | Steps | Expected Result | Status |
|---|---|---|---|---|
| UAT-001 | Health check | Open `/health` | API returns status ok | Pending |
| UAT-002 | Version check | Open `/version` | App name and version are returned | Pending |
| UAT-003 | No image uploaded | Submit empty request to `/predict` | API returns validation error | Pending |
| UAT-004 | Single image inference | Upload one valid image | Segmentation result and metrics are returned | Pending |
| UAT-005 | Multiple image inference | Upload multiple images | Batch results are returned | Pending |
| UAT-006 | Model not loaded | Start service without MODEL_PATH | API returns clear 503 error | Pending |
| UAT-007 | Frontend request | Click Analyze button on web UI | Request reaches `/predict` successfully | Pending |
| UAT-008 | Error message | Upload invalid file | User sees readable error message | Pending |
| UAT-009 | Async queue task | Upload case, submit `/api/segmentations`, poll `/api/tasks/{task_id}` | Task reaches SUCCESS and report is created | Pending |
| UAT-010 | Concurrent queue requests | Run `scripts/load_test_queue.py --requests 20 --concurrency 20` | All tasks are queued and completed without API crash | Pending |
| UAT-011 | Task stuck handling | Stop Celery, submit async task | Task remains pending and runbook escalation path is followed | Pending |
| UAT-012 | Upload failure handling | Upload invalid file type or empty request | User receives clear error and issue can be logged with steps | Pending |

| 用例编号    | 场景     | 验收标准    | 测试步骤       | 预期结果                       | 实际结果 | 状态   | Issue |
| ------- | ------ | ------- | ---------- | -------------------------- | ---- | ---- | ----- |
| UAT-001 | 打开平台首页 | 页面正常加载  | 访问前端地址     | 显示工作台                      | 通过   | Pass | -     |
| UAT-002 | 上传合法图片 | 能返回分割结果 | 上传 PNG/JPG | 显示叠加图                      | 通过   | Pass | -     |
| UAT-003 | 模型未加载  | 返回明确错误  | 不配置模型启动服务  | 返回 503                     | 通过   | Pass | -     |
| UAT-004 | 上传非法文件 | 前端提示错误  | 上传 txt/pdf | 显示格式错误                     | 待修复  | Fail | Q-001 |
| UAT-005 | 查询任务进度 | 能看到任务状态 | 提交异步任务     | 返回 pending/running/success | 通过   | Pass | -     |


## Release Decision
- Pass: all critical cases pass.
- Block: health check, predict API, or frontend flow fails.

## Regression Test Scope

Run regression testing after any upload, inference, queue, or frontend display change:

| Area | Regression Check |
|---|---|
| Health | `/health` returns `status=ok`, `model_loaded=true`, `device=cuda` |
| Upload | Valid PNG/JPG upload works; invalid file shows clear error |
| Real inference | `/predict` returns `status=success`, `image_base64`, and metrics |
| Queue flow | `/api/segmentations` returns `task_id`; `/api/tasks/{task_id}` reaches SUCCESS |
| Report | Completed queue task appears in `/api/reports` |
| Frontend | `/cases`, `/workbench`, `/models`, `/reports` load without blank page |
| High concurrency | Queue load test completes with expected success count |
