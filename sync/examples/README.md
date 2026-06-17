# sync/examples

Reference messages — one per built-in `ops.*` type, with paired request/response.
**These are documentation only.** They do not participate in the protocol and must
never be processed as live messages (note the `examples/` location and the
`c2s_` / `s2c_` filename prefix, which differ from real message paths).

Each filename encodes: `<direction>_<seq>-<ts>-<id>.<type>.json`. In a real
exchange the file would live under `sync/c2s/` or `sync/s2c/` and be named
`<seq>-<ts>-<id>.json` (no direction prefix, no type suffix).

See `../PROTOCOL.md` for the full spec.

| Type | Direction | File |
|------|-----------|------|
| `ops.health.request`    | c2s | `c2s_000001-...ops.health.request.json` |
| `ops.health.response`   | s2c | `s2c_000001-...ops.health.response.json` |
| `ops.version.request`   | c2s | `c2s_000002-...ops.version.request.json` |
| `ops.version.response`  | s2c | `s2c_000002-...ops.version.response.json` |
| `ops.deploy.request`    | c2s | `c2s_000003-...ops.deploy.request.json` |
| `ops.deploy.response`   | s2c | `s2c_000003-...ops.deploy.response.json` |
| `ops.restart.request`   | c2s | `c2s_000004-...ops.restart.request.json` |
| `ops.restart.response`  | s2c | `s2c_000004-...ops.restart.response.json` |
| `ops.logs.request`      | c2s | `c2s_000005-...ops.logs.request.json` |
| `ops.logs.response`     | s2c | `s2c_000005-...ops.logs.response.json` |
| `ops.ack`               | s2c | `s2c_000006-...ops.ack.json` |
| `ops.error`             | s2c | `s2c_000007-...ops.error.json` |
