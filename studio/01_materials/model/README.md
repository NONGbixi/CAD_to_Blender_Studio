# Model contract

Put **one** CAD-imported Blender file here:

```text
01_materials/model/model.blend
```

or point `CAD_MODEL_BLEND` somewhere else. `.blend` files are git-ignored, so this
directory is normally empty in a clone.

## What the rest of the pipeline requires from that file

Nothing will run correctly until every line below is true. These are not style
preferences; each one is looked up by name or relied on by a computation.

| # | Requirement | Used by |
|---|---|---|
| 1 | a collection literally named `MODEL_原始装配` containing every component | `studio_core.fingerprint()`, `studio_core.make_scene()`, outline pipeline |
| 2 | one `EMPTY` per CAD component, each with a `source_id` custom property | component counting, mechanism maps, per-component emphasis |
| 3 | the component's mesh parented to its empty, holding the original world matrix | motion is authored on empties; meshes are never edited |
| 4 | metric units, millimetres, and the CAD world frame's tilt **preserved** | studio floor, camera rig and light scaling are derived from the model's own axes |
| 5 | materials already assigned per part (Principled BSDF, no textures needed) | the subject is rendered with its original material |
| 6 | no modifiers, no decimation, no re-topology | `fingerprint()` compares the mesh arrays exactly |
| 7 | outline curves generated at import, parented per component | the line pass filters the model's own derived edge curves |

## Verification

`studio_core.fingerprint()` gives you the cheapest possible contract check:

```python
import bpy, sys
sys.path.insert(0, "studio/02_studio/scripts")
from studio_core import fingerprint
print(fingerprint()["components"], fingerprint()["mesh_count"], fingerprint()["triangles"])
```

Then build the studio. `build_studio.py` fingerprints the model before and after
building the two scenes and **asserts they are identical** — if the assertion
fires, the studio build changed the model and the import is not trustworthy.

## Why this contract exists

A CAD import is a lossy, opinionated translation. Keeping one empty per component
means animation moves transforms, never vertices; keeping the original world
matrix means the studio can be built along the machine's real axes even when the
CAD assembly sits tilted in space; keeping the mesh arrays bit-identical means a
reopen-and-compare is a meaningful integrity check rather than a vague one.
