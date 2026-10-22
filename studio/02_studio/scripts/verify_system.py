"""Reopen saved blend, verify CAD integrity, projection, motion and follow behavior."""
import bpy,json,os,sys,math
from pathlib import Path
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from studio_core import *
from camera_control import objects_for
bpy.ops.wm.open_mainfile(filepath=str(Path(os.environ.get('CAD_STUDIO_BLEND',ROOT/'02_studio/studio.blend'))))
bpy.context.view_layer.update()
expected=json.loads((ROOT/'01_materials/reference/model_fingerprint.json').read_text(encoding='utf-8'))
actual=fingerprint()
if actual!=expected:
    dump(ROOT/'04_output/reports/reopened_fingerprint.json',actual)
    def diffs(a,b,path=''):
        if type(a)!=type(b):return [(path,str(a)[:100],str(b)[:100])]
        if isinstance(a,dict):return [x for k in a.keys()|b.keys() for x in diffs(a.get(k),b.get(k),path+'/'+str(k))]
        if isinstance(a,list):return [x for i,(v,w) in enumerate(zip(a,b)) for x in diffs(v,w,path+'/'+str(i))]
        return [] if a==b else [(path,a,b)]
    dump(ROOT/'04_output/reports/reopen_differences.json',diffs(expected,actual))
assert actual==expected,'Saved project model changed'
checks=[];presets=[]
for scene in bpy.data.scenes:
    bpy.context.window.scene=scene;bpy.context.view_layer.update()
    assert scene.render.fps==30
    for target in MECHANISMS:
        for view,lens in [('hero',35),('low',50),('top',85),('macro',85)]:
            rig=CameraRig(scene).fit(target,lens,view)
            bpy.context.view_layer.update()
            uv=[world_to_camera_view(scene,rig.camera,p) for p in corners(target)]
            inside=all(0<=v.x<=1 and 0<=v.y<=1 and v.z>0 for v in uv)
            if not inside:raise AssertionError((scene.name,target,view,[(v.x,v.y) for v in uv]))
            presets.append({'scene':scene.name,'target':target,'view':view,'lens_mm':lens,
                'camera_world_location':list(rig.camera.matrix_world.translation),
                'target_world_location':list(rig.anchor.matrix_world.translation)})
    rig=CameraRig(scene).fit()
    for motion in ['dolly','orbit']:
        rig.fit();getattr(rig,motion)(1,30)
        points=[];angles=[]
        for frame in range(1,31):
            scene.frame_set(frame);bpy.context.view_layer.update()
            pos=rig.camera.matrix_world.translation.copy();points.append(pos)
            axis=-(rig.camera.matrix_world.to_3x3()@Vector((0,0,1)))
            target=rig.anchor.matrix_world.translation-pos
            angles.append(axis.angle(target))
        assert max(angles)<1e-3,(motion,max(angles))
        steps=[(b-a).length for a,b in zip(points,points[1:])]
        assert steps[0]<max(steps) and steps[-1]<max(steps)
        checks.append({'scene':scene.name,'motion':motion,'track_error_degrees':math.degrees(max(angles)),
                      'first_step_m':steps[0],'max_step_m':max(steps),'last_step_m':steps[-1]})
    rig.fit('Extension')
    part=next(o for o in bpy.data.collections['05_前伸'].all_objects if o.type=='MESH').parent
    original_location=part.location.copy()
    assert part.animation_data is None
    part.location=original_location;part.keyframe_insert('location',frame=1)
    part.location=original_location+Vector((.006,0,0));part.keyframe_insert('location',frame=30)
    rig.follow(part,1,30)
    offsets=[];target_errors=[]
    for frame in range(1,31):
        scene.frame_set(frame);bpy.context.view_layer.update()
        offsets.append(rig.camera.matrix_world.translation-part.matrix_world.translation)
        target_errors.append((rig.anchor.matrix_world.translation-part.matrix_world.translation).length)
    assert max((o-offsets[0]).length for o in offsets)<1e-5
    assert max(target_errors)<1e-5
    part.animation_data_clear();part.location=original_location
    scene.frame_set(1);rig.fit();bpy.context.view_layer.update()
    checks.append({'scene':scene.name,'motion':'follow_actual_extension_part','part':part.name,
                   'max_follow_offset_error_m':max((o-offsets[0]).length for o in offsets),
                   'max_target_error_m':max(target_errors)})
    assert fingerprint()==expected,'Temporary motion was not completely restored'
scene=bpy.data.scenes['Studio_Dark'];bpy.context.window.scene=scene;bpy.context.view_layer.update()
f,r,u=chassis_axes()
wheels=[o for o in objects_for('Mecanum Wheels') if '麦轮' in o.get('source_name','')]
wheel=max(wheels,key=lambda o:center_of(o).dot(f+r))
detail={'wheel_front':wheel.name,'wheel_source':wheel.get('source_name'),'belt_collection':MECHANISMS['Timing Belt']}
dump(ROOT/'03_director/detail_targets.json',detail)
dump(ROOT/'03_director/camera_presets.json',presets)
dump(ROOT/'04_output/reports/system_verification.json',{'saved_model_exact_match':True,'projection_presets_checked':len(presets),
     'camera_checks':checks,'final_model_exact_match':fingerprint()==expected,'detail_targets':detail})
print('SYSTEM_VERIFIED',len(presets),'camera presets',flush=True)
