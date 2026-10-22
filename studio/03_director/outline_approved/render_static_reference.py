"""Non-persistent two-module review. Does not save or replace any .blend/preset.
Deliverables are four comparison images (two modules, two views).
Intermediate renders/audit live in cache.
"""
import bpy,sys,json,hashlib,time,math
from pathlib import Path
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path(__file__).resolve().parents[2]
CACHE=ROOT/'04_output/cache/outline_reference_rerender'
CACHE.mkdir(parents=True,exist_ok=True)
PROFILE=json.loads((ROOT/'02_studio/presets/module_outline_approved.json').read_text(encoding='utf-8'))
STYLE=PROFILE['style'];SELECTION=PROFILE['edge_selection']
EDGE_WIDTH=STYLE['edge_width_px']
sys.path.insert(0,str(ROOT/'02_studio/scripts'));sys.path.insert(0,str(ROOT/'03_director'))
from studio_core import fingerprint,configure_device,dump
import module_focus as mf
from camera_control import chassis_axes,corners,center_of,aim
PROJECT=ROOT/PROFILE['source_project']

def camera_light_state():
    state={}
    for o in bpy.data.objects:
        if o.type not in ['CAMERA','LIGHT'] or o.name.startswith('OutlineReview'):continue
        entry={'parent':o.parent.name if o.parent else None,'basis':[list(r) for r in o.matrix_basis],
               'constraints':[(c.name,c.type,getattr(getattr(c,'target',None),'name',None)) for c in o.constraints]}
        if o.type=='CAMERA':entry['data']={'lens':o.data.lens,'shift':(o.data.shift_x,o.data.shift_y),
            'clip':(o.data.clip_start,o.data.clip_end),'sensor':(o.data.sensor_width,o.data.sensor_height,o.data.sensor_fit),
            'dof':o.data.dof.use_dof}
        else:entry['data']={'type':o.data.type,'energy':o.data.energy,'color':list(o.data.color),
                           'size':getattr(o.data,'size',None)}
        state[o.name]=entry
    return state

def review_camera(scene,width,height):
    """Independent opposite front diagonal; before/after share this one camera."""
    source=scene.camera
    cam=bpy.data.objects.new('OutlineReviewCamera',source.data.copy())
    scene.collection.objects.link(cam);cam.data.name='OutlineReviewLens'
    cam.data.dof.use_dof=False;cam.data.shift_x=0;cam.data.shift_y=0
    scene.camera=cam
    f,r,u=chassis_axes();point=center_of();direction=(f-r+u*.65).normalized()
    p=cam.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=width,y=height)
    tanx=1/p[0][0];tany=1/p[1][1]
    z=direction;x=u.cross(z).normalized();y=z.cross(x).normalized()
    pts=[p-point for p in corners()]
    margin=1.12
    distance=max(max(abs(p.dot(x))*margin/tanx+p.dot(z),abs(p.dot(y))*margin/tany+p.dot(z)) for p in pts)
    cam.location=point+direction*distance;aim(cam,point,u)
    target=bpy.data.objects.new('OutlineReviewTarget',None)
    scene.collection.objects.link(target);target.location=point
    tracker=cam.constraints.new('TRACK_TO');tracker.name='AlwaysTrack'
    tracker.target=target;tracker.mute=True
    bpy.context.view_layer.update()
    return cam

def rear_camera(scene):
    presets=json.loads((ROOT/'01_materials/reference/outline_approved_35/camera_views.json').read_text(encoding='utf-8'))
    preset=next(v for v in presets if v['name']=='02_整车后方45度')
    cam=bpy.data.objects.new('OutlineReviewRearCamera',scene.camera.data.copy())
    scene.collection.objects.link(cam);cam.data.name='OutlineReviewRearLens'
    cam.location=preset['location'];cam.rotation_euler=preset['rotation']
    cam.data.type='ORTHO';cam.data.ortho_scale=preset['ortho_scale']
    cam.data.sensor_fit='HORIZONTAL';cam.data.shift_x=0;cam.data.shift_y=0;cam.data.dof.use_dof=False
    target=bpy.data.objects.new('OutlineReviewRearTarget',None)
    scene.collection.objects.link(target);target.location=center_of()
    tracker=cam.constraints.new('TRACK_TO');tracker.name='AlwaysTrack';tracker.target=target;tracker.mute=True
    bpy.context.view_layer.update()
    return cam,preset

