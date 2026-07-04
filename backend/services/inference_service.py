import io
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from backend.core.config import settings
from backend.services.storage_service import object_store

try:
    import torch
    from PIL import Image
    from torchvision import transforms

    from config import get_config
    from networks.vision_transformer import MMRSGUNet as ViT_seg

    ML_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - lightweight CI environments may omit ML deps
    torch = None
    Image = None
    transforms = None
    get_config = None
    ViT_seg = None
    ML_IMPORT_ERROR = str(exc)


CLASS_NAMES = ["背景", "主动脉", "胆囊", "左肾", "右肾", "肝脏", "胰腺", "脾脏", "胃"]
COLORS = np.array(
    [
        [0, 0, 0],
        [255, 0, 0],
        [0, 255, 0],
        [0, 0, 255],
        [255, 255, 0],
        [255, 0, 255],
        [0, 255, 255],
        [255, 128, 0],
        [128, 0, 128],
    ],
    dtype=np.uint8,
)


class InferenceUnavailable(RuntimeError):
    pass


@dataclass
class ModelArgs:
    dataset: str = "Synapse"
    img_size: int = 224
    num_classes: int = 9
    cfg: str = "configs/cswin_tiny_224_lite.yaml"
    opts: None = None
    zip: bool = False
    cache_mode: str = "part"
    resume: None = None
    accumulation_steps: None = None
    use_checkpoint: bool = False
    amp_opt_level: str = "O1"
    tag: None = None
    eval: bool = False
    throughput: bool = False
    batch_size: int = 1
    base_lr: float = 0.0001
    max_epochs: int = 250
    output_dir: str = "./"
    list_dir: str = "./lists/lists_Synapse"
    volume_path: str = "../data/Synapse"


