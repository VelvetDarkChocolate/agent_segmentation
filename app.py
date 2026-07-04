import asyncio
import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.authority_retriever import authority_status
from agent.service import analyze_segmentation_with_authority
from backend.core.config import ROOT_DIR, settings
from backend.core.database import init_db
from backend.services.case_service import create_case_from_uploads, list_cases
from backend.services.inference_service import InferenceUnavailable, inference_service
from backend.services.segmentation_service import (
    attach_celery_task,
    case_exists,
    create_segmentation_record,
    fail_segmentation_task,
    get_task_status_payload,
    list_reports,
)
from backend.services.storage_service import object_store

try:
    from celery.result import AsyncResult
    from celery_app import celery_app
    from tasks import segmentation_task

    CELERY_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - exercised in lightweight CI envs
    AsyncResult = None
    celery_app = None
    segmentation_task = None
    CELERY_IMPORT_ERROR = str(exc)


START_TIME = time.time()
init_db()

app = FastAPI(title="MMRSG-UNet Medical API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/objects", StaticFiles(directory=object_store.root), name="objects")


class SegmentationRequest(BaseModel):
    case_id: str
    model_name: str = "Seg-Model v2.0"
    threshold: float = 0.5


class AgentChatMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    message: str
    history: list[AgentChatMessage] = Field(default_factory=list)
    segmentation_context: str = ""


class SegmentationAnalyzeRequest(BaseModel):
    message: str
    segmentation_result: dict[str, Any]
    top_k: int = 8
    authority_only: bool = True
    min_authority_level: int = 4


DEEPSEEK_SYSTEM_PROMPT = """
你是医学图像分割平台内置的 DeepSeek 科研助手。你可以帮助用户理解 MMRSG-UNet 项目、分割流程、实验指标和结果报告。
必须遵守：仅做医学影像科研辅助分析；不提供临床诊断；不提供治疗建议；不声称可以替代医生。
回答应简洁、专业、结构化。如果用户询问分割结果，请提醒需要结合模型输出、人工复核和科研场景理解。
"""


def celery_state_for(status: str) -> str:
    return {
        "uploaded": "PENDING",
        "queued": "PENDING",
        "running": "PROGRESS",
        "completed": "SUCCESS",
        "failed": "FAILURE",
        "reviewed": "SUCCESS",
    }.get(status, "PENDING")


def task_response(payload: dict[str, Any]) -> dict[str, Any]:
    state = celery_state_for(payload["status"])
    response = {
        "task_id": payload["task_id"],
        "celery_task_id": payload.get("celery_task_id"),
        "case_id": payload["case_id"],
        "status": payload["status"],
        "state": state,
        "progress": payload.get("progress", 0),
        "message": payload.get("message") or ("任务完成" if state == "SUCCESS" else "任务处理中"),
        "error": payload.get("error", ""),
    }
    if state == "SUCCESS":
        response["result"] = payload.get("result", {})
    return response


async def post_llm_chat(messages: list[dict[str, str]]) -> dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    base_url = (os.getenv("LLM_BASE_URL") or settings.llm_base_url).rstrip("/")
    model_name = os.getenv("LLM_MODEL") or settings.llm_model

    if base_url.startswith("sk-"):
        return {
            "answer": (
                "DeepSeek 配置写反了：LLM_BASE_URL 应该是接口地址，不是 API key。\n\n"
                "请这样配置：\n"
                "LLM_API_KEY=你的 DeepSeek key\n"
                "LLM_BASE_URL=https://api.deepseek.com\n"
                "LLM_MODEL=deepseek-v4-flash\n\n"
                "修改后请重启后端服务。"
            ),
            "model": model_name,
            "configured": False,
        }

    if not api_key:
        return {
            "answer": (
                "DeepSeek API key 尚未配置。请在后端启动前设置 LLM_API_KEY 或 DEEPSEEK_API_KEY。\n\n"
                "示例：export LLM_API_KEY=\"你的 DeepSeek key\"\n\n"
                "安全提示：本助手仅用于医学影像科研辅助分析，不提供临床诊断或治疗建议。"
            ),
            "model": model_name,
            "configured": False,
        }

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(45.0)) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model_name,
                        "messages": messages,
                        "temperature": 0.2,
                        "stream": False,
                    },
                )
            response.raise_for_status()
            data = response.json()
            return {"answer": data["choices"][0]["message"]["content"], "model": model_name, "configured": True}
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(0.4 * (attempt + 1))
    raise HTTPException(status_code=502, detail=f"DeepSeek 调用失败：{last_error}")


