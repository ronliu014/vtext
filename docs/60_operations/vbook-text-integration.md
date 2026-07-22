# vBook Text Integration Runbook

This runbook shows how vBook should call vtext as a text-processing module
without importing or vendoring vtext internals.

## Preconditions

- vtext server is running and reachable.
- ffmpeg is available to the client.
- Local development uses the Anaconda `App` environment:

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m pytest tests/test_client
```

## Health Check

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m vtext_client `
  --check-server `
  --server "http://192.168.0.122:8000"
```

Expected result:

```text
Server: http://192.168.0.122:8000
Status: ok
Model:  <configured-model>
Queue:  <size>/<max>
Workers: <busy>/<total> busy
```

## Per-Lesson Bundle Command

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m vtext_client `
  "<video-path>" `
  --server "http://192.168.0.122:8000" `
  --bundle vbook `
  --output "<lesson-output-dir>" `
  --format srt `
  --language zh
```

Use one command per lesson for the first vBook integration pass.

For `--bundle vbook`, vtext always sends refine requests through the server LLM
relay. The default `auto` mode resolves to `server`; explicit
`--refine-mode direct` is rejected so the Windows CLI cannot bypass the
production server boundary. `--no-refine` is also rejected because it would
make the required bundle incomplete.

## Expected Output

```text
<lesson-output-dir>/
|-- transcript.raw.txt
|-- transcript.raw.srt
|-- transcript.clean.txt
|-- summary.md
+-- manifest.json
```

Read `manifest.json` to discover which artifacts exist. Do not guess filenames
from source video names in vBook.

## Minimal Manifest Check

```powershell
& 'D:\anaconda3\envs\App\python.exe' -c `
  "import json, pathlib; p=pathlib.Path(r'<lesson-output-dir>')/'manifest.json'; print(json.loads(p.read_text(encoding='utf-8'))['status'])"
```

Expected success status:

```text
done
```

## Failure Handling

If transcription fails, vtext exits non-zero and writes a failed manifest when
the output directory can be created:

```json
{
  "status": "failed",
  "outputs": {},
  "errors": [
    {
      "stage": "transcription",
      "code": "server_error",
      "message": "Human-readable failure summary"
    }
  ]
}
```

If refine fails, vtext keeps the raw transcript artifacts, writes fallback
`transcript.clean.txt` and `summary.md` files derived from the raw transcript,
and records a `refine` error in `errors[]`. vBook can still consume a complete
bundle while seeing the degraded refine quality in the manifest.

Fallback output is not publication-quality text. Keep the affected lesson
paused until a successful refine-only recovery clears the active refine error.

## Refine-Only Recovery

For a lesson whose raw transcript is valid, recover the existing bundle without
rerunning ASR:

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m vtext_client `
  "<lesson-output-dir>/transcript.raw.txt" `
  --server "http://192.168.0.122:8000" `
  --refine-only `
  --bundle vbook `
  --output "<lesson-output-dir>"
```

Long transcripts are split into bounded 6,000-character chunks at sentence
boundaries. Each chunk is corrected and structured through the Linux server
relay, and outputs are assembled in source order. A successful recovery records
the previous refine errors under `manifest.json recovery.previous_errors`.

Revalidate all required outputs and the manifest before changing a terminal
vBook run or removing an operator pause. Preserve the original task attempts as
audit evidence.

## Common Issues

- Server unavailable: run `--check-server`, start `vtext-server`, or change
  `--server`.
- Queue full: retry later or use a less busy server.
- Large files: client compresses WAV files at or above 100 MB, but server upload
  size and memory limits still apply.
- Refine unavailable: have `lcodex` inspect the vtext server LLM relay and its
  upstream connection to GPU Ollama. Do not route the Windows CLI directly to
  Ollama as a production workaround.
- Chinese conversion test failures: use the `App` environment because it
  includes `opencc`.

## Related Contracts

- [../20_architecture/output-contracts.md](../20_architecture/output-contracts.md)
- [../90_reference/vbook-text-integration-response.md](../90_reference/vbook-text-integration-response.md)