def build_occluder():
    """Read-only BVH from all original solids; used only to cull drawn edges."""
    vertices=[];polygons=[];offset=0
    for obj in bpy.data.collections['MODEL_原始装配'].all_objects:
        if obj.type!='MESH' or obj.hide_render:continue
        mesh=obj.data
        local=np.empty(len(mesh.vertices)*3,np.float32);mesh.vertices.foreach_get('co',local);local=local.reshape(-1,3)
        matrix=np.asarray(obj.matrix_world,dtype=np.float32)
        world=local@matrix[:3,:3].T+matrix[:3,3]
        loops=np.empty(len(mesh.loops),np.int32);mesh.loops.foreach_get('vertex_index',loops)
        counts=np.empty(len(mesh.polygons),np.int32);mesh.polygons.foreach_get('loop_total',counts)
        assert np.all(counts==3)
        vertices.extend(map(tuple,world.tolist()));polygons.extend(map(tuple,(loops.reshape(-1,3)+offset).tolist()))
        offset+=len(local)
    return BVHTree.FromPolygons(vertices,polygons,all_triangles=True,epsilon=1e-7)

def make_light_edge_material(scene):
    """sRGB #A8ADB3 compensated for unchanged exposure; 35% opacity."""
    mat=bpy.data.materials.new('OutlineReview_LightGrey_35pct');mat.use_nodes=True
    nodes=mat.node_tree.nodes;nodes.clear()
    out=nodes.new('ShaderNodeOutputMaterial');mix=nodes.new('ShaderNodeMixShader')
    transparent=nodes.new('ShaderNodeBsdfTransparent');emission=nodes.new('ShaderNodeEmission')
    srgb=np.array([int(STYLE['edge_color_srgb_hex'][i:i+2],16) for i in (1,3,5)],dtype=float)/255
    linear=np.where(srgb<=.04045,srgb/12.92,((srgb+.055)/1.055)**2.4)*2**(-scene.view_settings.exposure)
    emission.inputs['Color'].default_value=(*linear,1);emission.inputs['Strength'].default_value=1
    mix.inputs[0].default_value=STYLE['edge_opacity']
    mat.node_tree.links.new(transparent.outputs[0],mix.inputs[1]);mat.node_tree.links.new(emission.outputs[0],mix.inputs[2])
    mat.node_tree.links.new(mix.outputs[0],out.inputs['Surface'])
    return mat