@app.get("/health")
async def health_check():
    model_status = inference_service.status()
    return {
        "status": "ok",
        "app_version": settings.app_version,
        "model_loaded": model_status["model_loaded"],
        "model_file_exists": model_status["model_file_exists"],
        "model_dependencies_ready": model_status["dependencies_ready"],
        "device": model_status["device"],
        "database_url": settings.database_url.split("@")[-1],
        "object_store": str(object_store.root),
        "uptime_seconds": round(time.time() - START_TIME, 2),
    }


@app.get("/version")
async def version():
    return {"app_name": "medical-ai-segmentation-platform", "version": settings.app_version}


@app.get("/")
async def serve_frontend():
    return FileResponse(ROOT_DIR / "index.html")


@app.post("/api/agent/chat")
async def agent_chat(payload: AgentChatRequest):
    messages = [{"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT}]
    if payload.segmentation_context:
        messages.append(
            {
                "role": "system",
                "content": (
                    "以下是当前平台真实分割接口返回的结构化结果。回答用户关于分割结果、科研汇报、"
                    "器官面积占比或模型表现的问题时，必须优先使用这些数据；不要编造 Dice、HD95、"
                    "Ground Truth 或临床结论。\n\n"
                    f"{payload.segmentation_context}"
                ),
            }
        )
    for item in payload.history[-8:]:
        if item.role in {"user", "assistant"} and item.content:
            messages.append({"role": item.role, "content": item.content})
    messages.append({"role": "user", "content": payload.message})
    return await post_llm_chat(messages)


@app.get("/api/agent/authority/status")
async def get_authority_status():
    return authority_status()


@app.post("/api/agent/authority/reindex")
async def reindex_authority_knowledge():
    try:
        from scripts.ingest_local_authority_pdfs import ingest_local_authority_pdfs

        return ingest_local_authority_pdfs()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Authority reindex failed: {exc}") from exc


@app.post("/api/agent/segmentation/analyze")
async def analyze_segmentation(payload: SegmentationAnalyzeRequest):
    base_url = (os.getenv("LLM_BASE_URL") or settings.llm_base_url).rstrip("/")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY") or ""
    model_name = os.getenv("LLM_MODEL") or settings.llm_model
    if base_url.startswith("sk-"):
        api_key = ""
        base_url = "https://api.deepseek.com"
    return await analyze_segmentation_with_authority(
        message=payload.message,
        segmentation_result=payload.segmentation_result,
        top_k=payload.top_k,
        min_authority_level=payload.min_authority_level,
        authority_only=payload.authority_only,
        api_key=api_key,
        base_url=base_url,
        model_name=model_name,
    )


@app.post("/api/agent/documents/upload")
async def upload_agent_documents(files: list[UploadFile] = File(...)):
    return {
        "status": "disabled_in_authority_only_mode",
        "received_files": [Path(file.filename).name for file in files],
        "message": (
            "Local-PDF Authority RAG 不把临时上传文档作为权威医学依据。"
            "请把权威 PDF 手动放入 authority_knowledge/pdfs/ 或 知识库书籍/，"
            "再调用 /api/agent/authority/reindex。"
        ),
    }


@app.post("/api/cases/upload")
async def upload_case(
    files: list[UploadFile] = File(...),
    modality: str = Form("CT"),
    body_part: str = Form("肝脏"),
):
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个文件")
    payload = [(Path(file.filename).name, await file.read()) for file in files]
    return create_case_from_uploads(files=payload, modality=modality, body_part=body_part)


@app.get("/api/cases")
async def get_cases():
    return list_cases()


@app.get("/api/models")
async def list_models():
    return [
        {
            "name": "Seg-Model v2.0",
            "body_part": "肝脏分割",
            "dice": 0.932,
            "hd95": 7.12,
            "status": "已上线",
            "version": "v2.0",
        },
        {
            "name": "Seg-Model v1.2",
            "body_part": "肝脏分割",
            "dice": 0.912,
            "hd95": 8.35,
            "status": "已发布",
            "version": "v1.2",
        },
    ]


@app.post("/api/v1/segmentations")
@app.post("/api/segmentations")
async def create_segmentation_task(payload: SegmentationRequest):
    if not case_exists(payload.case_id):
        raise HTTPException(status_code=404, detail="病例不存在，请先上传数据")
    if segmentation_task is None:
        raise HTTPException(status_code=503, detail=f"Celery is unavailable: {CELERY_IMPORT_ERROR}")
    task_record = create_segmentation_record(payload.case_id)

    try:
        celery_task = segmentation_task.delay(
            task_id=task_record["task_id"],
            case_id=payload.case_id,
            model_name=payload.model_name,
            threshold=payload.threshold,
        )
    except Exception as exc:
        fail_segmentation_task(task_record["task_id"], f"Celery enqueue failed: {exc}")
        raise HTTPException(status_code=503, detail=f"Celery enqueue failed: {exc}") from exc
    attach_celery_task(task_record["task_id"], celery_task.id)
    task_record["celery_task_id"] = celery_task.id
    task_record["message"] = "任务已进入 Redis 队列，等待 Celery Worker 处理"
    return task_response(task_record)


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    payload = get_task_status_payload(task_id)
    if payload:
        return task_response(payload)

    if AsyncResult is None or celery_app is None:
        return {
            "task_id": task_id,
            "state": "UNAVAILABLE",
            "status": "unavailable",
            "progress": 0,
            "message": f"Celery is unavailable: {CELERY_IMPORT_ERROR}",
        }

    task = AsyncResult(task_id, app=celery_app)
    meta = task.info or {}
    return {
        "task_id": task_id,
        "state": task.state,
        "status": task.state.lower(),
        "progress": meta.get("progress", 0),
        "message": meta.get("message", "任务处理中"),
    }


@app.get("/api/reports")
async def get_reports():
    return list_reports()


async def read_uploads(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    return [(Path(file.filename).name, await file.read()) for file in files]


async def run_sync_prediction(
    files: list[UploadFile],
    alpha: float,
    model_preset: str,
    inference_mode: str,
):
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个文件")
    payload = await read_uploads(files)
    try:
        return await asyncio.to_thread(
            inference_service.run,
            files=payload,
            alpha=alpha,
            model_preset=model_preset,
            inference_mode=inference_mode,
            include_base64=True,
            persist_outputs=True,
        )
    except InferenceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/predict/sync")
async def predict_sync_api(
    files: list[UploadFile] = File(...),
    alpha: float = Form(0.4),
    model_preset: str = Form("abdomen"),
    inference_mode: str = Form("accurate"),
):
    try:
        result = await run_sync_prediction(files, alpha, model_preset, inference_mode)
        return JSONResponse(content=result)
    except HTTPException as exc:
        return JSONResponse(content={"status": "error", "message": exc.detail}, status_code=exc.status_code)
    except Exception as exc:
        return JSONResponse(content={"status": "error", "message": str(exc)}, status_code=500)


@app.post("/predict")
async def predict_api(
    files: list[UploadFile] = File(...),
    alpha: float = Form(0.4),
    model_preset: str = Form("abdomen"),
    inference_mode: str = Form("accurate"),
):
    return await predict_sync_api(files, alpha, model_preset, inference_mode)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
