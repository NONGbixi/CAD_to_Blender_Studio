"""Shared scene/device setup. Imported by build_studio and render_job."""
import bpy, sys, json, hashlib, time, subprocess, array
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'03_director'))
from camera_control import CameraRig, chassis_axes, corners, center_of, aim, MECHANISMS

def dump(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def fingerprint():
    """Hash exact geometry, transforms, hierarchy, shading and material assignments."""
    model=bpy.data.collections['MODEL_原始装配']
    objects={};materials={}
    for o in sorted(model.all_objects,key=lambda o:o.name):
        item={'type':o.type,'parent':o.parent.name if o.parent else None,
              'matrix':[[float(v) for v in row] for row in o.matrix_world],
              'hide_render':o.hide_render,'collections':sorted(c.name for c in o.users_collection),
              'modifiers':[m.type for m in o.modifiers]}
        if o.type=='MESH':
            m=o.data;h=hashlib.sha256()
            for seq,attr,code,n in [(m.vertices,'co','f',len(m.vertices)*3),
                (m.loops,'vertex_index','i',len(m.loops)),
                (m.polygons,'material_index','i',len(m.polygons)),
                (m.polygons,'use_smooth','b',len(m.polygons)),
                (m.edges,'use_edge_sharp','b',len(m.edges))]:
                buf=array.array(code,[0])*n;seq.foreach_get(attr,buf);h.update(buf.tobytes())
            item.update(sha256=h.hexdigest(),vertices=len(m.vertices),polygons=len(m.polygons),
                        materials=[x.name if x else None for x in m.materials])
            for mat in m.materials:
                if mat is None or mat.name in materials:continue
                nodes=[]
                for node in mat.node_tree.nodes if mat.use_nodes else []:
                    inputs={}
                    for v in node.inputs:
                        if hasattr(v,'default_value'):
                            val=v.default_value
                            try:val=list(val)
                            except TypeError:pass
                            if isinstance(val,(str,int,float,bool,list)):inputs[v.name]=val
                    nodes.append({'name':node.name,'type':node.bl_idname,'inputs':inputs})
                materials[mat.name]={'diffuse_color':list(mat.diffuse_color),'nodes':nodes,
                  'links':sorted([l.from_node.name,l.from_socket.name,l.to_node.name,l.to_socket.name] for l in mat.node_tree.links) if mat.use_nodes else []}
        objects[o.name]=item
    return {'objects':objects,'materials':materials,'mesh_count':sum(o['type']=='MESH' for o in objects.values()),
            'triangles':sum(o.get('polygons',0) for o in objects.values()),
            'components':sum(o.type=='EMPTY' and 'source_id' in o for o in model.all_objects)}

def setup_paths():
    cache=ROOT/'04_output/cache';cache.mkdir(parents=True,exist_ok=True)
    bpy.context.preferences.filepaths.temporary_directory=str(cache)
    bpy.context.preferences.filepaths.save_version=0

def gpu_snapshot():
    try:
        p=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu,power.draw,temperature.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10)
        if p.returncode:return {'error':p.stderr}
        vals=[x.strip() for x in p.stdout.strip().split(',')]
        return dict(zip(['name','driver','total_MiB','used_MiB','free_MiB','utilization_percent','power_W','temperature_C'],vals))
    except Exception as e:return {'error':str(e)}

def configure_device(scene, force=None):
    prefs=bpy.context.preferences.addons['cycles'].preferences
    attempts=[]
    for backend in ([force] if force else ['OPTIX','CUDA','HIP','ONEAPI','METAL']):
        if backend=='CPU':break
        try:
            prefs.compute_device_type=backend;prefs.get_devices()
            matching=[d for d in prefs.devices if d.type==backend]
            attempts.append({'backend':backend,'matching':[d.name for d in matching]})
            if matching:
                for d in prefs.devices:d.use=d in matching
                scene.cycles.device='GPU'
                return {'backend':backend,'devices':[d.name for d in matching],'attempts':attempts,
                        'status':'enumerated; actual render must succeed'}
        except Exception as e:attempts.append({'backend':backend,'error':str(e)})
    scene.cycles.device='CPU'
    return {'backend':'CPU','devices':['CPU'],'attempts':attempts,'status':'GPU unavailable or explicit CPU'}

