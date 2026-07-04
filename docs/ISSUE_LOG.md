| Issue ID | 问题描述                            | 严重级别   | 影响范围 | Owner            | 状态          | 修复方案                | 复测结果    |
| -------- | ------------------------------- | ------ | ---- | ---------------- | ----------- | ------------------- | ------- |
| Q-001    | 前端模型预设未真正联动后端模型                 | Medium | 用户体验 | Backend          | Open        | 增加 model registry   | Pending |
| Q-002    | 前端展示 CUDA/TensorRT 信息可能与实际环境不一致 | Medium | 信任度  | Frontend         | Open        | 改为调用 `/health` 动态展示 | Pending |
| Q-003    | 非图片文件上传缺少清晰提示                   | High   | UAT  | Frontend/Backend | In Progress | 增加文件校验              | Pending |
| Q-004    | Celery 分割任务当前为模拟结果              | Medium | 平台能力 | Backend          | Open        | 后续接入真实推理            | Pending |

## Issue Record Template

| Field | Description |
|---|---|
| Issue ID | Unique id such as Q-005 or T-001 |
| Summary | Short problem description |
| Reproduction Steps | Exact steps, input file, API path, browser, timestamp |
| Expected Result | What should happen |
| Actual Result | What happened |
| Severity | Critical / High / Medium / Low |
| Priority | P0 / P1 / P2 / P3 |
| Owner | Frontend / Backend / Model / Infra / QA |
| Status | Open / Investigating / Fixed / Retest / Closed |
| Fix Version | Target release |
| Retest Result | Pass / Fail and evidence |

## Support Ticket Examples

| Ticket ID | User Issue | Impact | Priority | Current Status | Owner | Escalation Path |
|---|---|---|---|---|---|---|
| T-001 | Upload returns error or page has no response | Blocks usage | High | Investigating | Frontend | Backend/Infra |
| T-002 | Task remains Running/Pending | Blocks result review | Medium | Open | Backend | Celery/Redis |
| T-003 | Segmentation colors are unclear | User experience | Low | Planned | Frontend | Product |
| T-004 | Model not loaded after restart | Blocks inference | High | Open | Backend | Model/Infra |
