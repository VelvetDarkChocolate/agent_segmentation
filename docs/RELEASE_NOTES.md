# Release Notes v0.2.0

## New
- Added React + Vite frontend for AI segmentation workflow.
- Added FastAPI backend endpoints for health check, version, prediction and async task tracking.
- Added Celery + Redis demo flow for long-running segmentation tasks.
- Added UAT checklist and project tracking document.

## Improved
- Improved deployment readiness with Dockerfile and runbook.
- Added pytest coverage for health, version and model-not-loaded scenarios.
- Added GitHub Actions CI workflow.
- Added operational guidance for model loading, upload failure, stuck tasks, and owner escalation.
- Added queue load test script to validate high-concurrency task submission.

## Known Issues
- Model preset selection is not fully connected to backend model registry.
- Celery segmentation task is currently a platform workflow demo.
- DICOM/NIfTI production workflow is not fully implemented.

## Release Checklist

| Check | Status | Notes |
|---|---|---|
| Core workflow passes | Pending | Upload, workbench, report |
| UAT completed | Pending | See `docs/UAT_CHECKLIST.md` |
| High priority issues closed | Pending | See `docs/ISSUE_LOG.md` |
| Regression passed | Pending | Health, upload, inference, queue, frontend |
| Release notes updated | Done | This file |
| Runbook updated | Done | See `docs/RUNBOOK.md` |
| Version checked | Pending | `/version` |
| Health check normal | Pending | `/health` |
| Deployment steps verified | Pending | Docker/local run |
| Known issues recorded | Done | This file |
| Rollback plan clear | Pending | Revert release commit or redeploy previous image |
