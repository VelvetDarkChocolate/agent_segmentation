import argparse
import asyncio
import time
from pathlib import Path

import httpx


async def upload_case(client: httpx.AsyncClient, image_path: Path, index: int) -> str:
    with image_path.open("rb") as image_file:
        files = {
            "files": (f"load_case_{index}_{image_path.name}", image_file, "image/png"),
        }
        data = {"modality": "CT", "body_part": "肝脏"}
        response = await client.post("/api/cases/upload", files=files, data=data)

    response.raise_for_status()
    return response.json()["case_id"]


async def enqueue_task(client: httpx.AsyncClient, case_id: str) -> str:
    response = await client.post(
        "/api/segmentations",
        json={
            "case_id": case_id,
            "model_name": "Seg-Model v2.0",
            "threshold": 0.5,
        },
    )
    response.raise_for_status()
    return response.json()["task_id"]


async def poll_task(client: httpx.AsyncClient, task_id: str, timeout_seconds: int) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_payload = {}

    while time.monotonic() < deadline:
        response = await client.get(f"/api/tasks/{task_id}")
        response.raise_for_status()
        payload = response.json()
        last_payload = payload
        if payload["state"] in {"SUCCESS", "FAILURE"}:
            return payload
        await asyncio.sleep(0.5)

    return {
        "task_id": task_id,
        "state": "TIMEOUT",
        "progress": last_payload.get("progress", 0),
        "message": "poll timeout",
    }


async def run_load_test(args: argparse.Namespace) -> None:
    image_path = Path(args.image).expanduser().resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    started_at = time.perf_counter()
    limits = httpx.Limits(max_connections=args.concurrency * 2)
    timeout = httpx.Timeout(args.request_timeout)

    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout, limits=limits) as client:
        health = (await client.get("/health")).json()
        print(f"health={health}")

        print(f"uploading {args.requests} cases with concurrency={args.concurrency}")
        upload_sem = asyncio.Semaphore(args.concurrency)

        async def guarded_upload(index: int) -> str:
            async with upload_sem:
                return await upload_case(client, image_path, index)

        case_ids = await asyncio.gather(*(guarded_upload(index) for index in range(args.requests)))

        print(f"enqueueing {len(case_ids)} segmentation tasks")
        enqueue_started = time.perf_counter()
        task_ids = await asyncio.gather(*(enqueue_task(client, case_id) for case_id in case_ids))
        enqueue_seconds = time.perf_counter() - enqueue_started
        print(f"queued={len(task_ids)} enqueue_seconds={enqueue_seconds:.2f}")

        print("polling task completion")
        results = await asyncio.gather(
            *(poll_task(client, task_id, args.poll_timeout) for task_id in task_ids)
        )

    total_seconds = time.perf_counter() - started_at
    states = {}
    for result in results:
        states[result["state"]] = states.get(result["state"], 0) + 1

    print(f"states={states}")
    print(f"total_seconds={total_seconds:.2f}")
    print(f"api_enqueue_qps={len(task_ids) / max(enqueue_seconds, 0.001):.2f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load test FastAPI + Redis + Celery queue flow.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--image", required=True)
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--request-timeout", type=float, default=30)
    parser.add_argument("--poll-timeout", type=int, default=120)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run_load_test(parse_args()))
