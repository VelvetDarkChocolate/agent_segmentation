# Operations Playbook - Medical AI Segmentation Platform

## AI Platform Concept

An AI platform is more than a model endpoint. A practical platform usually includes:

| Area | Project Mapping |
|---|---|
| Data input | React case upload and FastAPI multipart upload |
| Model service | PyTorch MMRSG-UNet inference through `/predict` |
| Task scheduling | Synchronous `/predict` plus Redis/Celery async task demo |
| Result display | React workbench segmentation overlay and report page |
| Quality evaluation | Dice/IoU metrics, UAT checklist, regression scope |
| Operations monitoring | `/health`, `/version`, runbook, logs |
| Release management | release notes, checklist, GitHub branch workflow |
| Security and compliance | file handling, issue tracking, audit-oriented owner mapping |

Project summary:

> This project simulates a medical AI image segmentation platform with React, FastAPI, PyTorch, Celery, Redis, Docker, CI, UAT, Runbook, and release documentation. It shows that AI platform work is not just making a model run, but making it testable, traceable, operable, and releasable.

## UAT Definition

UAT means User Acceptance Testing. It validates whether the product satisfies user workflows and business requirements, not only whether code compiles.

How this project applies UAT:
- Define acceptance criteria before release.
- Cover normal path, error path, edge cases, and regression cases.
- Record actual result, severity, owner, status, and retest result.
- Block release when health, upload, inference, or frontend display fails.

## Regression Testing

Regression testing means verifying existing core functions after a fix or release change.

Example:

If upload error handling is changed, retest:
- valid PNG/JPG upload;
- invalid file upload;
- batch upload;
- model not loaded response;
- health check;
- React result display;
- async queue task status.

## Acceptance Criteria Guidance

Weak:

> Upload works.

Strong:

> Given a user uploads PNG/JPG medical slices from the workbench, when the backend model is loaded, the system should return a segmentation overlay image and organ metrics. If the model is not loaded, the API should return a 503 message and the frontend should show a readable error without crashing.

Formula:

```text
Scenario + Input + Expected Behavior + Success Standard + Error Handling
```

## Issue Management

Avoid vague issues such as "there is a bug." A useful issue includes:

- problem description;
- reproduction steps;
- expected result;
- actual result;
- severity;
- priority;
- owner;
- status;
- fix version;
- retest result.

Severity guide:

| Severity | Meaning | Example |
|---|---|---|
| Critical | Release blocker or data loss | API cannot start |
| High | Core workflow blocked | Upload or inference fails |
| Medium | Important workflow degraded | Task progress missing |
| Low | Experience issue | Label color unclear |

## Release Quality Gate

Before release, confirm:

| Check | Why It Matters |
|---|---|
| Core features pass | Main user workflow is usable |
| UAT completed | Business acceptance is documented |
| High-priority issues closed | Avoid known release blockers |
| Regression passed | Prevent old features from breaking |
| Release notes ready | Stakeholders know what changed |
| Runbook updated | Support team can operate the system |
| Version correct | Release tracking is possible |
| Health check normal | Basic availability is confirmed |
| Deployment verified | Release steps are repeatable |
| Known issues recorded | Risk is transparent |
| Rollback plan clear | Failure recovery is possible |

## Collaboration Model

Meeting notes should capture decisions and actions, not just discussion.

Template:

```markdown
# Meeting Notes

## Date
2026-xx-xx

## Attendees
PM, Backend, Frontend, Model, QA

## Topics
- UAT progress
- Upload error handling
- Celery task status display
- Model inference validation

## Decisions
- Use `/health` to drive environment status in frontend.
- Keep model preset as demo metadata in v0.2.
- Use `/predict` for real model inference in workbench.
- Use Redis/Celery flow to demonstrate async queue and high-concurrency handling.

## Action Items
| Item | Owner | Due Date | Status |
|---|---|---|---|
| Add invalid file upload validation | Frontend/Backend | xx/xx | Open |
| Update UAT checklist | QA/PM | xx/xx | In Progress |
| Verify checkpoint loading on CUDA | Model Owner | xx/xx | Done |

## Risks
- Lack of production DICOM/NIfTI data may delay full validation.
- GPU capacity limits require controlled worker concurrency.
```

## Owner Escalation

| Problem | Primary Owner | Escalation |
|---|---|---|
| Model not loaded | Backend | Model owner / Infra |
| Upload failed | Frontend or Backend | Product / QA for format requirement |
| Inference task stuck | Backend | Redis/Celery Infra |
| Segmentation quality issue | Model owner | Product / QA |
| Frontend blank page | Frontend | Backend if API dependency fails |
| GPU unavailable | Infra | Backend / Model owner |

## Support Response Examples

| Ticket ID | User Issue | Impact | Priority | Owner | Next Action |
|---|---|---|---|---|---|
| T-001 | Upload returns error | Blocks case creation | High | Frontend/Backend | Collect file type, size, timestamp, API response |
| T-002 | Task stays Running | Blocks report | Medium | Backend | Check Redis, Celery active/reserved tasks |
| T-003 | Model not loaded | Blocks inference | High | Backend/Model | Check `MODEL_PATH`, checkpoint, CUDA |
| T-004 | Overlay colors unclear | User experience | Low | Frontend/Product | Adjust color legend and opacity |

## Interview Talking Point

> I built this project as an AI platform workflow, not only a model demo. It includes data upload, real PyTorch inference, React result visualization, Redis/Celery async task handling, health/version endpoints, UAT documentation, issue tracking, release notes, and operational runbooks. This helped me understand how AI systems are validated, released, monitored, and supported in a production-like environment.