class InferenceService:
    def __init__(self, model_path: str | None = None):
        self.args = ModelArgs()
        self.model_path = model_path or settings.model_path
        self.device = torch.device("cuda" if torch and torch.cuda.is_available() else "cpu") if torch else "unavailable"
        self.model = None
        self.config = None
        self.transform = (
            transforms.Compose([transforms.Resize((self.args.img_size, self.args.img_size)), transforms.ToTensor()])
            if transforms
            else None
        )
        self.load_error = ML_IMPORT_ERROR

    def load_model(self) -> None:
        if self.model is not None:
            return
        if not torch or not ViT_seg or not get_config or not self.transform:
            raise InferenceUnavailable(f"Model dependencies are unavailable: {self.load_error}")
        if not self.model_path or not Path(self.model_path).exists():
            raise InferenceUnavailable(f"Model is not loaded. Please set MODEL_PATH before inference: {self.model_path}")

        self.config = get_config(self.args)
        self.model = ViT_seg(self.config, img_size=self.args.img_size, num_classes=self.args.num_classes).to(self.device)
        checkpoint = torch.load(self.model_path, map_location=self.device)
        state_dict = {
            key.replace("cswin_unet.", "mmrsg_unet.").replace("MSCA", "msdc"): value
            for key, value in checkpoint.items()
        }
        self.model.load_state_dict(state_dict, strict=False)
        self.model.eval()

    def is_available(self) -> bool:
        try:
            self.load_model()
            return True
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        model_path = Path(self.model_path) if self.model_path else None
        return {
            "dependencies_ready": not bool(self.load_error),
            "dependency_error": self.load_error,
            "model_path": str(model_path) if model_path else "",
            "model_file_exists": bool(model_path and model_path.exists()),
            "model_loaded": self.model is not None,
            "device": str(self.device),
        }

    def preprocess(self, image_bytes_list: list[bytes]) -> tuple[list[Any], list[tuple[int, int]], Any]:
        if Image is None or torch is None or self.transform is None:
            raise InferenceUnavailable(f"Model dependencies are unavailable: {self.load_error}")

        images = []
        original_sizes = []
        for image_bytes in image_bytes_list:
            image = Image.open(io.BytesIO(image_bytes))
            if image.mode != "RGB":
                image = image.convert("RGB")
            images.append(image)
            original_sizes.append(image.size)

        if not images:
            raise ValueError("未接收到图片")

        tensor_list = [self.transform(image) for image in images]
        return images, original_sizes, torch.stack(tensor_list).to(self.device)

    def predict_batch(self, batch_tensor: Any, inference_mode: str = "accurate") -> np.ndarray:
        self.load_model()
        if inference_mode == "fast" and getattr(self.device, "type", "") == "cuda":
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                with torch.no_grad():
                    output = self.model(batch_tensor)
        else:
            with torch.no_grad():
                output = self.model(batch_tensor)
        preds = output[0] if isinstance(output, list) else output
        return torch.argmax(preds, dim=1).cpu().numpy()

    def compute_metrics(self, pred_mask: np.ndarray) -> list[dict[str, Any]]:
        total_pixels = pred_mask.shape[0] * pred_mask.shape[1]
        metrics = []
        for index in range(1, self.args.num_classes):
            pixel_count = int(np.sum(pred_mask == index))
            if pixel_count > 0:
                metrics.append(
                    {
                        "organ": CLASS_NAMES[index],
                        "pixel_count": pixel_count,
                        "percentage": f"{(pixel_count / total_pixels) * 100:.2f}%",
                    }
                )
        return metrics

    def postprocess(
        self,
        *,
        image: Any,
        pred_mask: np.ndarray,
        original_size: tuple[int, int],
        alpha: float,
    ) -> tuple[Any, Any, list[dict[str, Any]]]:
        color_mask = COLORS[pred_mask]
        mask_image = Image.fromarray(color_mask).resize(original_size, Image.NEAREST)
        overlay_image = Image.blend(image, mask_image, alpha=alpha)
        return mask_image, overlay_image, self.compute_metrics(pred_mask)

    def save_png(self, image: Any, object_key: str) -> str:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        object_store.save_bytes(object_key, buffer.getvalue())
        return object_store.url_for(object_key)

    def image_to_base64_data_url(self, image: Any) -> str:
        import base64

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode('utf-8')}"

    def run(
        self,
        *,
        files: list[tuple[str, bytes]],
        alpha: float = 0.4,
        model_name: str = "MMRSG-UNet epoch_241.pth",
        model_preset: str = "abdomen",
        inference_mode: str = "accurate",
        case_id: str | None = None,
        task_id: str | None = None,
        include_base64: bool = False,
        persist_outputs: bool = True,
        progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        started = time.time()
        filenames = [Path(name).name for name, _ in files]
        image_bytes = [content for _, content in files]
        progress_callback = progress_callback or (lambda progress, message: None)

        progress_callback(10, "正在读取与预处理影像")
        images, original_sizes, batch_tensor = self.preprocess(image_bytes)

        progress_callback(35, "正在执行 MMRSG-UNet 推理")
        pred_masks = self.predict_batch(batch_tensor, inference_mode=inference_mode)

        results = []
        for index, image in enumerate(images):
            filename = filenames[index]
            progress = 60 + int(((index + 1) / len(images)) * 25)
            progress_callback(progress, f"正在后处理 {filename}")
            mask_image, overlay_image, metrics = self.postprocess(
                image=image,
                pred_mask=pred_masks[index],
                original_size=original_sizes[index],
                alpha=alpha,
            )

            item: dict[str, Any] = {
                "filename": filename,
                "metrics": metrics,
            }
            if persist_outputs:
                output_prefix = f"segmentations/{case_id or 'sync'}/{task_id or str(int(started))}/{index + 1:03d}"
                item["mask_url"] = self.save_png(mask_image, f"{output_prefix}_mask.png")
                item["overlay_url"] = self.save_png(overlay_image, f"{output_prefix}_overlay.png")
            if include_base64:
                item["image_base64"] = self.image_to_base64_data_url(overlay_image)
            results.append(item)

        progress_callback(95, "正在生成结构化指标")
        return {
            "status": "success",
            "case_id": case_id,
            "task_id": task_id,
            "model_name": model_name,
            "model_preset": model_preset,
            "inference_mode": inference_mode,
            "latency_seconds": round(time.time() - started, 3),
            "results": results,
        }


inference_service = InferenceService()
