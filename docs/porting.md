# Porting and adapting

This code was extracted from a working project. It runs on that project's
directory convention and on a CAD-imported `.blend` that it does not ship. This
page lists everything you have to change to make it run on your own model.

## 1. The scene contract

The pipeline assumes the following about the model `.blend`. Nothing will run
until it is true:

| Requirement | Why |
|---|---|
| one collection named `MODEL_原始装配` | `studio_core.fingerprint()`, `make_scene()` and the outline pipeline all look it up by name |
| one `EMPTY` per CAD component, with a `source_id` custom property | component count, per-component grouping, mechanism maps |
| mesh objects parented to those empties, with original world matrices | motion is driven by moving empties, never by editing meshes |
| metric units, and the CAD world frame's tilt preserved | the studio floor and camera rig are derived from the model's own axes, not from world Z |
| scene name `Studio_Light` / `Studio_Dark` after `build_studio.py` | every job selects a scene by `Studio_<Name>` |

`studio_core.fingerprint()` is the cheapest way to check a new model: it will
tell you component count, mesh count, triangle count and whether the hierarchy
looks the way the pipeline expects.

## 2. Path conventions

Scripts resolve `ROOT` and then append the original layout:

```text
ROOT/01_materials/...      model, reference data, fonts
ROOT/02_studio/...         studio .blend, presets, scripts
ROOT/03_director/...       camera, typography, outline
ROOT/04_output/...         frames, stills, videos, reports, logs, cache
```

Nothing forces you to keep those names, but every one of them appears in at least
one script. If you rename them, grep for the old name first:

```powershell
Select-String -Path .\studio\**\*.py -Pattern "01_materials|02_studio|03_director|04_output"
```

The environment variables in the README cover the four entry points that matter
most (`CAD_ROOT`, `CAD_STUDIO_BLEND`, `CAD_MODEL_BLEND`,
`CAD_OUTLINE_PROFILE`, `CAD_TYPOGRAPHY_PROFILE`).

## 3. What is parameterised

| Was hard-coded | Now |
|---|---|
| `D:\...\blender.exe` | `CAD_BLENDER`, else `blender` on `PATH` |
| `.../studio.blend` | `CAD_STUDIO_BLEND` |
| `.../model.blend` | `CAD_MODEL_BLEND` |
| cross-project studio path | `CAD_STUDIO_ROOT` |
| fake brand names in presets and sample copy | generic placeholders (`ACME`, `studio.blend`) |

## 4. External dependencies

| Need | Where it is used | Notes |
|---|---|---|
| **Blender 4.5.3 LTS** | everything | `bpy` APIs differ between minor versions; 4.5 is what was tested |
| **numpy** | outline projection, BVH helpers | ships with Blender, but the standalone helpers import it |
| **Pillow** | 2D typography, line compositing | system Python, not Blender's |
| **imageio-ffmpeg** | encoding | or point `CAD_FFMPEG` at any FFmpeg |
| **A CJK font** | `styles.json` points at `Noto Sans SC Medium` | download from notofonts; the glyph audit will reject a wrong file |
| **Windows** | only `run_render.py` resource sampling | guarded by `os.name != 'nt'` in the sampler |

## 5. Known rough edges

- `run_render.py` and `encode_video.py` assume the caller's `ROOT` contains
  `02_studio/scripts/render_job.py`. If you move scripts, fix both the subprocess
  path and the script-hash list in the job identity.
- The typography helpers run in *system* Python (for Pillow), while everything
  else runs inside Blender's Python. That split is intentional but means two
  interpreters must exist.
- The outline parameters were tuned for 1080p on a 797k-triangle model. Smaller
  models will need a larger `min_feature_mm`; higher resolutions need no change
  because line width is defined relative to output height.
- `module_outline_v02.json` contains placeholder object names
  (`gimbal_bracket_object_name`, …). Replace them with real object names from
  your own assembly; the config is meaningless until you do.

## 6. Suggested first test

1. Import your CAD, verify the collection and component contract.
2. `build_studio.py` — it asserts that the model fingerprint is unchanged after
   building both scenes. If that assertion fails, stop; the import is wrong.
3. Render one still in each studio at 64 samples and look at the contact shadows.
4. Render 30 frames of a camera orbit and check for line flicker, transparent
   surface noise and denoiser pumping. Do this before committing to a shot.
5. Only then set up a `shot_config.json` and run the shot engine.
