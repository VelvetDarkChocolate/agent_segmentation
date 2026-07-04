import os
import io
import uuid
import numpy as np
import base64
import requests
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Any, Dict, List

from agent.authority_retriever import authority_status
from agent.service import analyze_segmentation_with_authority

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

try:
    import torch
    from PIL import Image
    from torchvision import transforms

    from networks.vision_transformer import MMRSGUNet as ViT_seg
    from config import get_config

    ML_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - exercised in lightweight CI envs
    torch = None
    Image = None
    transforms = None
    ViT_seg = None
    get_config = None
    ML_IMPORT_ERROR = str(exc)

import time
import logging

APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "model" / "epoch_241.pth"
MODEL_PATH = os.getenv("MODEL_PATH") or str(DEFAULT_MODEL_PATH)
START_TIME = time.time()
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
CASE_STORE: Dict[str, dict] = {}
REPORT_STORE: Dict[str, dict] = {}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("medical-ai-platform")


class SegmentationRequest(BaseModel):
    case_id: str
    model_name: str = "Seg-Model v2.0"
    threshold: float = 0.5


class AgentChatMessage(BaseModel):
    role: str
    content: str


class AgentChatRequest(BaseModel):
    message: str
    history: List[AgentChatMessage] = []
    segmentation_context: str = ""


class SegmentationAnalyzeRequest(BaseModel):
    message: str
    segmentation_result: Dict[str, Any]
    top_k: int = 8
    authority_only: bool = True
    min_authority_level: int = 4


DEEPSEEK_SYSTEM_PROMPT = """
你是医学图像分割平台内置的 DeepSeek 科研助手。你可以帮助用户理解 MMRSG-UNet 项目、分割流程、实验指标和结果报告。
必须遵守：仅做医学影像科研辅助分析；不提供临床诊断；不提供治疗建议；不声称可以替代医生。
回答应简洁、专业、结构化。如果用户询问分割结果，请提醒需要结合模型输出、人工复核和科研场景理解。
"""


def load_local_env():
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

# ==========================================
# 2. FastAPI 服务构建
# ==========================================
app = FastAPI(title="MMRSG-UNet Medical API")

# 允许跨域请求（方便前端调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. 初始化配置与模型 (保留您原本的逻辑)
# ==========================================
class MockArgs:
    dataset = 'Synapse'
    img_size = 224
    num_classes = 9
    cfg = 'configs/cswin_tiny_224_lite.yaml'
    opts = None
    zip = False
    cache_mode = 'part'
    resume = None
    accumulation_steps = None
    use_checkpoint = False
    amp_opt_level = 'O1'
    tag = None
    eval = False
    throughput = False
    batch_size = 1
    base_lr = 0.0001
    max_epochs = 250
    output_dir = './'
    list_dir = './lists/lists_Synapse'
    volume_path = '../data/Synapse'

args = MockArgs()
device = torch.device("cuda" if torch and torch.cuda.is_available() else "cpu") if torch else "unavailable"
model = None
config = None

if not torch or not ViT_seg or not get_config:
    logger.warning("Model dependencies are unavailable. Model will not be loaded: %s", ML_IMPORT_ERROR)
elif not MODEL_PATH or not Path(MODEL_PATH).exists():
    logger.warning("MODEL_PATH is not set or does not exist. Model will not be loaded: %s", MODEL_PATH)
else:
    config = get_config(args)
    model = ViT_seg(config, img_size=args.img_size, num_classes=args.num_classes).to(device)
    checkpoint = torch.load(MODEL_PATH, map_location=device)
    new_state_dict = {}
    for k, v in checkpoint.items():
        new_key = k.replace('cswin_unet.', 'mmrsg_unet.').replace('MSCA', 'msdc')
        new_state_dict[new_key] = v

    model.load_state_dict(new_state_dict, strict=False)
    model.eval()
    logger.info("Model loaded from %s", MODEL_PATH)

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "app_version": APP_VERSION,
        "model_loaded": model is not None,
        "device": str(device),
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }


@app.get("/version")
async def version():
    return {
        "app_name": "medical-ai-segmentation-platform",
        "version": APP_VERSION
    }


@app.post("/api/agent/chat")
async def agent_chat(payload: AgentChatRequest):
    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = (os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    model_name = os.getenv("LLM_MODEL") or "deepseek-v4-flash"

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

    try:
        response = requests.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "messages": messages,
                "temperature": 0.2,
                "stream": False,
            },
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        return {
            "answer": answer,
            "model": model_name,
            "configured": True,
        }
    except Exception as exc:
        logger.exception("DeepSeek chat request failed")
        raise HTTPException(status_code=502, detail=f"DeepSeek 调用失败：{exc}") from exc


@app.get("/api/agent/authority/status")
async def get_authority_status():
    return authority_status()


