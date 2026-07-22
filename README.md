# vtext

音视频转写工具，基于 [whisper.cpp](https://github.com/ggerganov/whisper.cpp) 实现，采用客户端-服务器分离架构。

在低性能笔记本上使用轻量客户端，将转写任务交给远程强大服务器处理；也可以单机本地运行。

---

## 生产部署与协同边界

vtext 是一个同时包含 client 和 server 的独立项目。生产环境中的组件、部署位置与 agent 责任固定如下：

| 范围 | 部署位置 | 责任 agent | 职责 |
|------|----------|------------|------|
| vtext client / CLI | Windows `192.168.5.1` | `wcodex` | 提供 CLI，提取音频、调用 vtext server，并生成本地 artifact |
| vtext server | Linux `192.168.0.122` | `lcodex` | 运行转写服务，管理队列、运行配置、日志、服务部署和上游模型调用 |
| vtext 内部通信 | 本仓库 [`sync/`](./sync/) | `wcodex` ↔ `lcodex` | 使用 Git 作为传输层，按 [`vtext-sync/1`](./sync/PROTOCOL.md) 在 Windows client 端与 Linux server 端之间传递运维和控制消息 |

生产调用链路为：

```text
vBook（外部项目）
  -> Windows 192.168.5.1 上的 vtext CLI（wcodex）
  -> Linux 192.168.0.122 上的 vtext server（lcodex）
  -> server 所管理的上游服务，例如 192.168.0.33:7866 上的 GPU Ollama
```

边界规则：

- `vBook` 是外部项目，只能通过稳定的 vtext CLI、HTTP API 和 artifact contract 使用 vtext；不得 import 或 vendor vtext 内部代码。
- `sync/` 是 **vtext 项目内部**的 Windows/Linux 双端通信协议，不是跨项目邮箱，也不替代转写所使用的 HTTP/SSE 数据通道。
- [`vsync`](https://github.com/ronliu014/vsync) 是 **跨项目**通信协议，使用 Git 作为传输层，负责 vtext、vBook、vision 等项目之间的 durable mailbox 通信。
- `sync` 与 `vsync` 名称相近但作用域不同，不得混用：内部双端协作用 `sync/`，跨项目协作用 `vsync`。
- 生产环境的 GPU/Ollama 上游连接由 vtext server 管理；Windows client 和 vBook 不应绕过 `192.168.0.122` 直接承担该连接。

---

## 架构

```
┌─────────────────────┐                    ┌──────────────────────┐
│   vtext (client)    │   上传 WAV 音频     │   vtext-server       │
│                     │ ──────────────────> │                      │
│  - CLI              │  (>100MB 则 zstd)  │  - whisper.cpp       │
│  - ffmpeg 提取音频   │                    │  - 任务队列 + 多进程  │
│  - zstd 压缩        │  SSE 推送进度       │  - 模型管理           │
└─────────────────────┘ <────────────────── └──────────────────────┘
```

客户端负责将视频/音频提取为 WAV，通过 HTTP 上传到 server，server 用 whisper.cpp 转写并通过 SSE 实时推送进度。

---

## 安装

**客户端（轻量，仅需 ffmpeg）：**
```sh
pip install vtext
```

**服务端：**
```sh
pip install "vtext[server]"
```

**完整开发环境：**
```sh
pip install -e ".[full,dev]"
```

客户端依赖系统安装的 `ffmpeg`，服务端依赖 `whisper.cpp` 二进制。

---

## 部署

### 服务端前置依赖：whisper.cpp

服务端需要 whisper.cpp 二进制和模型文件：

```sh
# 编译 whisper.cpp（需要 cmake、gcc/clang）
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
cmake -B build -DCMAKE_BUILD_RPATH_USE_ORIGIN=ON
cmake --build build --target whisper-cli -j$(nproc)

# 下载模型（中文推荐 small 及以上）
./models/download-ggml-model.sh small
```

### 服务端配置

创建 `~/.config/vtext/server.toml`（所有字段均有默认值，按需修改）：

```toml
host = "127.0.0.1"
port = 8000
workers = 4
whisper_binary = "/path/to/whisper.cpp/build/bin/whisper-cli"
model = "small"
models_dir = "~/.cache/vtext/models"
```

### systemd 用户级服务（推荐，开机自启）

使用项目自带的管理脚本：

```sh
scripts/vtext-service.sh install   # 安装并 enable 服务（开机自启）
scripts/vtext-service.sh start     # 启动
scripts/vtext-service.sh stop      # 停止
scripts/vtext-service.sh restart   # 重启
scripts/vtext-service.sh status    # 查看 systemd 状态 + health API 信息
scripts/vtext-service.sh logs 100  # 查看最近 100 行日志（默认 50）
scripts/vtext-service.sh follow    # 实时追踪日志
scripts/vtext-service.sh uninstall # 停止并删除服务
```

脚本会自动执行 `loginctl enable-linger`，确保服务在用户登出后继续运行。

### 客户端配置

创建 `~/.config/vtext/client.toml`：

```toml
server_url = "http://127.0.0.1:8000"   # 远程服务器改为对应地址
default_format = "txt"                  # txt / srt / vtt
default_language = "zh"                 # 留空则自动检测
```

配置优先级：**CLI 参数 > 环境变量 > TOML 配置 > 内置默认值**

详细部署选项（Docker、环境变量、安全配置）见 [docs/60_operations/deployment.md](./docs/60_operations/deployment.md)。

---

## 快速上手

### 单机本地使用

```sh
# 终端 1：启动 server
vtext-server --model small

# 终端 2：转写
vtext video.mp4                        # 输出到终端
vtext video.mp4 -o output.txt          # 输出到文件
vtext video.mp4 -f srt -o video.srt   # 生成字幕
vtext video.mp4 -l en                 # 指定语言
```

### 连接远程服务器

```sh
export VTEXT_SERVER_URL=http://192.168.1.100:8000
vtext video.mp4
```

### 批量处理

```sh
vtext folder/ -j 4 -f srt   # 4 个并发任务
```

### 检查 server 状态

```sh
vtext --check-server
```

---

## vtext-server 选项

```sh
vtext-server                                        # 默认 127.0.0.1:8000
vtext-server --host 0.0.0.0 --port 9000            # 监听所有网卡
vtext-server --model large-v3                       # 指定模型
vtext-server --workers 4                            # 并发 worker 数（默认 = CPU 核心数）
vtext-server --binary /opt/whisper.cpp/main         # 指定 whisper.cpp 路径
vtext-server --log-dir /var/log/vtext               # 日志目录（不填则只输出到控制台）
vtext-server --log-level DEBUG                      # 日志级别：DEBUG / INFO / WARNING / ERROR
```

日志文件按天切割，保留 30 天，文件名格式：`vtext-server.YYYY-MM-DD.log`。

日志目录也可在 `server.toml` 中配置：

```toml
log_dir = "~/.local/share/vtext/logs"
log_level = "INFO"
```

---

## 支持的模型

实测数据（CPU，测试音频 21 秒中文 / 11 秒英文）：

| 模型 | 大小 | 中文（自动检测）| 中文耗时 | 英文耗时 | 推荐场景 |
|------|------|----------------|---------|---------|---------|
| `tiny` | 75MB | ❌ 识别为英文 | — | <1s | 仅限英文快速原型 |
| `base` | 142MB | ❌ 错误率高 | — | ~2s | 仅限英文 |
| `small` | 466MB | ✅ 自动识别 | ~11s | ~4s | **中文推荐最低配置** |
| `medium` | 1.5GB | ⚠️ 须加 `-l zh` | ~32s | — | 高精度，需指定语言 |
| `large-v3` | 3.1GB | ✅ 自动识别 | ~65s | ~51s | 最高精度 |

**中文必须用 `small` 及以上**；`medium` 不指定语言会输出英文翻译，需加 `-l zh`；`large-v3` 修正了这一问题，自动检测恢复正常。

详细对比见 [docs/60_operations/models.md](./docs/60_operations/models.md)。

---

## 输出格式

| 格式 | 说明 |
|------|------|
| `txt` | 纯文本（默认） |
| `srt` | SubRip 字幕 |
| `vtt` | WebVTT 字幕 |

---

## 文档

详细设计文档见 [docs/](./docs/README.md)：

- [docs/00_project/overview.md](./docs/00_project/overview.md) — 项目定位与边界
- [docs/20_architecture/design.md](./docs/20_architecture/design.md) — 总体架构与模块设计
- [docs/20_architecture/api.md](./docs/20_architecture/api.md) — API 端点与 SSE 协议
- [docs/20_architecture/architecture.md](./docs/20_architecture/architecture.md) — 架构决策记录
- [docs/20_architecture/output-contracts.md](./docs/20_architecture/output-contracts.md) — 输出文件与 manifest 合同
- [docs/60_operations/deployment.md](./docs/60_operations/deployment.md) — Docker / systemd 部署指南
- [docs/60_operations/models.md](./docs/60_operations/models.md) — 模型选择指南与实测对比
- [docs/60_operations/vbook-text-integration.md](./docs/60_operations/vbook-text-integration.md) — vBook 文本集成运行手册

### 文档分层规范

`docs/` 采用轻量编号分层，和兄弟项目 vBook 的文档组织方式保持兼容：

| 层级 | 用途 |
|------|------|
| `00_project/` | 项目概览、状态、任务板 |
| `20_architecture/` | 架构、API、输出合同、长期技术决策 |
| `40_development/` | 本地开发环境、测试命令、协作规则 |
| `60_operations/` | 部署、模型、运行手册、故障排查 |
| `70_progress/` | 日期化进展记录、阶段总结 |
| `90_reference/` | 跨项目请求/响应、外部约束、参考资料 |

新增文档时优先放入对应层级，不再把设计、部署、合同和进展记录混放在 `docs/` 根目录。

### 跨项目协同规范

vtext、vBook、vision 是兄弟项目，分工不同，通过稳定边界协作：

- **vtext** 负责音视频转写、文本纠错、文本摘要和可机器读取的文本产物。
- **vision** 负责图像/帧理解、OCR、视觉描述和视觉证据产物。
- **vBook** 负责编排课程知识生产流程，融合 vtext 文本证据和 vision 视觉证据，生成预览输出和未来的 vault 写回。

长期集成边界只能是 CLI、HTTP API、JSON/Markdown artifact contract 和文档化 runbook。vBook 不应 import 或 vendor vtext 内部 Python 模块；vtext 也不应依赖 vBook 或 vision 的内部实现。

vBook 调用 vtext 的当前稳定入口见 [docs/60_operations/vbook-text-integration.md](./docs/60_operations/vbook-text-integration.md)。输出文件和 `manifest.json` 合同见 [docs/20_architecture/output-contracts.md](./docs/20_architecture/output-contracts.md)。跨项目请求/响应记录保存在 [docs/90_reference/](./docs/90_reference/)。
