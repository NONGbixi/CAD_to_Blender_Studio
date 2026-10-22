# CAD to Blender Studio

**A production pipeline that turns a mechanical CAD assembly into product-grade
stills and film shots in Blender / Cycles.**

This is not a library. It is the working code behind a real 55-second product
film for an autonomous mobile robot: one SolidWorks assembly was imported into
Blender, dressed in a two-scene virtual studio, lit and shot with a scripted
camera rig, rendered on a laptop GPU, and cut into a commercial — with the
outline, camera, typography and job-management tooling all written from scratch.

Everything here was extracted from that project, not rewritten for show. The
assets (CAD, `.blend`, renders, fonts, music) are deliberately **not** included.
Read [NOTICE.md](NOTICE.md) first if you plan to reuse any of it.

---

## The interesting part: transparent-module emphasis

The recurring brief in hardware films is *"show this one mechanism, but keep the
rest of the machine readable as a ghost"*. The usual answer is Freestyle, Line
Art or a Wireframe modifier. This pipeline does none of those, because on a
797,810-triangle assembly they cannot hold a stable, thin, occlusion-correct
line from frame to frame.

Instead it splits the problem in two:

1. **Surfaces** are rendered normally. The subject keeps its real CAD material
   and stays fully opaque; every other component gets a derived transparent
   material at **Alpha 0.13**. Cycles renders and denoises this pass.
2. **Lines** come from the assembly's own derived edge curves, which are
   projected to screen space *per frame* with the current camera, tested against
   a per-frame BVH for back-faces and occlusion, filtered for coplanar triangles
   and sub-16 mm internal features, then composited once at **35% opacity,
   ~0.4 px, `#A8ADB3`** on top of the denoised surface pass.

The line pass is composited *after* denoising, so sub-pixel lines survive.
Text is composited after that, in 2D, so type is never perspective-warped.

| Confirmed parameter | Value |
|---|---|
| Context surface alpha | `0.13` |
| Line width at 1080p | `~0.4 px` (0.8 px at 4K) |
| Line colour / opacity | `#A8ADB3` / `35%` |
| Subject | original opaque CAD material, untouched geometry |
| Removed lines | back-faces, occluded, coplanar, dense small holes |
| Not used | Freestyle, Line Art, Wireframe modifier, blur to fake depth of field |

The parameters live in `studio/02_studio/presets/module_outline_*.json`; the
implementation is `studio/03_director/outline_approved/`.

---

## What is inside

| Module | What it does | Entry point |
|---|---|---|
| **Outline pipeline** | per-frame transparent context + BVH-tested projected outlines | `studio/03_director/outline_approved/outline_pipeline.py` |
| **2D line compositor** | blends the per-frame edge JSON into the surface render | `.../compose_edges.py` |
| **Module focus** | decides which components are solid / ghosted / hidden per shot | `studio/03_director/module_focus.py` |
| **Studio builder** | builds `Studio_Light` / `Studio_Dark` scenes from JSON presets | `studio/02_studio/scripts/build_studio.py` |
| **Scene core** | Cycles device selection, render settings, geometry fingerprint | `.../studio_core.py` |
| **Camera rig** | `fit / dolly / orbit / follow / animate_lens`, 56 checked framings | `studio/03_director/camera_control.py` |
| **Typography** | 2D RGBA title system with per-glyph cmap audit | `studio/03_director/typography/` |
| **Render jobs** | fingerprinted, resumable PNG-sequence jobs + FFmpeg encode | `.../render_job.py`, `.../encode_video.py` |
| **Queue / lock** | sequential GPU queue and single-worker lock | `tvc/07_自动化制作/scripts/` |

---

## Pipeline at a glance

```text
SolidWorks assembly
   │  read-only COM export, per-part tessellation
   ▼
model.blend            collection MODEL_原始装配, one EMPTY per component,
   │                   original world matrices, metric units, tilt preserved
   ▼
studio.blend           build_studio.py → Studio_Light + Studio_Dark,
   │                   both sharing one MODEL collection, lights from JSON
   ▼
shot_config.json       frame range, module to emphasise, camera segments,
   │                   motion amplitudes, sample budget, copy
   ▼
render_job.py          per-frame: evaluate constraints → set transparency →
   │                   project + occlude-test outlines → render & denoise
   │                   surfaces → composite one line pass → PNG
   ▼
compose_edges.py       lines + 2D typography
   ▼
encode_video.py        PNG sequence → validated H.264 MP4
```

---

## Production conventions worth stealing

The code is ordinary. The *file discipline* is what made a 12-shot film with
eight revision rounds reviewable:

- **Versioned directories, never overwritten.** Every revision gets a new
  `rNN_<reason>/` folder; the previous shot project, frames and preview stay
  readable forever.
- **One pointer file.** `project_current.json` / `task_current.json` record which
  revision is live, with the SHA-256 of every input it depends on.
- **Refuse to mix revisions.** A render job hashes the model, the preset and the
  scripts; if any of them changed, existing frames are rejected instead of
  silently reused.
