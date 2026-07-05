# vtext 总体设计

> 客户端-服务器分离架构的音视频转写工具

---

## 1. 总体架构

```
┌─────────────────────┐                    ┌──────────────────────┐
│   vtext (client)    │   HTTP/REST API    │   vtext-server       │
│                     │ ──────────────────> │                      │
│  - CLI 命令行        │  上传 WAV 音频      │  - whisper.cpp       │
│  - ffmpeg（提取音频）│  (>100MB 则 zstd)  │  - 模型管理           │
│  - 批量处理          │                    │  - FastAPI           │
│  - requests + click │  SSE 推送进度       │  - 任务队列 + 多进程  │
└─────────────────────┘ <────────────────── └──────────────────────┘
```

**音频处理流程：**
1. 客户端用 ffmpeg 将视频/音频提取为 WAV（16kHz, mono）
2. 若 WAV ≥ 100MB，用 zstd 压缩后上传，form field 携带 `encoding: zstd`
3. server 收到后按需解压，直接将 WAV 交给 whisper.cpp

---

## 2. 项目结构

```
vtext/
├── docs/                           # 文档目录（见 docs/README.md）
├── pyproject.toml
│
├── vtext_server/                   # server 包
│   ├── __init__.py
│   ├── __main__.py                 # vtext-server 命令入口
│   ├── app.py                      # FastAPI 应用
│   ├── transcriber.py              # whisper.cpp 调用
│   ├── models.py                   # 模型下载和管理
│   ├── queue.py                    # 任务队列 + 多进程 worker
│   ├── config.py                   # 配置管理
│   └── errors.py                   # 异常定义
│
├── vtext_client/                   # client 包
│   ├── __init__.py
│   ├── __main__.py                 # vtext 命令入口
│   ├── audio.py                    # 音频提取（ffmpeg）+ zstd 压缩
│   ├── api.py                      # HTTP 客户端
│   ├── cli.py                      # 命令行参数解析
│   ├── batch.py                    # 批量处理
│   └── errors.py                   # 异常定义
│
├── vtext_common/                   # 共享代码
│   ├── __init__.py
│   ├── formats.py                  # txt/srt/vtt 格式处理
│   └── types.py                    # 共享数据类型
│
└── tests/
    ├── test_server/
    ├── test_client/
    └── test_integration/
```

---

## 3. 命令设计

### vtext-server（服务端）

```sh
vtext-server                                      # 默认 127.0.0.1:8000
vtext-server --host 0.0.0.0 --port 9000          # 监听所有网卡
vtext-server --model base                         # 预加载指定模型
vtext-server --model /data/models/ggml-large-v3.bin
vtext-server --binary /opt/whisper.cpp/main       # 指定 whisper.cpp 路径
vtext-server --workers 4                          # 并发 worker 数
```

**配置优先级：** 命令行参数 → 环境变量（`WHISPER_CPP_BIN`, `WHISPER_CPP_MODEL`） → `~/.config/vtext/server.toml` → 默认值

### vtext（客户端）

```sh
vtext video.mp4                                   # 默认连接 127.0.0.1:8000
vtext video.mp4 --server http://192.168.1.100:8000
vtext video.mp4 -o output.txt
vtext video.mp4 -f srt -o video.srt              # 生成字幕
vtext video.mp4 -l en                            # 指定语言
vtext folder/ -j 4 -f srt                        # 批量处理
vtext --check-server                             # 查看 server 状态
```

**配置优先级：** `--server` → `VTEXT_SERVER_URL` → `~/.config/vtext/client.toml` → `http://127.0.0.1:8000`

---

## 4. 并发模型

server 使用**任务队列 + 多进程 worker** 充分利用多核：

- 每个 worker 进程独占一个 CPU 核心，运行一个 whisper.cpp 实例
- 默认 worker 数 = CPU 核心数，可通过 `--workers` 覆盖
- 队列满时返回 `429` 及队列状态，由客户端自决是等待还是放弃