def simplified_edges(scene,bvh,material):
    camera=scene.camera;camera_pos=camera.matrix_world.translation.copy()
    width=scene.render.resolution_x;height=scene.render.resolution_y
    projection=camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=width,y=height)
    focal_pixels=projection[0][0]*width/2
    camera_inv=camera.matrix_world.inverted()
    counts={'old_visible_segments':0,'new_visible_segments':0,'small_hole_loops_removed':0,
            'back_edges_removed':0,'occluded_edges_removed':0,'width_px_target':EDGE_WIDTH}
    nominal_widths=[]
    screen_lines=[]
    is_ortho=camera.data.type=='ORTHO'
    toward_camera=camera.matrix_world.to_quaternion()@Vector((0,0,1))
    view_projection=np.asarray(projection@camera_inv,dtype=np.float64)
    for copy in list(bpy.data.collections[scene.name+'__Display'].all_objects):
        if copy.type!='MESH':continue
        line=bpy.data.objects[copy.name+'__Edges']
        if line.hide_render:continue
        counts['old_visible_segments']+=len(line.data.splines)
        source=bpy.data.objects[copy['source_object']]
        verts,edges,normals,centers,a,b,valid,old_features=mf.edge_arrays(source.data)
        local_cam=source.matrix_world.inverted()@camera_pos
        if is_ortho:
            local_direction=source.matrix_world.inverted().to_3x3()@toward_camera
            facing=normals@np.asarray(local_direction)>0
        else:facing=np.einsum('ij,ij->i',normals,np.asarray(local_cam)-centers)>0
        silhouette=valid&(facing[a]!=facing[b])
        front=valid&(facing[a]|facing[b])
        dots=np.einsum('ij,ij->i',normals[a],normals[b])
        # Preserve silhouettes and major corners; remove shallow CAD seam detail.
        major=valid&((a==b)|(dots<math.cos(math.radians(SELECTION['major_crease_angle_degrees']))))
        candidate=(silhouette|major)&front
        counts['back_edges_removed']+=int(((old_features|silhouette)&~front).sum())
        # Remove entire small closed loops instead of dotted/per-triangle deletion.
        internal=np.flatnonzero(candidate&~silhouette).tolist()
        for chain in mf.edge_chains(edges,internal):
            pairs=edges[chain];ids=np.unique(pairs)
            degree=np.bincount(pairs.ravel(),minlength=len(verts))[ids]
            span=np.ptp(verts[ids],axis=0)
            if np.all(degree==2) and float(np.linalg.norm(span))<SELECTION['small_closed_feature_loop_max_diagonal_m']:
                candidate[chain]=False;counts['small_hole_loops_removed']+=1
        indices=np.flatnonzero(candidate)
        matrix=np.asarray(source.matrix_world,dtype=np.float32)
        world=verts@matrix[:3,:3].T+matrix[:3,3]
        kept=[]
        for index in indices:
            e=edges[index];mid=(world[e[0]]+world[e[1]])*.5
            origin=Vector(mid)+toward_camera*5 if is_ortho else camera_pos
            delta=Vector(mid)-origin;distance=delta.length
            hit,normal,face,hit_distance=bvh.ray_cast(origin,delta.normalized(),max(0,distance-SELECTION['ray_distance_tolerance_m']))
            if hit is None:kept.append(index)
            else:counts['occluded_edges_removed']+=1
        curve=line.data;curve.splines.clear();curve.materials.clear();curve.materials.append(material)
        # A per-part representative camera depth keeps diameter close to 0.4px.
        center=Vector((world.min(axis=0)+world.max(axis=0))/2)
        depth=max(.001,-(camera_inv@center).z)
        parent_scale=sum(source.matrix_world.to_scale())/3
        pixel_scale=focal_pixels if is_ortho else focal_pixels/depth
        curve.bevel_depth=EDGE_WIDTH/(2*pixel_scale*max(parent_scale,1e-8));curve.bevel_resolution=0
        nominal_widths.append(2*curve.bevel_depth*parent_scale*pixel_scale)
        for index in kept:
            v0,v1=verts[edges[index]]
            spline=curve.splines.new('POLY');spline.points.add(1)
            spline.points.foreach_set('co',(*v0,1,*v1,1))
            points=world[edges[index]]
            clip=np.c_[points,np.ones(2)]@view_projection.T
            ndc=clip[:,:2]/clip[:,3,None]
            xy=(ndc+1)*np.array([width/2,height/2]);xy[:,1]=height-xy[:,1]
            screen_lines.append(xy.tolist())
        # Composite this same derived line layer after denoising the surfaces.
        # This avoids denoising erasing subpixel lines; no duplicate 3D layer.
        line.hide_render=True
        counts['new_visible_segments']+=len(kept)
    counts['nominal_width_range_px']=[min(nominal_widths),max(nominal_widths)]
    return counts,screen_lines

