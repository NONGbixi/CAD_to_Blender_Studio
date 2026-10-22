# Render jobs

`studio/02_studio/scripts/render_job.py`, `run_render.py`, `encode_video.py`

A "job" is one named, fingerprinted, resumable render unit. The design goal was
that an interrupted 1,300-frame sequence could be resumed by re-running the same
command, and that a frame rendered under different inputs could never be
silently mixed into the result.

## Job identity

Every job writes a report next to its output:

```text
04_output/reports/<job>.json
04_output/frames/<job>/frame_0001.png ...
04_output/stills/<job>.png            (single-frame jobs)
04_output/videos/<job>_clean.mp4      (after encoding)
04_output/videos/<job>_titles.mp4
04_output/logs/<job>.log
```

The report stores an `identity` hash derived from:

- SHA-256 of the `.blend` that was opened,
- SHA-256 of the studio preset JSON,
- the render arguments (resolution, samples, adaptive threshold, frame range,
  motion range, lens, depth of field),
- SHA-256 of the core scripts (`studio_core.py`, `camera_control.py`,
  `outline_pipeline.py`, `compose_edges.py`, …).

Re-running a job name with a different identity **raises**:

```text
RuntimeError: Job inputs changed; select a new job name
```

That is deliberate. Changing a preset must not silently produce a sequence whose
first 400 frames came from the old lighting.

## Resume

Existing frames are skipped only if they are actually valid — the PNG is opened
and its size, structure and CRC are checked, plus the expected resolution:

```bash
# first attempt died at frame 511
python studio/02_studio/scripts/run_render.py --studio dark --job my_seq \
       --samples 128 --sequence --end 900 --motion orbit

# same command again: frames 1..510 are verified and skipped, 511..900 render
```

`--start` / `--end` may be narrowed on resume. `--motion-start` /
`--motion-end` must stay identical, because the camera animation is computed
from them; widen `--motion-end` when extending a shot.

## Encode

`encode_video.py` refuses to encode a sequence with gaps, re-verifies every frame,
optionally composites the 2D typography, then calls FFmpeg:

```text
libx264 · CRF 18 · yuv420p · 30 fps · MP4 · faststart
```

It writes `<job>_encode.json` with the frame count, duration, codec and output
SHA-256, and then decodes the result once to confirm the expected frame count.

## Concurrency

`render_queue.py` runs jobs sequentially and records progress in
`build_progress.json`; `task_worker_lock.py` prevents two workers from driving
the same GPU at once. The hardware assumption is one GPU, so parallelism is
refused rather than attempted.

## What a job is *not*

A job is not a project. Shot projects are separate `.blend` files, one per shot
and revision. The job only opens one, renders a frame range and reports. That
separation is what allows the same engine to drive twelve shots with different
cameras, motions and modules.