def render_settings(scene,samples=64,width=1920,height=1080,preview=False):
    scene.render.engine='CYCLES'
    scene.render.resolution_x=width;scene.render.resolution_y=height;scene.render.resolution_percentage=100
    scene.render.pixel_aspect_x=scene.render.pixel_aspect_y=1
    scene.render.fps=30;scene.render.fps_base=1
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB'
    scene.render.image_settings.color_depth='8';scene.render.image_settings.compression=25
    scene.render.film_transparent=False
    scene.render.use_persistent_data=True
    scene.render.use_simplify=False
    scene.render.use_file_extension=True
    scene.render.use_motion_blur=False
    scene.cycles.samples=samples;scene.cycles.use_adaptive_sampling=True
    scene.cycles.adaptive_threshold=.02 if preview else .01
    scene.cycles.adaptive_min_samples=min(32,samples)
    scene.cycles.use_denoising=True;scene.cycles.denoiser='OPENIMAGEDENOISE'
    if hasattr(scene.cycles,'denoising_use_gpu'):scene.cycles.denoising_use_gpu=True
    scene.cycles.denoising_input_passes='RGB_ALBEDO_NORMAL'
    scene.cycles.preview_samples=16;scene.cycles.use_preview_denoising=True
    scene.cycles.preview_denoiser='OPTIX'
    scene.cycles.max_bounces=6;scene.cycles.diffuse_bounces=4;scene.cycles.glossy_bounces=4
    scene.cycles.transmission_bounces=4;scene.cycles.transparent_max_bounces=8
    scene.cycles.seed=17;scene.cycles.use_animated_seed=False
    scene.cycles.sample_clamp_direct=0;scene.cycles.sample_clamp_indirect=0
    scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
    scene.view_settings.gamma=1;scene.display_settings.display_device='sRGB'
    scene.frame_start=1;scene.frame_end=30

def apply_background(scene,preset):
    catcher=preset.get('shadow_catcher',False)
    bpy.data.objects[scene.name+'__Floor'].is_shadow_catcher=catcher
    scene.render.film_transparent=catcher
    scene.use_nodes=catcher
    if catcher:
        nodes=scene.node_tree.nodes;nodes.clear()
        layers=nodes.new('CompositorNodeRLayers');layers.scene=scene
        over=nodes.new('CompositorNodeAlphaOver');over.inputs[0].default_value=1
        v=preset.get('background_srgb',.94)
        linear=v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
        linear*=2**(-scene.view_settings.exposure)
        over.inputs[1].default_value=(linear,linear,linear,1)
        out=nodes.new('CompositorNodeComposite')
        scene.node_tree.links.new(layers.outputs['Image'],over.inputs[2])
        scene.node_tree.links.new(over.outputs['Image'],out.inputs[0])

def make_scene(preset):
    scene=bpy.data.scenes.new(preset['scene'])
    scene.collection.children.link(bpy.data.collections['MODEL_原始装配'])
    bpy.context.window.scene=scene;bpy.context.view_layer.update()
    scene.unit_settings.system='METRIC';scene.unit_settings.length_unit='MILLIMETERS'
    render_settings(scene)
    scene.view_settings.exposure=preset['exposure']
    world=bpy.data.worlds.new(scene.name+'__World');world.use_nodes=True;scene.world=world
    bg=world.node_tree.nodes.get('Background');bg.inputs[0].default_value=(*preset['world_color'],1)
    bg.inputs[1].default_value=preset['world_strength']
    col=bpy.data.collections.new(scene.name+'__Environment');scene.collection.children.link(col)
    f,r,u=chassis_axes();point=center_of();pts=corners()
    span=max(max(p.dot(a) for p in pts)-min(p.dot(a) for p in pts) for a in (f,r,u))
    scale=span/.45
    # CAD frame may be tilted. Compute true bottom from every original vertex.
    bottom=min((o.matrix_world@v.co).dot(u) for o in bpy.data.collections['MODEL_原始装配'].all_objects if o.type=='MESH' for v in o.data.vertices)-.0005
    floor_center=point+u*(bottom-point.dot(u))
    mesh=bpy.data.meshes.new(scene.name+'__FloorMesh')
    mesh.from_pydata([tuple(floor_center+r*x+f*y) for x,y in [(-20,-20),(20,-20),(20,20),(-20,20)]],[],[(0,1,2,3)])
    floor=bpy.data.objects.new(scene.name+'__Floor',mesh);col.objects.link(floor)
    mat=bpy.data.materials.new(scene.name+'__FloorMat');mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=(*preset['floor_color'],1)
    bsdf.inputs['Roughness'].default_value=1;bsdf.inputs['Specular IOR Level'].default_value=0
    floor.data.materials.append(mat)
    for light in preset['lights']:
        name=scene.name+'__'+light['name'];data=bpy.data.lights.new(name,'AREA')
        data.energy=light['watts']*scale**2;data.shape='DISK';data.size=light['size']*scale
        obj=bpy.data.objects.new(name,data);col.objects.link(obj)
        a,b,c=light['offset_FRU'];obj.location=point+(f*a+r*b+u*c)*scale
        aim(obj,point,u)
    apply_background(scene,preset)
    rig=CameraRig(scene).fit()
    scene['studio_preset']=preset['id'];scene['studio_scale']=scale
    scene['model_policy']='Shared original CAD collection; no geometry or material changes'
    scene['typography']='External 2D RGBA overlay: 03_director/typography'
    scene['mechanism_aliases']=json.dumps(MECHANISMS,ensure_ascii=False)
    return scene