def main():
    source_hash=hashlib.sha256(PROJECT.read_bytes()).hexdigest()
    bpy.ops.wm.open_mainfile(filepath=str(PROJECT))
    scene=bpy.data.scenes['Emphasis_Light'];bpy.context.window.scene=scene;bpy.context.view_layer.update()
    original=fingerprint();protected=camera_light_state();original_camera=scene.camera
    mechanism={'freestyle':bool(scene.render.use_freestyle),
        'source_mesh_modifiers':[(o.name,m.type) for o in bpy.data.collections['MODEL_原始装配'].all_objects for m in o.modifiers],
        'curve_objects':sum(o.type=='CURVE' for o in bpy.data.collections[scene.name+'__Display'].all_objects),
        'mechanism':'Independent generated CURVE objects, OBJECT material overrides; no extra outline layer added'}
    scene.render.resolution_percentage=100
    scene.cycles.samples=PROFILE['quality_validation']['review_samples'];scene.cycles.adaptive_threshold=.002
    scene.cycles.adaptive_min_samples=128;scene.cycles.use_denoising=True
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    device=configure_device(scene)
    bvh=build_occluder();edge_material=make_light_edge_material(scene)
    line_materials={o.name:[m for m in o.data.materials] for o in bpy.data.collections[scene.name+'__Display'].all_objects if o.type=='CURVE'}
    rear,preset=rear_camera(scene)
    result={'mechanism':mechanism,'device':device,'alpha_both':STYLE['context_face_opacity'],'samples':scene.cycles.samples,
            'line_compositing':'same derived CURVE edge selection, projected once after surface denoising; no 3D edge duplication',
            'rear_reference_camera':preset,
            'source_project_sha256':source_hash,'modules':[]}
    for view,camera,width,height,crop in [('original',original_camera,1920,1080,[650,0,1610,1080]),('rear',rear,960,1080,[0,0,960,1080])]:
      scene.camera=camera;scene.render.resolution_x=width;scene.render.resolution_y=height
      bpy.context.view_layer.update()
      camera_state=([list(r) for r in camera.matrix_world],camera.data.lens)
      for key in ['gimbal','extension']:
        mf.set_focus(scene,key,refresh=False)
        for line_name,mats in line_materials.items():
            line=bpy.data.objects[line_name];line.data.materials.clear()
            for mat in mats:line.data.materials.append(mat)
        mf.update_edges(scene)
        face=bpy.data.materials[scene.name+'__Ghost_Faces'];face.node_tree.nodes['Mix Shader'].inputs[0].default_value=STYLE['context_face_opacity']
        scene.render.filepath=str(CACHE/f'{view}_{key}_before.png')
        t=time.perf_counter();bpy.ops.render.render(write_still=True)
        record={'module':key,'view':view,'before_render_seconds':time.perf_counter()-t,'crop':crop,'render_size':[width,height]}
        record['edge_change'],screen_lines=simplified_edges(scene,bvh,edge_material)
        dump(CACHE/f'{view}_{key}_lines.json',{'lines':screen_lines,'width_px':EDGE_WIDTH,'color':STYLE['edge_color_srgb_hex'],'opacity':STYLE['edge_opacity']})
        scene.render.filepath=str(CACHE/f'{view}_{key}_after_faces.png')
        t=time.perf_counter();bpy.ops.render.render(write_still=True)
        record['after_render_seconds']=time.perf_counter()-t
        assert camera_state==([list(r) for r in camera.matrix_world],camera.data.lens)
        assert fingerprint()==original,'Original geometry/materials/hierarchy changed'
        assert camera_light_state()==protected,'An existing camera or light changed'
        result['modules'].append(record)
        dump(CACHE/'audit.json',result)
        print('COMPARISON_COMPLETE',view,key,record['edge_change'],flush=True)
    assert hashlib.sha256(PROJECT.read_bytes()).hexdigest()==source_hash
    result['original_cameras_lights_unchanged']=True;result['original_model_fingerprint_unchanged']=True
    result['source_blend_not_saved_or_modified']=True;result['only_two_modules_reviewed']=True
    dump(CACHE/'audit.json',result)
    print('OUTLINE_TRIAL_COMPLETE',flush=True)

if __name__=='__main__':main()
