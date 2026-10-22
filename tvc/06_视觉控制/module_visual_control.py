"""Small public wrapper around the module-emphasis system; no geometry edits.

Run inside Blender after opening a shot project. A frame render still needs the
2D compose_edges pass for the final thin outlines.

Environment:
  CAD_STUDIO_ROOT       path to the studio project (default: <repo>/studio)
  CAD_OUTLINE_PROFILE   outline profile JSON (default: 06_视觉控制/module_outline_tvc.json)
"""
import os, sys
from pathlib import Path
TVC=Path(__file__).resolve().parents[1]
STUDIO=Path(os.environ.get('CAD_STUDIO_ROOT',TVC.parent/'studio')).resolve()
sys.path[:0]=[str(STUDIO/'03_director'),str(STUDIO/'03_director/outline_approved')]
def focus(scene,module,profile=None):
 from outline_pipeline import OutlinePipeline
 default=Path(os.environ.get('CAD_OUTLINE_PROFILE',TVC/'06_视觉控制/module_outline_tvc.json'))
 pipeline=OutlinePipeline(scene,Path(profile) if profile else default)
 return pipeline,pipeline.prepare_frame(module)
def restore_full_solid():
 import bpy
 scene=bpy.data.scenes['Studio_Dark'];bpy.context.window.scene=scene;bpy.context.view_layer.update()
 return scene
