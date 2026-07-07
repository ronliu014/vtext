# Development Environment

## Local Windows Environment

Use the Anaconda `App` environment for local development:

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m pytest
& 'D:\anaconda3\envs\App\python.exe' -m pytest tests/test_client
& 'D:\anaconda3\envs\App\python.exe' -m vtext_client video.mp4
```

Prefer invoking the interpreter directly. In this shell, `conda run` can hit
Windows quoting or conda temporary-file behavior.

The `App` environment includes `opencc`. Tests in
`tests/test_client/test_refine.py` depend on it for
Traditional-to-Simplified Chinese conversion.

## Legacy Linux/WSL Notes

Some older project instructions reference:

```text
/mnt/data/profile/.pyenv/versions/3.13.2/bin/python3
```

Keep those notes for Linux-style environments, but on this Windows workstation
the Anaconda `App` environment is the expected development path.

## Useful Commands

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m pytest tests/test_client
& 'D:\anaconda3\envs\App\python.exe' -m pytest tests/test_common
& 'D:\anaconda3\envs\App\python.exe' -m pytest tests/test_server
```

Linting currently uses `ruff`:

```powershell
ruff check .
```

