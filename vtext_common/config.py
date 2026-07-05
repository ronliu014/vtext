"""Shared TOML config loading utility."""
import sys
from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "vtext"


def load_toml(path: Path) -> dict:
    """Load a TOML file. Returns empty dict if file does not exist."""
    if not path.exists():
        return {}
    if sys.version_info >= (3, 11):
        import tomllib
        with path.open("rb") as f:
            return tomllib.load(f)
    else:
        try:
            import tomli
            with path.open("rb") as f:
                return tomli.load(f)
        except ImportError:
            raise RuntimeError(
                f"Python < 3.11 requires 'tomli' to read config files: "
                f"pip install tomli"
            )