- **Verify by reopening.** Every saved scene is reopened and re-fingerprinted
  (vertex, loop, material-index, shading, hierarchy, world matrix) before it is
  considered valid.
- **Write uncertainty down.** Parts whose motion ownership could not be proven
  were recorded as "confidence: medium" instead of guessed.

See [docs/conventions.md](docs/conventions.md).

---

## Requirements

- **Blender 4.5.3 LTS.** Developed and verified on that version only.
- **A Cycles GPU** — OptiX was used throughout; the code falls back to CUDA,
  HIP, oneAPI, Metal, then CPU, and records which backend actually rendered.
- **Windows** for `run_render.py` (it samples memory/GPU through `ctypes` and
  `nvidia-smi`). The Blender-side scripts carry no Windows dependency.
- **Python 3.12** with `Pillow`, `numpy`, `imageio-ffmpeg`:

```bash
pip install -r requirements.txt
```

Reference timings on the project machine (RTX 5070 Laptop, 1080p, OptiX,
128 adaptive samples, OIDN): **1.95 s/frame** for the dark studio, **5.2 s/frame**
for the light shadow-catcher studio. Measure your own — the numbers depend
mostly on how much of the frame the subject fills.

---

## Quick start

This repository does **not** ship the CAD or the `.blend` files, and the scripts
follow the original project's directory conventions. Read
[docs/porting.md](docs/porting.md) before running anything.

```bash
# 1. put a CAD-imported model here
#    01_materials/model/model.blend
#    required: collection 'MODEL_原始装配', one EMPTY per component carrying a
#    'source_id' custom property, metric units, original world matrices

# 2. build the two studio scenes from the JSON presets
blender -b --factory-startup --python studio/02_studio/scripts/build_studio.py

# 3. render one still, with a fingerprinted job name
python studio/02_studio/scripts/run_render.py --studio dark --job test_still --samples 64

# 4. render a 30-frame sequence and encode it
python studio/02_studio/scripts/run_render.py --studio dark --job test_seq --samples 64 \
    --sequence --end 30 --motion orbit
python studio/02_studio/scripts/encode_video.py --job test_seq --titles
```

---

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `CAD_ROOT` | `studio/` | project root holding `01_materials`, `03_director`, `04_output` |
| `CAD_STUDIO_ROOT` | `<repo>/studio` | studio project used by the shot engine |
| `CAD_STUDIO_BLEND` | `02_studio/studio.blend` | scene opened by every render job |
| `CAD_MODEL_BLEND` | `01_materials/model/model.blend` | CAD-imported input for `build_studio.py` |
| `CAD_OUTLINE_PROFILE` | `06_视觉控制/module_outline_tvc.json` | outline config for the shot engine |
| `CAD_TYPOGRAPHY_PROFILE` | `04_字体与版式/typography_profile.json` | font roles + SHA-256 |
| `CAD_BLENDER` | `blender` on `PATH` | Blender executable |
| `CAD_PYTHON` | `python` on `PATH` | system Python for the 2D compositing helpers |
| `CAD_FFMPEG` | bundled `imageio-ffmpeg` | FFmpeg executable |

---

## Repository layout

```text
studio/
  01_materials/          (empty — your CAD-imported model goes here)
  02_studio/
    presets/             light.json, dark.json, module_outline_*.json
    scripts/             build_studio, studio_core, render_job, run_render,
                         encode_video, verify_system, validation_suite,
                         render_outline_job, run_outline_render
  03_director/
    camera_control.py    camera rig and framing presets
    module_focus.py      per-shot solid / ghost / hidden decisions
    outline_approved/    the outline pipeline and its static reference renderer
    typography/          title system, styles, glyph audit
  04_output/             (empty — renders, logs and caches land here)
tvc/
  06_视觉控制/            per-shot outline profile wrapper
  07_自动化制作/scripts/   queue and worker lock
docs/                    architecture, outline pipeline, job design, porting
```

---

## Status and limitations

- **Extracted, not packaged.** There is no CLI, no test suite and no release. It
  is the actual production code with the project-specific parts parameterised.
- **Path conventions are inherited.** Scripts expect the `01_materials` /
  `02_studio` / `03_director` / `04_output` layout. [docs/porting.md](docs/porting.md)
  lists every point you have to adapt.
- **Windows-only resource sampler** in `run_render.py`; rendering itself is
  cross-platform.
- **Verified on one machine** (RTX 5070 Laptop, driver 592.01, Blender 4.5.3).
  No long-run thermal or 4K benchmarking was done.
- **The per-shot kinematic engine is withheld.** It drives one specific machine
  (its part IDs, gear meshing, belt circulation, wheel groups) and is therefore
  not reusable; it lives in the private archive. What is published is the whole
  layer it drives: studios, cameras, outline pipeline, typography and jobs. The
  pattern it follows is described in [docs/architecture.md](docs/architecture.md).
- **No product assets.** The images that would make this README pretty are
  withheld on purpose — see [NOTICE.md](NOTICE.md).

---

## License

Code is MIT — see [LICENSE](LICENSE). Third-party notices in [NOTICE.md](NOTICE.md).

中文说明见 [README.zh-CN.md](README.zh-CN.md)。
