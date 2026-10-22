# Production conventions

These are the habits that made a twelve-shot film with eight revision rounds
reviewable after the fact. They are not enforced by code; they are the reason the
code stayed small.

## 1. Version directories, never overwritten

Every revision gets a new directory named `<number>_<reason>`:

```text
02_镜头制作/S04_云台/r01/               first pass
02_镜头制作/S04_云台/r02_横移字幕/       subtitle revision
02_镜头制作/S04_云台/r03_对角线与云台闪烁修正/
```

Within a revision:

```text
shot_config.json      the parameters that define this revision
scripts/             the scripts that ran for it
project/*.blend      the editable shot project
frames/*.png         the sequence (regenerable)
reports/*.json       what actually happened: timings, hashes, verification
review/*.png         contact sheets for human review
preview/*.mp4        low-res or trimmed preview
制作说明.md            what changed and why
```

Nothing is ever overwritten in place. The cost is disk space; the benefit is
that "which version did the client approve?" is answerable months later without
guesswork.

## 2. One pointer file

The live revision is named in exactly one place:

```json
{
  "revision": "tvc_pose_r02",
  "base_project": "03_机构基准/project/统一姿态_r02.blend",
  "base_project_sha256": "697ce65d...",
  "pose_config": "03_机构基准/start_pose_r02.json",
  "S02_current": "02_镜头制作/S02/.../r03_抖动修正",
  "current_video": ".../preview/....mp4",
  "status": "..."
}
```

Reading the pointer tells you what is live; reading any directory tells you what
exists. Scripts read the pointer, never a hard-coded path.

## 3. SHA-256 on every input and output

- source CAD files are hashed **before and after** a read-only import; equal
  hashes prove the source was not modified;
- every `.blend` that becomes an input is hashed and the hash stored in the
  consuming job's report;
- delivered video is hashed and stored in the delivery manifest, next to the
  decoded frame count;
- re-encoded video must prove the *picture stream* is unchanged when only audio
  was added.

A hash in a report is only useful if it is checked. Delivery reports record the
check, not just the value.

## 4. Verify by reopening

No scene counts as saved until it has been reopened in a fresh process and
re-fingerprinted. The fingerprint covers exactly what a render would depend on:
vertices, loops, material indices, smooth/sharp flags, parent hierarchy, world
matrices, and material node inputs.

The typical verification report says "source SHA unchanged, 442 components,
523 meshes, 797,810 triangles, all components visible, no animation, reopened
fingerprint identical". That single sentence is what allows the next stage to
trust the file.

## 5. Distinguish regenerable from irreplaceable

| Regenerable | Irreplaceable |
|---|---|
| PNG frame sequences | source `.blend` per shot revision |
| per-frame edge JSON | parameters (`shot_config.json`, presets) |
| logs, caches, previews | delivered MP4 + delivery manifest |
| contact sheets | decisions written in `制作说明.md` |

Frame sequences are the largest thing on disk and the most reproducible, so they
are the first thing to archive off. The `.blend` and the JSON are the actual
asset.

## 6. Write uncertainty down

Where a classification could not be proven, it was recorded as such instead of
smoothed over:

```text
311 个顶层紧固件类型明确，但具体随哪个机构运动不能仅凭顶层父级确认，
保持中性灰和源父级，置信度"中"，待确认的运动归属写入备注。
```

A deliverable that says "medium confidence, here is the evidence" is more useful
than one that quietly guesses. It also stops the next person from re-doing the
investigation.

## 7. Separate "does it look right" from "is it valid"

Renders were checked in two independent ways:

- **visually** — contact sheets of first/middle/last frame, 100% crops for noise
  and line quality, before/after pairs at identical camera positions;
- **mechanically** — frame count, resolution, PNG CRC, contiguous sequence,
  decode the encoded MP4 and count frames, compare hashes of unchanged streams.

Neither replaces the other. A frame that decodes perfectly can still have a line
through the subject.