@app.post("/api/agent/authority/reindex")
async def reindex_authority_knowledge():
    try:
        from scripts.ingest_local_authority_pdfs import ingest_local_authority_pdfs

        return ingest_local_authority_pdfs()
    except Exception as exc:
        logger.exception("Authority knowledge reindex failed")
        raise HTTPException(status_code=500, detail=f"Authority reindex failed: {exc}") from exc


@app.post("/api/agent/segmentation/analyze")
async def analyze_segmentation(payload: SegmentationAnalyzeRequest):
    api_key = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    base_url = (os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    model_name = os.getenv("LLM_MODEL") or "deepseek-v4-flash"
    if base_url.startswith("sk-"):
        api_key = ""
        base_url = "https://api.deepseek.com"
    return analyze_segmentation_with_authority(
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
async def upload_agent_documents(files: List[UploadFile] = File(...)):
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
    files: List[UploadFile] = File(...),
    modality: str = Form("CT"),
    body_part: str = Form("肝脏"),
):
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个文件")

    case_id = f"CASE-{time.strftime('%Y%m%d')}-{str(uuid.uuid4())[:8]}"
    case_dir = UPLOAD_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for file in files:
        safe_name = Path(file.filename).name
        target_path = case_dir / safe_name
        content = await file.read()
        target_path.write_bytes(content)
        saved_files.append(safe_name)

    case = {
        "case_id": case_id,
        "modality": modality,
        "body_part": body_part,
        "file_count": len(saved_files),
        "filenames": saved_files,
        "status": "已上传",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    CASE_STORE[case_id] = case
    return case


@app.get("/api/cases")
async def list_cases():
    return list(CASE_STORE.values())


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
        {
            "name": "Seg-Model v1.0",
            "body_part": "肝脏分割",
            "dice": 0.887,
            "hd95": 9.64,
            "status": "已下线",
            "version": "v1.0",
        },
    ]


@app.post("/api/segmentations")
async def create_segmentation_task(payload: SegmentationRequest):
    case = CASE_STORE.get(payload.case_id)
    if not case:
        raise HTTPException(status_code=404, detail="病例不存在，请先上传数据")
    if segmentation_task is None:
        raise HTTPException(status_code=503, detail=f"Celery is unavailable: {CELERY_IMPORT_ERROR}")

    task = segmentation_task.delay(
        case_id=payload.case_id,
        filenames=case["filenames"],
        model_name=payload.model_name,
        threshold=payload.threshold,
    )

    case["status"] = "处理中"
    case["task_id"] = task.id

    return {
        "task_id": task.id,
        "case_id": payload.case_id,
        "status": "queued",
        "progress": 0,
        "message": "任务已进入 Redis 队列，等待 Celery Worker 处理",
    }


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    if AsyncResult is None or celery_app is None:
        return {
            "task_id": task_id,
            "state": "UNAVAILABLE",
            "progress": 0,
            "message": f"Celery is unavailable: {CELERY_IMPORT_ERROR}",
        }

    task = AsyncResult(task_id, app=celery_app)

    if task.state == "PENDING":
        return {
            "task_id": task_id,
            "state": task.state,
            "progress": 0,
            "message": "任务等待中",
        }

    if task.state in ["STARTED", "PROGRESS"]:
        meta = task.info or {}
        return {
            "task_id": task_id,
            "state": task.state,
            "progress": meta.get("progress", 10),
            "message": meta.get("message", "任务处理中"),
        }

    if task.state == "SUCCESS":
        result = task.result
        REPORT_STORE[result["case_id"]] = result
        if result["case_id"] in CASE_STORE:
            CASE_STORE[result["case_id"]]["status"] = "已完成"

        return {
            "task_id": task_id,
            "state": task.state,
            "progress": 100,
            "message": "任务完成",
            "result": result,
        }

    if task.state == "FAILURE":
        return {
            "task_id": task_id,
            "state": task.state,
            "progress": 0,
            "message": str(task.info),
        }

    return {
        "task_id": task_id,
        "state": task.state,
        "progress": 0,
        "message": "未知状态",
    }


@app.get("/api/reports")
async def list_reports():
    return list(REPORT_STORE.values())

transform = transforms.Compose([
    transforms.Resize((args.img_size, args.img_size)),
    transforms.ToTensor()
]) if transforms else None

# 类别名称与颜色映射
CLASS_NAMES = ["背景", "主动脉", "胆囊", "左肾", "右肾", "肝脏", "胰腺", "脾脏", "胃"]
COLORS = np.array([
    [0, 0, 0], [255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0], 
    [255, 0, 255], [0, 255, 255], [255, 128, 0], [128, 0, 128],
], dtype=np.uint8)

# ==========================================
# 新增：让根目录直接返回我们的前端 HTML 网页
# ==========================================
@app.get("/")
async def serve_frontend():
    # 确保您的 index.html 和 app.py 放在同一个目录下
    return FileResponse("index.html")

@app.post("/predict")
async def predict_api(
    files: List[UploadFile] = File(...), 
    alpha: float = Form(0.4),
    model_preset: str = Form("abdomen"),     # 👈 新增：接收模型部位
    inference_mode: str = Form("accurate")   # 👈 新增：接收推理精度
):
    if model is None:
        return JSONResponse(
            content={
                "status": "error",
                "message": "Model is not loaded. Please set MODEL_PATH before inference."
            },
            status_code=503
        )

    try:
        # 🔥 在后台终端打印前端传过来的设置，你可以借此确认前后端已经打通！
        print(f"==== 🚀 收到推理任务 ====")
        print(f"预设部位: [{model_preset}]")
        print(f"推理模式: [{inference_mode}]")
        print(f"切片数量: {len(files)} 张")
        print(f"===========================")

        images = []
        original_sizes = []
        
        # 1. 异步读取所有上传的图片
        for file in files:
            image_bytes = await file.read()
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != 'RGB':
                image = image.convert('RGB')
            images.append(image)
            original_sizes.append(image.size)

        if not images:
            return JSONResponse(content={"status": "error", "message": "未接收到图片"}, status_code=400)

        # 2. 将多张图片堆叠成一个 Batch Tensor (B, C, H, W)
        tensor_list = [transform(img) for img in images]
        batch_tensor = torch.stack(tensor_list).to(device)

        # 3. 批量推理 (GPU 并行加速)
        # 💡 这里可以根据前端传来的 inference_mode 决定是否开启半精度加速
        if inference_mode == "fast" and getattr(device, "type", "") == "cuda":
            with torch.autocast(device_type='cuda', dtype=torch.float16):
                with torch.no_grad():
                    output = model(batch_tensor)
        else:
            with torch.no_grad():
                output = model(batch_tensor)

        # 输出形状应为 [B, num_classes, H, W]
        preds = output[0] if isinstance(output, list) else output
        # 批量获取类别索引，形状 [B, H, W]
        pred_masks = torch.argmax(preds, dim=1).cpu().numpy()

        # 4. 批量后处理与数据封装
        results = []
        for b in range(len(images)):
            pred_mask = pred_masks[b]
            original_size = original_sizes[b]
            filename = files[b].filename

            # 计算量化指标
            total_pixels = pred_mask.shape[0] * pred_mask.shape[1]
            metrics = []
            for i in range(1, args.num_classes):
                pixel_count = np.sum(pred_mask == i)
                if pixel_count > 0:
                    percentage = (pixel_count / total_pixels) * 100
                    metrics.append({
                        "organ": CLASS_NAMES[i],
                        "pixel_count": int(pixel_count),
                        "percentage": f"{percentage:.2f}%"
                    })

            # 图像后处理与半透明叠加
            color_mask = COLORS[pred_mask]
            mask_image = Image.fromarray(color_mask).resize(original_size, Image.NEAREST)
            blend_image = Image.blend(images[b], mask_image, alpha=alpha)

            # 转换为 Base64
            buffered = io.BytesIO()
            blend_image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

            results.append({
                "filename": filename,
                "image_base64": f"data:image/png;base64,{img_str}",
                "metrics": metrics
            })

        return JSONResponse(content={
            "status": "success",
            "results": results
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)
    
async def predict_api(file: UploadFile = File(...), alpha: float = Form(0.4)):
    try:
        # 1. 读取并预处理图像
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode != 'RGB':
            image = image.convert('RGB')
        original_size = image.size

        # 2. 模型推理
        img_tensor = transform(image).unsqueeze(0).to(device)
        with torch.no_grad():
            output = model(img_tensor)
            pred = output[0] if isinstance(output, list) else output
            pred_mask = torch.argmax(pred, dim=1).squeeze(0).cpu().numpy()

        # 3. 计算量化指标 (各个器官的像素面积占比)
        total_pixels = pred_mask.shape[0] * pred_mask.shape[1]
        metrics = []
        for i in range(1, args.num_classes): # 跳过背景(0)
            pixel_count = np.sum(pred_mask == i)
            if pixel_count > 0:
                percentage = (pixel_count / total_pixels) * 100
                metrics.append({
                    "organ": CLASS_NAMES[i],
                    "pixel_count": int(pixel_count),
                    "percentage": f"{percentage:.2f}%"
                })

        # 4. 图像后处理与叠加
        color_mask = COLORS[pred_mask]
        mask_image = Image.fromarray(color_mask).resize(original_size, Image.NEAREST)
        blend_image = Image.blend(image, mask_image, alpha=alpha)

        # 5. 转换为 Base64 以供前端渲染
        buffered = io.BytesIO()
        blend_image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

        return JSONResponse(content={
            "status": "success",
            "image_base64": f"data:image/png;base64,{img_str}",
            "metrics": metrics
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
