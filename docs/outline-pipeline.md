# Outline pipeline

`studio/03_director/outline_approved/`

The job: keep one mechanism of a CAD assembly fully solid and readable, and show
the rest of the machine as a ghost with thin structural lines — stable from
frame to frame, while parts move.

## Why not the built-in options

| Option | Why it failed here |
|---|---|
| Freestyle | line set evaluation is not aware of the assembly's derived outline curves; occlusion and back-face decisions become unstable once parts move |
| Line Art | same per-frame ambiguity, plus heavy cost on a 797k-triangle model |
| Wireframe / Solidify modifier | shows every triangle edge, including coplanar CAD tessellation |
| Post-process edge filter (Sobel etc.) | edges depend on shading and lighting, not structure; thin lines vanish after denoise |
| Blur to fake depth | explicitly forbidden by the brief: transparency must mean structure, not defocus |

The assembly already contains a set of derived **outline curves** (one per
component, generated at import). The pipeline filters *those*, so the lines are
geometrically meaningful rather than shading-derived.

## Two-pass design

```text
pass 1  surfaces   subject  → original CAD material, opaque
                   context  → derived material, Alpha 0.13
                   render Cycles, denoise with OIDN (RGB + Albedo + Normal)

pass 2  lines      per frame: project derived edge curves with current camera
                   test back-face / occlusion against a per-frame BVH
                   drop coplanar triangles and sub-16 mm closed features
                   composite ONE antialiased mask at 35%, ~0.4 px, #A8ADB3

pass 3  type       2D RGBA overlay, never perspective-warped
```

Compositing order matters: the line pass is composited **after** denoising, so
sub-pixel lines are not smoothed away; and the line colour is applied once, so
overlapping segments do not accumulate opacity.

## Per-frame steps

1. `scene.frame_set(frame)` — evaluate constraints, animated matrices, modifiers.
2. Restore the emphasised module's original materials; give every other object
   the derived context material at `context_face_opacity`.
3. Hide the derived 3D outline objects from the surface render (they would
   otherwise be visible geometry).
4. Rebuild the occlusion BVH for the **current** frame. A cached BVH is invalid
   as soon as a part moves.
5. Project outline segments to screen space; for perspective cameras rays start
   at the camera position, for orthographic cameras they are parallel.
6. Reject segments that are back-facing, occluded, coplanar with a neighbouring
   triangle, or part of a closed internal feature smaller than ~16 mm.
7. Emit one JSON per frame: a list of 2D endpoint pairs.
8. `compose_edges.py` rasterises that list at ~10× supersampling and alpha-blends
   it onto the denoised surface PNG at the configured width, colour and opacity.

Long segments are sampled along their projected length rather than at the
midpoint only, otherwise a subject edge can be "visible" while its far end is
behind another part. Contour selection is deterministic across frames so lines
do not jump.

## Parameters

`studio/02_studio/presets/module_outline_approved.json` and
`module_outline_v02.json` are the single source of truth. Nothing here is meant
to be inferred from a saved `.blend`, from an old render, or from a rejected
50% trial.

| Key | Value | Meaning |
|---|---|---|
| `context_face_opacity` | `0.13` | alpha of every non-subject surface |
| `line_width_px` (1080p) | `~0.4` | scaled by output height |
| `line_color_srgb` | `#A8ADB3` | neutral structural grey |
| `line_opacity` | `0.35` | applied once, not accumulated |
| `module_context_overrides` | per module | e.g. the battery shot hides the gimbal bracket and its descendants completely |

## Known failure modes that drove the design

- **Varying line width between frames** — from compositing before denoise; fixed
  by compositing after.
- **Lines through the subject** — from testing visibility at a segment midpoint
  only; fixed by sampling along the projected length.
- **Random line flicker** — from unordered edge selection; fixed by deterministic
  selection and by rebuilding the BVH per frame.
- **Ghost surfaces flickering** — from adaptive sampling thresholds that were too
  loose on transparent surfaces; fixed with a fixed seed, adaptive minimum
  samples and a stricter noise threshold.
- **Lines lost on 4K** — width is defined as a fraction of output height, not in
  absolute pixels.

## Reference implementation

- `outline_pipeline.py` — the per-frame state machine (prepare, project, filter).
- `compose_edges.py` — standalone 2D compositor; also usable on a single frame.
- `render_static_reference.py` — renders the four before/after validation pairs
  from stored camera views without touching a saved `.blend`.
- `module_focus.py` — per-shot decision of solid / ghost / hidden / no-outline.
- `render_outline_job.py` — the video job that wires the above into a PNG
  sequence with a fingerprint report.
