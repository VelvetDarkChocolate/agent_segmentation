import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


def load_local_env(env_path: Path | None = None) -> None:
    path = env_path or ROOT_DIR / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()


@dataclass(frozen=True)
class Settings:
    app_version: str = os.getenv("APP_VERSION", "0.2.0")
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{ROOT_DIR / 'data' / 'app.db'}")
    object_store_dir: Path = Path(os.getenv("OBJECT_STORE_DIR", str(ROOT_DIR / "object_store")))
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", str(ROOT_DIR / "uploads")))
    model_path: str = os.getenv("MODEL_PATH", str(ROOT_DIR / "model" / "epoch_241.pth"))
    llm_api_key: str = os.getenv("LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY", "")
    llm_base_url: str = (os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    llm_model: str = os.getenv("LLM_MODEL") or "deepseek-v4-flash"


settings = Settings()

