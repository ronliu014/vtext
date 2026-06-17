# vtext API 文档

vtext-server 提供 RESTful API，异步任务通过 SSE 推送进度。

---

## 端点总览

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/transcribe` | 提交转写任务 |
| `GET` | `/jobs/{id}/stream` | SSE 流，实时推送任务进度和结果 |
| `GET` | `/jobs/{id}` | 查询任务状态（SSE 断线后恢复用） |
| `GET` | `/health` | server 健康状态 |
| `GET` | `/models` | 列出可用模型 |
| `POST` | `/models/download` | 下载模型 |

---

## POST /transcribe

提交一个转写任务。server 将任务加入队列，立即返回 `job_id`。

**请求：** `multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | binary | ✅ | WAV 文件（16kHz mono），或 zstd 压缩后的 WAV |
| `encoding` | string | 可选 | 压缩方式，目前仅支持 `zstd` |
| `language` | string | 可选 | 语言代码，如 `en`、`zh`，不填则自动检测 |
| `format` | string | 可选 | 输出格式：`txt`（默认）、`srt`、`vtt` |
| `model` | string | 可选 | 覆盖 server 默认模型，如 `base`、`large-v3` |

**客户端上传逻辑：**
1. ffmpeg 提取音频为 WAV（16kHz, mono）
2. WAV < 100MB：直接上传，不携带 `encoding`
3. WAV ≥ 100MB：zstd 压缩后上传，携带 `encoding: zstd`

**响应 201 — 任务已入队：**
```json
{
  "job_id": "a1b2c3d4",
  "status": "queued",
  "position": 2
}
```

**响应 429 — 队列已满：**
```json
{
  "error": "QueueFull",
  "message": "Queue is full",
  "queue_size": 16,
  "position": 16,
  "estimated_wait_seconds": 120
}
```
客户端收到 429 后自决：等待后重试，或直接放弃。

---

## GET /jobs/{id}/stream

SSE 长连接，server 实时推送任务进度，任务完成后关闭连接。

**事件类型：**

```
event: queued
data: {"position": 2, "estimated_wait_seconds": 60}

event: processing
data: {"progress": 45, "elapsed_seconds": 12}

event: done
data: {
  "text": "Full transcript...",
  "language": "zh",
  "duration": 125.5,
  "segments": [
    {"start": 0.0, "end": 2.5, "text": "你好世界"}
  ],
  "formatted": "1\n00:00:00,000 --> 00:00:02,500\n你好世界\n\n..."
}

event: error
data: {"error": "TranscriptionError", "message": "whisper.cpp failed: ..."}
```

**客户端处理：**
- 连接断开时，通过 `GET /jobs/{id}` 恢复状态，再重连 SSE
- 收到 `done` 或 `error` 事件后连接自动关闭

---

## GET /jobs/{id}

查询任务当前状态，用于 SSE 断线后恢复。

**响应：**
```json
{
  "job_id": "a1b2c3d4",
  "status": "processing",
  "progress": 45,
  "position": 0,
  "elapsed_seconds": 12
}
```

`status` 枚举值：`queued` | `processing` | `done` | `error`

任务完成后结果保留 10 分钟，之后自动清理。

---

## GET /health

```json
{
  "status": "ok",
  "version": "1.0.0",
  "uptime": 3600,
  "workers": {
    "total": 4,
    "busy": 2
  },
  "queue": {
    "size": 3,
    "max": 16
  },
  "model": {
    "loaded": "base",
    "switching": false
  }
}
```

---

## GET /models

```json
{
  "current": "base",
  "available": ["tiny", "tiny.en", "base", "base.en", "small", "medium", "large-v3"],
  "cached": ["base", "small"]
}
```

---

## POST /models/download

**请求：**
```json
{ "name": "small" }
```

**响应：**
```json
{
  "status": "downloading",
  "progress": 45,
  "size_mb": 466
}
```

---

## 错误响应格式

所有错误统一返回：
```json
{
  "error": "ErrorClassName",
  "message": "Human-readable description",
  "details": "Optional extra info (e.g. stderr output)"
}
```
