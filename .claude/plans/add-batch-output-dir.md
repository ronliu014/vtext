# Add `--output` support for batch mode

## Problem

Current batch mode hardcodes output to `<input_dir>/text`, mixing input and output in the same parent directory. Users cannot specify an independent output root. This forces workarounds (custom driver scripts) when clean separation is needed.

## Proposed Solution

Add optional `output_dir` parameter to `batch_transcribe()` and wire CLI's existing `--output` flag to batch mode. When specified, mirror input directory hierarchy under the output root; when omitted, preserve current behavior for backward compatibility.

## Design

### 1. Core changes

**`vtext_client/batch.py::batch_transcribe()`**
- Add optional parameter: `output_dir: Path | None = None`
- Line 47 logic becomes:
  ```python
  if output_dir is not None:
      text_dir = output_dir
  else:
      text_dir = directory / "text"  # current behavior
  text_dir.mkdir(parents=True, exist_ok=True)
  ```
- `_process_one()` already accepts separate `base_dir` / `text_dir` and mirrors hierarchy (line 151-152), so no change needed there

**`vtext_client/cli.py`**
- Line 84-89: pass `output` to `batch_transcribe()` when `input_path.is_dir()`:
  ```python
  if input_path.is_dir():
      output_path = Path(output) if output and output != "-" else None
      batch_transcribe(
          input_path,
          output_dir=output_path,  # NEW
          server=server, fmt=fmt, language=language, model=model, jobs=jobs,
          simplify=simplify, refine=refine,
          ollama_url=ollama_url, refine_model=refine_model,
          refine_mode=refine_mode, llm_timeout=cfg.llm_timeout
      )
      return
  ```
- Edge case: `--output -` (stdout) makes no sense for batch; reject with clear error before calling `batch_transcribe()`

### 2. Backward compatibility

- `output_dir` defaults to `None` → existing code (tests, scripts) calling `batch_transcribe()` without the param continues to work
- CLI without `--output` → `output=None` → default behavior unchanged
- Test `test_batch.py::test_does_not_reprocess_text_outputs` still passes (it relies on `<input>/text` exclusion, which remains when `output_dir=None`)

### 3. Documentation updates

**`OUTPUT_BEHAVIOR.md`**
Current section 33-40 says batch creates `./media/text/`. Update to:
```markdown
## Batch Mode (directory input)

### Default (no `-o` option)
Creates `text/` subdirectory in the input directory:
```bash
vtext ./media/               # → ./media/text/file1.txt
                            # → ./media/text/sub/file2.txt
```

### Specify output directory (`-o <dir>`)
Mirrors input hierarchy under the output directory:
```bash
vtext ./media/ -o ./output  # → ./output/file1.txt
                            # → ./output/sub/file2.txt
```

Input: `./media/2023/jan/clip.mp4`  
Output: `./output/2023/jan/clip_raw.txt` (hierarchy preserved)
```

**CLI help text** (line 24-26)
Current: "Raw transcript output path/dir (default: <stem>_raw.<fmt> next to input; use '-' for stdout)"

Update to clarify batch support:
"Raw transcript output path/dir. Single file: default <stem>_raw.<fmt> next to input; use '-' for stdout. Batch: default <input>/text/; specify dir to mirror input hierarchy under output root."

### 4. Error handling

**CLI**: if user passes `--output -` with a directory input, raise:
```python
if input_path.is_dir() and output == "-":
    raise click.UsageError("Batch mode does not support stdout output (--output -).")
```

**batch.py**: no new error cases (output_dir is just a Path or None)

### 5. Testing strategy

**New test in `test_batch.py`**:
```python
def test_custom_output_dir_mirrors_hierarchy(tmp_path):
    sub = tmp_path / "input" / "season1"
    sub.mkdir(parents=True)
    (sub / "clip.mp4").touch()
    output_dir = tmp_path / "output"
    
    with patch("vtext_client.batch._process_one", ...):
        batch_transcribe(
            tmp_path / "input",
            output_dir=output_dir,
            server="...", fmt="txt", language=None, model=None, jobs=1
        )
    
    # _process_one should have been called with text_dir=output_dir
    # and base_dir=tmp_path/"input", which produces
    # output_dir/season1/clip_raw.txt
    assert mock_call_kwargs["text_dir"] == output_dir
```

**New test in `test_cli.py`**:
```python
def test_batch_with_output_dir(runner, tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "clip.mp4").touch()
    output_dir = tmp_path / "output"
    
    with patch("vtext_client.cli.batch_transcribe") as mock_batch:
        r = runner.invoke(cli, [str(media_dir), "-o", str(output_dir)])
    
    assert r.exit_code == 0
    mock_batch.assert_called_once()
    assert mock_batch.call_args[1]["output_dir"] == output_dir

def test_batch_rejects_stdout(runner, tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    r = runner.invoke(cli, [str(media_dir), "-o", "-"])
    assert r.exit_code != 0
    assert "does not support stdout" in r.output
```

**Existing tests**: all pass without modification (no param → default behavior)

### 6. Migration path for users

Current scripts/workflows calling `vtext <dir>` see no change. Users wanting the new behavior add `-o <output_dir>` explicitly.

Users with custom drivers (like `batch_extract.py`) can migrate to calling the library's `batch_transcribe(output_dir=...)` and delete their driver, or keep the driver for specialized logic (resume, custom filtering).

## Implementation Order

1. Add `output_dir` param to `batch_transcribe()` with default `None` and conditional logic
2. Wire CLI `--output` to batch path with stdout rejection
3. Add tests (batch + CLI)
4. Update `OUTPUT_BEHAVIOR.md`
5. Update CLI help text
6. Run full test suite to confirm no regressions

## Open Questions

None — design is straightforward, leverages existing `_process_one()` mirror logic, and maintains full backward compat.
