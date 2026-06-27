# Output Behavior

## Single File Mode

### Default (no `-o` option)
Creates a `text/` subdirectory next to the input file and saves output as `<input_stem>.<format>`:
```bash
vtext video.mp4              # → ./text/video.txt
vtext ../media/clip.mp4      # → ../media/text/clip.txt  
```

### Specify output directory (`-o <dir>`)
Saves to the specified directory with input filename + format extension:
```bash
vtext video.mp4 -o /output   # → /output/video.txt
vtext video.mp4 -o ./results # → ./results/video.txt
```

### Specify full output path (`-o <file>`)
Saves to the exact path specified:
```bash
vtext video.mp4 -o result.txt      # → ./result.txt
vtext video.mp4 -o /tmp/out.srt    # → /tmp/out.srt
```

### Output to stdout (`-o -`)
Prints transcription to stdout (useful for piping):
```bash
vtext video.mp4 -o -         # prints to stdout
vtext video.mp4 -o - | less  # pipe to pager
```

## Batch Mode (directory input)

### Default (no `-o` option)
Creates `text/` subdirectory in the input directory and preserves input hierarchy:
```bash
vtext ./media/               # processes all media files
                            # → ./media/text/file1.txt
                            # → ./media/text/sub/file2.txt
```

### Specify output directory (`-o <dir>`)
Mirrors input directory hierarchy under the specified output root:
```bash
vtext ./media/ -o ./output  # → ./output/file1.txt
                            # → ./output/sub/file2.txt
```

Example with nested structure:
```
Input:  ./media/2023/jan/clip.mp4
Output: ./output/2023/jan/clip_raw.txt  (hierarchy preserved)
```

All output files use the input filename stem + format extension (`.txt`, `.srt`, or `.vtt`).
