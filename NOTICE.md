# Provenance and third-party notices

## Where this code comes from

Every script in this repository was written for, and used in production by, a
single project: turning a SolidWorks CAD assembly of an autonomous mobile robot
into product stills and a 55-second TV commercial inside Blender / Cycles.

The production workspace was extracted into this repository with three changes:

1. project- and brand-specific file names were replaced with generic ones
   (`studio.blend`, `model.blend`, `studio_emphasis.blend`);
2. hard-coded absolute paths were replaced with environment variables
   (see `docs/porting.md`);
3. object names inside `presets/module_outline_v02.json` were replaced with
   placeholder keys.

Nothing else was rewritten. The code is therefore a faithful record of what
actually ran, not a cleaned-up rewrite.

## What is **not** included

- **No CAD data.** No SolidWorks files, no `.blend` files, no meshes, no
  renders of the product. You supply your own CAD-derived `.blend`.
- **No product photography or film footage.** All images and video of the
  original product were deliberately left out.
- **No fonts.** `styles.json` points at `Noto Sans SC Medium`, which is
  licensed under the SIL Open Font License 1.1 and can be downloaded from
  <https://github.com/notofonts/noto-cjk>. Font files are not redistributed here.
  The production project also used Apple system fonts (PingFang SC, SF Pro) for
  one revision; those are **not** redistributable and are not part of this repo.
- **No music.** The commercial used licensed recordings; none of it is here.

## Third-party software

- [Blender](https://www.blender.org) 4.5.3 LTS — GPL, invoked as an external
  executable, not linked.
- [Pillow](https://python-pillow.org) — MIT-CMU.
- [numpy](https://numpy.org) — BSD-3-Clause.
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) — BSD-2-Clause,
  bundles an FFmpeg build (LGPL/GPL depending on the build).
- [Noto Sans CJK](https://github.com/notofonts/noto-cjk) — SIL OFL 1.1.
