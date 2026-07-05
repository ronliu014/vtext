# vtext-sync 协议规范 v1

`sync/` 是一个**提交进 git 的文件信箱**,用于 vtext **client 与 server 之间的全双工带外通信**。
它**不替代** HTTP/SSE 的转录主通道,而是一条控制/运维旁路:即使你够不着服务器的网络端口,
只要双方都能 `git pull` / `git push` 同一个仓库,就能互发消息。

> **触发是人工的。** 本协议**不包含**任何守护进程、轮询或文件监听。
> 发消息 = 写文件后 `git commit && git push`;收消息 = `git pull` 后读目录。
> 何时收发由使用者自己决定。

---

## 1. 设计铁律:单写者 + 只追加

git 冲突只发生在「两个分支修改同一个文件」时。本协议通过**强制每个路径只有一个作者、消息文件只新增不修改**,
让 `git pull` 永远是无冲突的自动合并。

| 路径 | 唯一作者 | 允许的操作 |
|------|---------|-----------|
| `sync/c2s/*.json` | **client** | 只新增。文件一旦提交,永不修改、永不删除 |
| `sync/s2c/*.json` | **server** | 只新增。文件一旦提交,永不修改、永不删除 |
| `sync/state/client.json` | **client** | 只有 client 修改 |
| `sync/state/server.json` | **server** | 只有 server 修改 |

> ⚠️ 违反铁律(例如 server 去删 `c2s/` 里的文件,或两端都写 `state/` 的同一个文件)
> 会立刻引入合并冲突。请严格遵守「谁的目录谁写」。

---

## 2. 目录布局

```
sync/
├── PROTOCOL.md               # 本文件
├── schema/
│   └── envelope.schema.json  # 信封的 JSON Schema(双方校验用)
├── c2s/                      # client → server 信道(client 唯一作者)
│   └── <seq>-<ts>-<id>.json
├── s2c/                      # server → client 信道(server 唯一作者)
│   └── <seq>-<ts>-<id>.json
├── state/
│   ├── client.json           # client 的游标 + 状态(client 唯一作者)
│   └── server.json           # server 的游标 + 状态(server 唯一作者)
└── examples/                 # 每种内置消息的示例(只读参考,不参与运行)
```

- `c2s` = **c**lient **to** **s**erver,`s2c` = **s**erver **to** **c**lient。
- 「全双工」体现在两个方向各有独立信道,互不阻塞。

---

## 3. 文件名约定

```
<seq>-<ts>-<id>.json
```

| 段 | 含义 | 例 |
|----|------|----|
| `seq` | 该**方向内**单调递增的 6 位零填充序号 | `000007` |
| `ts`  | UTC 时间戳,紧凑 ISO-8601(`YYYYMMDDTHHMMSSZ`) | `20260617T134500Z` |
| `id`  | 8 位十六进制随机 id,与信封内 `id` 字段一致 | `a1b2c3d4` |

完整示例:`sync/c2s/000007-20260617T134500Z-a1b2c3d4.json`

- 文件名可直接字典序排序 = 时间顺序。
- `seq` 由发送方决定:取该目录现有最大 `seq` + 1,并写回自己的 `state` 文件(见 §6)。
- `id` 用于请求/响应关联,全局唯一即可。

---

## 4. 信封格式

每个消息文件是一个 JSON 对象,结构如下(完整约束见 `schema/envelope.schema.json`):

