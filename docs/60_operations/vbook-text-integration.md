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
  --server "http://127.0.0.1:8000"
```

Expected result:

```text
Server: http://127.0.0.1:8000
Status: ok
Model:  <configured-model>
Queue:  <size>/<max>
Workers: <busy>/<total> busy
```

## Per-Lesson Bundle Command

```powershell
& 'D:\anaconda3\envs\App\python.exe' -m vtext_client `
  "<video-path>" `
  --server "http://127.0.0.1:8000" `
  --bundle vbook `
  --output "<lesson-output-dir>" `
  --format srt `
  --language zh
```

Use one command per lesson for the first vBook integration pass.

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

If refine fails, vtext keeps the raw transcript artifacts and records a
`refine` error in `errors[]`. vBook can still consume raw text evidence.

## Common Issues

- Server unavailable: run `--check-server`, start `vtext-server`, or change
  `--server`.
- Queue full: retry later or use a less busy server.
- Large files: client compresses WAV files at or above 100 MB, but server upload
  size and memory limits still apply.
- Refine unavailable: confirm direct Ollama or server LLM relay configuration.
- Chinese conversion test failures: use the `App` environment because it
  includes `opencc`.

## Related Contracts

- [../20_architecture/output-contracts.md](../20_architecture/output-contracts.md)
- [../90_reference/vbook-text-integration-response.md](../90_reference/vbook-text-integration-response.md)

