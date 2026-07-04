# Runbook - Medical AI Segmentation Platform

## Start Service

```bash
export MODEL_PATH=/path/to/epoch_241.pth
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Start Full Platform

Redis:

```bash
redis-server
```

FastAPI:

```bash
cd ~/proiect_pratice_of_cnn/MMRSG-UNet-main
python -m uvicorn app:app --reload --port 8000
```

Celery worker:

```bash
celery -A celery_app.celery_app worker --loglevel=info --concurrency=1
```

React frontend:

```bash
cd ~/proiect_pratice_of_cnn/MMRSG-UNet-main/frontend
npm run dev
```

## Health Checks

| Check | Command | Expected |
|---|---|---|
| API health | `curl http://localhost:8000/health` | `status=ok` |
| Model loaded | `curl http://localhost:8000/health` | `model_loaded=true` |
| GPU ready | `curl http://localhost:8000/health` | `device=cuda` |
| Version | `curl http://localhost:8000/version` | app name and version |
| Frontend | open `http://localhost:5175/workbench` | workbench loads |

## Incident Response

### Model Not Loaded

Symptoms:
- `/health` returns `model_loaded=false`.
- `/predict` returns `503`.
- Frontend cannot produce segmentation overlay.

Checks:
```bash
ls -lh model/epoch_241.pth
curl http://localhost:8000/health
```

Actions:
- Confirm the model file exists.
- Start FastAPI from the project root.
- Set `MODEL_PATH` explicitly if using a different checkpoint.
- Restart FastAPI after changing model files or environment variables.

Escalation:
- Backend owner: API loading path or error response.
- Model owner: checkpoint compatibility, class count, architecture mismatch.
- Infra owner: GPU/CUDA/container runtime problem.

### User Upload Failed

Symptoms:
- Upload returns `400`, `422`, or frontend shows upload error.
- Case does not appear in `/api/cases`.

Checks:
```bash
curl http://localhost:8000/health
ls -ld uploads
```

Actions:
- Verify the file is PNG/JPG for `/predict`.
- Verify multipart field name is `files`.
- Confirm `uploads/` is writable.
- Ask user for filename, size, file type, browser, and timestamp.

Escalation:
- Frontend owner: validation message or form data issue.
- Backend owner: request parsing, file writing, API status code.
- Product/QA owner: unsupported file type requirement.

### Inference Task Stuck

Symptoms:
- `/api/tasks/{task_id}` stays `PENDING` or `PROGRESS`.
- Result report never appears.

Checks:
```bash
redis-cli ping
celery -A celery_app.celery_app inspect active
celery -A celery_app.celery_app inspect reserved
```

Actions:
- Confirm Redis is running.
- Confirm Celery worker is running.
- Keep GPU worker at `--concurrency=1` unless capacity is tested.
- Restart a dead worker, then retry the task.
- Record task id and case id in the issue log.

Escalation:
- Backend owner: task state API, Celery task code.
- Infra owner: Redis availability, queue backlog, worker process.
- Model owner: task fails inside model inference.

## High Concurrency Test

Use this to prove API requests are queued instead of forcing many GPU jobs to run at once:

```bash
python scripts/load_test_queue.py \
  --image uploads/CASE-20260703-901bb694/case0036_slice_142_img.png \
  --requests 20 \
  --concurrency 20
```

Expected:
- FastAPI quickly returns task ids.
- Redis queues tasks.
- Celery processes tasks steadily.
- `states={'SUCCESS': 20}` after polling.

Operational interpretation:
- FastAPI handles concurrent request bursts.
- Redis provides buffering.
- Celery controls GPU consumption.
- High concurrency is achieved through queue-based back pressure, not by running many GPU models at the same time.