```
请求 → FastAPI → 任务队列 → worker-1 (whisper.cpp)
                           → worker-2 (whisper.cpp)
                           → worker-N (whisper.cpp)
```

---

## 5. 模型管理

- 默认模型在 server 启动时加载，常驻内存
- 每个请求可通过 `model` 参数指定模型，server 按需切换
- **模型切换策略**：等待当前队列清空后再切换，避免频繁切换导致吞吐下降
- 模型缓存目录：`~/.cache/vtext/models/`

---

## 6. 依赖管理

```toml
[project]
name = "vtext"
requires-python = ">=3.9"

dependencies = [
    "requests>=2.31.0",
    "click>=8.1.0",
    "zstandard>=0.21.0",
]

[project.optional-dependencies]
server = [
    "fastapi>=0.100.0",
    "uvicorn[standard]>=0.23.0",
    "python-multipart>=0.0.6",
]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.24.0",
    "ruff>=0.0.280",
]
full = ["vtext[server]"]

[project.scripts]
vtext = "vtext_client.__main__:main"
vtext-server = "vtext_server.__main__:main"
```

**安装场景：**
```sh
pip install vtext              # 仅客户端
pip install vtext[server]      # 仅服务端
pip install vtext[full,dev]    # 完整开发环境
```

---

## 7. 错误处理

### 客户端错误

```python
class VtextClientError(Exception): ...
class ServerConnectionError(VtextClientError): ...   # 连接失败
class ServerError(VtextClientError): ...             # server 返回错误
class QueueFullError(VtextClientError): ...          # 队列已满
class TimeoutError(VtextClientError): ...            # 请求超时
```

**重试策略：**
- 连接失败 / 超时 → 指数退避重试，最多 3 次
- 4xx → 不重试，直接报错
- 5xx → 重试

**用户提示示例：**
```
$ vtext video.mp4
Error: Cannot connect to vtext-server at http://127.0.0.1:8000

Possible solutions:
  1. Start the server: vtext-server
  2. Check server status: curl http://127.0.0.1:8000/health
  3. Specify different server: vtext video.mp4 --server http://other-server:8000
```

### 服务端错误

```python
class VtextServerError(Exception): ...
class TranscriptionError(VtextServerError): ...      # 转写失败
class ModelNotFoundError(VtextServerError): ...      # 模型文件不存在
class DependencyError(VtextServerError): ...         # whisper.cpp 未找到
```

---

## 8. 测试策略

```
tests/
├── test_server/
│   ├── test_transcriber.py    # whisper.cpp 调用（mock 子进程）
│   ├── test_models.py         # 模型管理
│   ├── test_queue.py          # 任务队列
│   └── test_app.py            # API 端点
│
├── test_client/
│   ├── test_audio.py          # 音频提取 + zstd 压缩
│   ├── test_api.py            # HTTP 客户端（mock HTTP）
│   ├── test_cli.py            # CLI 参数解析
│   └── test_batch.py          # 批量处理
│
└── test_integration/
    ├── test_e2e.py            # 端到端（启动 server + client 调用）
    └── test_docker.py         # Docker 集成测试
```

---

## 9. 迁移路径（从 vtext-tool）

| 模块 | vtext-tool 位置 | 新项目位置 | 改动 |
|------|----------------|-----------|------|
| audio.py | `src/vtext/` | `vtext_client/` | 移到客户端，新增 zstd 压缩 |
| transcriber.py | `src/vtext/` | `vtext_server/` | 保持不变 |
| models.py | `src/vtext/` | `vtext_server/` | 保持不变 |
| formats.py | `src/vtext/` | `vtext_common/` | 保持不变 |
| errors.py | `src/vtext/` | 各自包 | 分离为 server/client |
| cli.py | `src/vtext/` | `vtext_client/` | 重写为 API 调用 |
| batch.py | `src/vtext/` | `vtext_client/` | 改为调用 API |
| pipeline.py | `src/vtext/` | ❌ 删除 | server 内部逻辑 |
