# vtext

音视频转写工具，基于 [whisper.cpp](https://github.com/ggerganov/whisper.cpp) 实现，采用客户端-服务器分离架构。

在低性能笔记本上使用轻量客户端，将转写任务交给远程强大服务器处理；也可以单机本地运行。

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

```sh
mkdir -p ~/.config/systemd/user/
```

创建 `~/.config/systemd/user/vtext.service`：

```ini
[Unit]
Description=vtext transcription server
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/vtext
ExecStart=/usr/bin/python3 -m vtext_server
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

```sh
systemctl --user daemon-reload
systemctl --user enable vtext
systemctl --user start vtext

# 允许服务在登出后继续运行
loginctl enable-linger $USER

# 查看状态 / 日志
systemctl --user status vtext
journalctl --user -u vtext -f
```

### 客户端配置

创建 `~/.config/vtext/client.toml`：

```toml
server_url = "http://127.0.0.1:8000"   # 远程服务器改为对应地址
default_format = "txt"                  # txt / srt / vtt
default_language = "zh"                 # 留空则自动检测
```

配置优先级：**CLI 参数 > 环境变量 > TOML 配置 > 内置默认值**

详细部署选项（Docker、环境变量、安全配置）见 [docs/deployment.md](./docs/deployment.md)。

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

详细对比见 [docs/models.md](./docs/models.md)。

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

- [docs/design.md](./docs/design.md) — 总体架构与模块设计
- [docs/api.md](./docs/api.md) — API 端点与 SSE 协议
- [docs/architecture.md](./docs/architecture.md) — 架构决策记录
- [docs/deployment.md](./docs/deployment.md) — Docker / systemd 部署指南
- [docs/models.md](./docs/models.md) — 模型选择指南与实测对比