```json
{
  "protocol": "vtext-sync/1",
  "id": "a1b2c3d4",
  "seq": 7,
  "ts": "2026-06-17T13:45:00Z",
  "from": "client",
  "to": "server",
  "type": "ops.version.request",
  "in_reply_to": null,
  "expects_reply": true,
  "payload": {}
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `protocol` | string | 固定 `"vtext-sync/1"`。大版本不兼容时递增 |
| `id` | string | 本消息唯一 id(8 位 hex),与文件名 `<id>` 段一致 |
| `seq` | integer | 本方向单调序号,与文件名 `<seq>` 段一致 |
| `ts` | string | 消息创建时间,UTC ISO-8601 |
| `from` | string | `"client"` 或 `"server"` |
| `to` | string | `"client"` 或 `"server"` |
| `type` | string | 点分命名空间的消息类型,见 §5。**可无限扩展** |
| `in_reply_to` | string \| null | 若本消息是对某请求的响应,填该请求的 `id`;否则 `null` |
| `expects_reply` | boolean | 发送方是否期待一条响应 |
| `payload` | object | 与 `type` 相关的内容。无内容时为 `{}` |

**扩展性**:新增能力只需定义新的 `type` 和对应 `payload`,无需改动信封或协议版本。
例如未来要把转录任务也走 git,加一个 `transcribe.request` 即可,协议本身不动。

**关联语义**:请求/响应靠 `id` ↔ `in_reply_to` 配对,而**不是**靠目录或文件名配对。
一条请求可以有 0 或多条响应(如 `ops.logs` 可分页多发)。

---

## 5. 内置消息类型(第一批)

所有内置运维消息位于 `ops.*` 命名空间。请求 `*.request` 由 client 发出写入 `c2s/`,
响应 `*.response` 由 server 发出写入 `s2c/` 且 `in_reply_to` 指向请求 `id`。

### 5.1 `ops.health` — 健康检查
**请求** `ops.health.request`,`payload: {}`
**响应** `ops.health.response`:
```json
{
  "status": "ok",
  "uptime_seconds": 11667,
  "workers": { "total": 2, "busy": 0 },
  "queue": { "size": 0, "max": 16 },
  "model": { "loaded": "small" }
}
```

### 5.2 `ops.version` — 版本信息
**请求** `ops.version.request`,`payload: {}`
**响应** `ops.version.response`:
```json
{
  "version": "0.1.3",
  "git_commit": "1254fea",
  "git_branch": "main",
  "model": "small"
}
```

### 5.3 `ops.deploy` — 拉取代码并重启
**请求** `ops.deploy.request`:
```json
{ "git_ref": "main" }
```
`git_ref` 可选,默认 `"main"`。
**响应** `ops.deploy.response`:
```json
{
  "ok": true,
  "previous_commit": "b332b31",
  "pulled_commit": "1254fea",
  "restarted": true,
  "note": "pulled and restarted via vtext-service.sh"
}
```

### 5.4 `ops.restart` — 仅重启(不拉代码)
**请求** `ops.restart.request`:
```json
{ "strategy": "graceful" }
```
`strategy` 可选,`"graceful"`(默认)或 `"force"`。
**响应** `ops.restart.response`:
```json
{ "ok": true, "accepted": true, "note": "graceful restart scheduled" }
```

### 5.5 `ops.logs` — 拉取服务器日志片段
**请求** `ops.logs.request`:
```json
{ "lines": 100, "level": "INFO", "since": "2026-06-17T13:00:00Z" }
```
所有字段可选:`lines` 默认 100、**上限 1000**(防止撑爆 git 历史);
`level` 过滤级别;`since` 只取该时刻之后的日志。
**响应** `ops.logs.response`:
```json
{
  "truncated": false,
  "lines": [
    "2026-06-17 13:45:01 INFO vtext.worker job start job_id=4c1fd2ce ...",
    "2026-06-17 13:45:31 INFO vtext.worker job done  job_id=4c1fd2ce ..."
  ]
}
```

### 5.6 通用 `ack` / `error`
任意一方可回 `ack`(已收到/已处理,无数据)或 `error`:
```json
{ "code": "unsupported_type", "message": "unknown type 'ops.frobnicate'" }
```
常见 `code`:`unsupported_type`、`bad_payload`、`internal_error`、`unauthorized`。
**向前兼容**:收到无法识别的 `type` 时,接收方应回 `error` `{code:"unsupported_type"}` 而非崩溃。

---

## 6. 状态文件(游标)

每一端用自己的 state 文件记录「我已经处理到对方信道的哪条序号」以及「我自己已发出的最大序号」。
这样收消息时只需处理 `seq` 大于游标的文件,处理完推进游标。

`sync/state/client.json`(client 唯一作者):
```json
{
  "owner": "client",
  "protocol": "vtext-sync/1",
  "last_sent_seq": 7,
  "last_processed_peer_seq": 3,
  "updated_at": "2026-06-17T14:01:00Z"
}
```

`sync/state/server.json`(server 唯一作者):
```json
{
  "owner": "server",
  "protocol": "vtext-sync/1",
  "last_sent_seq": 3,
  "last_processed_peer_seq": 7,
  "updated_at": "2026-06-17T14:00:12Z"
}
```

| 字段 | 含义 |
|------|------|
| `last_sent_seq` | 我在**自己方向**(client→c2s / server→s2c)已发出的最大 seq |
| `last_processed_peer_seq` | 我已处理的**对方方向**最大 seq;下次只看比它大的文件 |

> 幂等:即使重复处理同一条消息也应安全。游标只是优化,不是正确性的唯一保证。

---

## 7. 手动收发流程

### 发送(以 client 发 `ops.version.request` 为例)
1. `git pull`(拿到最新 `c2s/` 以正确计算下一个 seq)。
2. 计算 `seq` = `c2s/` 现有最大序号 + 1(或读 `state/client.json` 的 `last_sent_seq` + 1)。
3. 生成 `id`(8 位 hex)和 `ts`(当前 UTC)。
4. 写文件 `sync/c2s/000008-<ts>-<id>.json`,内容按 §4 信封填好。
5. 更新 `sync/state/client.json` 的 `last_sent_seq` 和 `updated_at`。
6. 提交并推送:
   ```sh
   git add sync/c2s sync/state/client.json
   git commit -m "sync: ops.version.request (id=<id>)"
   git push
   ```

### 接收(server 侧处理 client 的请求)
1. `git pull`。
2. 列出 `sync/c2s/` 中 `seq` > `state/server.json.last_processed_peer_seq` 的文件,按 `seq` 升序。
3. 逐条处理。若 `expects_reply` 为真,生成一条响应写入 `sync/s2c/`,
   `in_reply_to` = 请求的 `id`,`seq` 取 s2c 方向的下一个序号。
4. 更新 `sync/state/server.json`:推进 `last_processed_peer_seq`,递增 `last_sent_seq`。
5. 提交并推送:
   ```sh
   git add sync/s2c sync/state/server.json
   git commit -m "sync: reply ops.version.response (in_reply_to=<id>)"
   git push
   ```

### client 取回响应
1. `git pull`。
2. 在 `sync/s2c/` 找 `in_reply_to` == 你之前请求 `id` 的文件。
3. 处理后更新 `state/client.json.last_processed_peer_seq`,commit/push。

> 若 `git push` 因对方刚推送而被拒:`git pull` 后**因铁律不会有冲突**,直接重新 `push` 即可。

---

## 8. 归档与清理(可选)

为防止 `c2s/`、`s2c/` 无限增长,可周期性归档。归档**仍受铁律约束**:
只能由该目录的作者移动**自己**的旧文件(例如 client 把 `c2s/` 的旧消息 `git mv` 到 `sync/archive/c2s/`)。
对方不得触碰。归档是可选优化,不影响协议正确性。

---

## 9. ⚠️ 安全边界(务必阅读)

`ops.deploy` 和 `ops.restart` 让「能 push 到本仓库的人」可以在服务器上**执行命令(拉代码、重启进程)**,
这等价于**远程代码执行能力**。请理解以下边界:

- **人在回路**:由于收消息靠人工 `git pull` + 手动处理,服务器操作者是最后一道闸——
  不会有任何后台进程自动执行 `ops.deploy`。这是有意为之的安全特性,**不要**加自动轮询来绕过它。
- **仓库写权限 = 命令执行权限**:若本仓库是公开的、或允许不受信任者 push,
  **不要**在服务器侧启用 `ops.deploy`/`ops.restart` 的处理逻辑,或必须先加消息签名校验(本 v1 未内置)。
- **日志可能含敏感信息**:`ops.logs.response` 会把服务器日志写进 git 历史(永久留存)。
  确认日志中无密钥、令牌、个人信息后再发送;必要时在服务器侧做脱敏。
- **不要把音频/大文件塞进 sync/**:会永久撑大仓库历史。转录主通道仍走 HTTP。

---

## 10. 版本

- 当前协议版本:`vtext-sync/1`。
- 不兼容变更时递增 `protocol`(如 `vtext-sync/2`),双方据此拒绝或适配。
- 新增 `type` / `payload` 字段属于兼容扩展,不需要升大版本。
