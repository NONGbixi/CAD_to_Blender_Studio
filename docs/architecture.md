# Architecture

Three stages, four layers, one shared model.

```text
                      ┌─────────────────────────┐
   CAD (SolidWorks)   │  read-only COM export    │
   ──────────────►    │  per-part tessellation   │
                      └───────────┬─────────────┘
                                  │  .tri + component tree
                                  ▼
                      ┌─────────────────────────┐
                      │  model.blend             │  collection: MODEL_原始装配
                      │  one EMPTY per component │  custom prop: source_id
                      │  original world matrices │  metric, tilt preserved
                      └───────────┬─────────────┘
                                  │  read-only input
                                  ▼
                      ┌─────────────────────────┐
                      │  studio.blend            │  Studio_Light + Studio_Dark
                      │  lights / floor / world  │  both share ONE model collection
                      │  from JSON presets       │  camera rig attached per scene
                      └───────────┬─────────────┘
                                  │  opened by every job
                                  ▼
   shot_config.json ──►  ┌─────────────────────────┐
   (frames, module,      │  shot engine / job       │  per frame:
    cameras, motion,     │                          │   constraints → materials
    samples, copy)       │                          │   → outline projection
                         │                          │   → surface render + denoise
                         │                          │   → line composite
                         └───────────┬─────────────┘
                                     ▼
                          PNG sequence → typography → H.264
```

## Layers

**1. Model layer (`01_materials`)**

The CAD-derived `.blend`. Contract that the rest of the pipeline relies on:

- one collection named `MODEL_原始装配` holding every component;
- one `EMPTY` per CAD component, carrying a `source_id` custom property, with the
  original world matrix and the mesh parented to it;
- metric units, geometry untouched — no decimation, no re-topology, no
  repositioning, no removal of the tilt of the CAD world frame.

`studio_core.fingerprint()` hashes vertex, loop, material-index, smooth-flag,
sharp-edge, hierarchy and world-matrix data, so any accidental change to that
contract is caught before a render.

**2. Studio layer (`02_studio`)**

A `.blend` containing two scenes, `Studio_Light` and `Studio_Dark`, that both
link the *same* model collection — switching studios never duplicates the model.
Each scene holds a floor, a world and area lights whose energy and size are
scaled from the model's own bounding box, so the studio fits any assembly.

Only numbers live in `presets/light.json` and `presets/dark.json`. Changing the
lighting means editing JSON and re-rendering; it does not mean editing the
`.blend`, which keeps the two in sync and makes the preset part of the job
fingerprint.

**3. Director layer (`03_director`)**

Everything that decides *what the frame looks like* without touching geometry:

- `camera_control.py` — a rig that fits a target's bounding box, then dolly,
  orbit, follow or animate focal length, with ease-in/ease-out and a separate
  focus target for depth of field;
- `module_focus.py` + `outline_approved/` — which components are solid, ghosted,
  hidden, or excluded from outlines;
- `typography/` — 2D titles with a per-glyph cmap audit so a missing glyph fails
  loudly instead of rendering a box.

**4. Production layer (`tvc`)**

The film-specific part: one `shot_config.json` per shot, one config-driven
engine, one queue. It knows nothing about CAD; it drives the three layers below
it. The dependency direction is strictly downward — the studio layer never
imports the film layer, which is what makes the studio layer reusable.

## One engine, twelve shots

`remaining_engine.py` receives a shot directory and reads everything else from
`shot_config.json`:

```json
{
  "id": "S04",
  "frames": [661, 780],
  "studio": "Emphasis_Dark",
  "module": "gimbal",
  "preview": {"width": 1920, "height": 1080, "samples": 128,
               "adaptive_min_samples": 32, "adaptive_threshold": 0.0075},
  "cameras": [
    {"frames": [661, 696], "target": ["PART_A", "PART_B"],
     "direction": [1, 0.8, 0.8], "lens": 85, "margin": 1.3,
     "move": "slide", "travel": [0, 0.01, 0]},
    {"frames": [697, 780], "target": ["PART_C", "PART_D"],
     "direction": [1, 0.8, 0.8], "lens": 75, "margin": 1.34,
     "move": "pull", "factor": 1.04}
  ],
  "motion": {"gimbal_max_deg": 14, "lift_down_mm": 88},
  "title": {"institution": "机构名称", "technical": "技术副标题"}
}
```

Adding a shot means adding a config and a directory, not writing code. That is
why eight revision rounds of a twelve-shot film stayed manageable.

**The engine itself is not part of this repository.** It is bound to one machine:
its part IDs, its gear tooth counts, its belt circulation and wheel groups. It is
kept in the private project archive, which is also why this document describes the
pattern rather than shipping the file.

## Why the studio and the film are separate projects

The studio setup (model, lighting, cameras, outline parameters) is the part that
is reusable across products. The film setup (shots, order, copy, timing) is
specific to one deliverable. Keeping them in two projects — with the film
importing the studio by path — meant the studio could be finished, validated and
frozen before any shot existed, and every later shot inherited those guarantees.
