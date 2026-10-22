import bpy,os,sys,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from studio_core import *
setup_paths()
source=Path(os.environ.get('CAD_MODEL_BLEND',ROOT/'01_materials/model/model.blend'))
bpy.ops.wm.open_mainfile(filepath=str(source))
bpy.context.view_layer.update()
before=fingerprint();dump(ROOT/'01_materials/reference/model_fingerprint.json',before)
old_scenes=list(bpy.data.scenes)
old_studio=bpy.data.collections.get('STUDIO_摄影棚（可整组隐藏）')
for key in ['light','dark']:
    preset=json.loads((ROOT/f'02_studio/presets/{key}.json').read_text(encoding='utf-8'))
    make_scene(preset)
for s in old_scenes:bpy.data.scenes.remove(s)
if old_studio:
    for o in list(old_studio.all_objects):bpy.data.objects.remove(o,do_unlink=True)
    bpy.data.collections.remove(old_studio)
bpy.context.window.scene=bpy.data.scenes['Studio_Light']
bpy.context.view_layer.update()
after=fingerprint()
assert before==after,'CAD geometry/material/transform/hierarchy changed'
aliases={alias:{'collection':name,'mesh_count':len([o for o in bpy.data.collections[name].all_objects if o.type=='MESH']),
                  'object_names':[o.name for o in bpy.data.collections[name].all_objects]} for alias,name in MECHANISMS.items()}
dump(ROOT/'03_director/mechanism_map.json',aliases)
device=configure_device(bpy.context.scene)
for s in bpy.data.scenes:s.cycles.device=bpy.context.scene.cycles.device
dump(ROOT/'04_output/reports/build_verification.json',{'exact_fingerprint_match':True,'components':before['components'],
    'meshes':before['mesh_count'],'triangles':before['triangles'],'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'shared_model_between_scenes':all(bpy.data.collections['MODEL_原始装配'] in list(s.collection.children) for s in bpy.data.scenes),
    'device':device,'gpu_at_build':gpu_snapshot(),'scenes':[s.name for s in bpy.data.scenes]})
for script in [ROOT/'03_director/camera_control.py',ROOT/'02_studio/scripts/build_studio.py',ROOT/'02_studio/scripts/studio_core.py']:
    text=bpy.data.texts.get('TASK2_'+script.name) or bpy.data.texts.new('TASK2_'+script.name)
    text.clear();text.write(script.read_text(encoding='utf-8'))
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_perspective='CAMERA'
            area.spaces.active.overlay.show_extras=False
            area.spaces.active.clip_start=.0005
bpy.context.scene.render.filepath='//../04_output/stills/light_hero.png'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'02_studio/studio.blend'))
print('BUILD_OK',flush=True)
