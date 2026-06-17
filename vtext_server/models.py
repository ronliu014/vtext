"""Model download and management."""
from pathlib import Path

from .config import ServerConfig
from .errors import ModelNotFoundError

# Known whisper.cpp GGML model filenames
MODEL_FILES = {
    "tiny":       "ggml-tiny.bin",
    "tiny.en":    "ggml-tiny.en.bin",
    "base":       "ggml-base.bin",
    "base.en":    "ggml-base.en.bin",
    "small":      "ggml-small.bin",
    "small.en":   "ggml-small.en.bin",
    "medium":     "ggml-medium.bin",
    "medium.en":  "ggml-medium.en.bin",
    "large-v3":   "ggml-large-v3.bin",
}

MODEL_SIZES_MB = {
    "tiny": 75, "tiny.en": 75,
    "base": 142, "base.en": 142,
    "small": 466, "small.en": 466,
    "medium": 1500, "medium.en": 1500,
    "large-v3": 3100,
}

BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"


def resolve_model_path(model: str, config: ServerConfig) -> Path:
    """Return the absolute path to a model file, raising if not found."""
    # Already an absolute path
    p = Path(model)
    if p.is_absolute():
        if not p.exists():
            raise ModelNotFoundError(f"Model file not found: {p}")
        return p

    # Named model
    filename = MODEL_FILES.get(model)
    if filename is None:
        raise ModelNotFoundError(f"Unknown model name: {model!r}")

    path = config.models_dir / filename
    if not path.exists():
        raise ModelNotFoundError(
            f"Model '{model}' not found at {path}. "
            f"Run: vtext-server model download {model}"
        )
    return path


def list_available() -> list:
    return list(MODEL_FILES.keys())


def list_cached(config: ServerConfig) -> list:
    cached = []
    for name, filename in MODEL_FILES.items():
        if (config.models_dir / filename).exists():
            cached.append(name)
    return cached


def download(name: str, config: ServerConfig) -> Path:
    """Download a named model into models_dir. Returns the local path."""
    import urllib.request

    if name not in MODEL_FILES:
        raise ModelNotFoundError(f"Unknown model name: {name!r}")

    filename = MODEL_FILES[name]
    dest = config.models_dir / filename
    config.models_dir.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        return dest

    url = f"{BASE_URL}/{filename}"
    urllib.request.urlretrieve(url, dest)
    return dest
