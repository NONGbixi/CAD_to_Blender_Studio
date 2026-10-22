"""Versioned CAD emphasis: evaluated per-frame BVH and one screen outline layer.

Source geometry/materials stay untouched. Presentation overrides are reversible.
The same selector can generate 3D preview curves or a denoise-safe 2D line pass.
"""
from pathlib import Path
import sys,json,hashlib,math,time
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'03_director'))
import module_focus as mf


class OutlinePipeline:
    def __init__(self,scene,profile):
        self.scene=scene
        self.profile=json.loads(Path(profile).read_text(encoding='utf-8')) if isinstance(profile,(str,Path)) else profile
        self.style=self.profile['style'];self.select=self.profile['edge_selection']
        mf.configure_mapping(ROOT/self.profile['module_mapping'])
        self.display=bpy.data.collections[scene.name+'__Display']
        self.sources=sorted([o for o in bpy.data.collections['MODEL_原始装配'].all_objects if o.type=='MESH' and not o.hide_render],key=lambda o:o.name)
        self.copies={o['source_object']:o for o in self.display.all_objects if o.type=='MESH'}
        self.lines={n:bpy.data.objects[o.name+'__Edges'] for n,o in self.copies.items()}
        self.material=self.edge_material()

    def edge_material(self):
        name=self.scene.name+'__ApprovedOutline35'
        mat=bpy.data.materials.get(name)
        if mat is None:mat=bpy.data.materials.new(name)
        mat.use_nodes=True;nodes=mat.node_tree.nodes;nodes.clear()
        out=nodes.new('ShaderNodeOutputMaterial');mix=nodes.new('ShaderNodeMixShader')
        trans=nodes.new('ShaderNodeBsdfTransparent');em=nodes.new('ShaderNodeEmission')
        code=self.style['edge_color_srgb_hex'];rgb=np.array([int(code[i:i+2],16) for i in [1,3,5]])/255
        linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)*2**(-self.scene.view_settings.exposure)
        em.inputs[0].default_value=(*linear,1);mix.inputs[0].default_value=self.style['edge_opacity']
        mat.node_tree.links.new(trans.outputs[0],mix.inputs[1]);mat.node_tree.links.new(em.outputs[0],mix.inputs[2])
        mat.node_tree.links.new(mix.outputs[0],out.inputs['Surface'])
        return mat

    def geometry(self,excluded_ids=None):
        excluded_ids=excluded_ids or set()
        deps=bpy.context.evaluated_depsgraph_get();records=[];points=[];triangles=[];offset=0;digest=hashlib.sha256()
        for source in self.sources:
            if source['source_id'] in excluded_ids:continue
            evaluated=source.evaluated_get(deps)
            temporary=bool(source.modifiers) or source.data.shape_keys is not None
            mesh=evaluated.to_mesh() if temporary else source.data
            if temporary:mf._EDGE_CACHE.pop(mesh.name,None)
            arrays=mf.edge_arrays(mesh)
            verts,edges,normals,centers,a,b,valid,features=arrays
            matrix=evaluated.matrix_world.copy();world=verts@np.asarray(matrix)[:3,:3].T+np.asarray(matrix)[:3,3]
            loops=np.empty(len(mesh.loops),np.int32);mesh.loops.foreach_get('vertex_index',loops)
            counts=np.empty(len(mesh.polygons),np.int32);mesh.polygons.foreach_get('loop_total',counts)
            if not np.all(counts==3):raise ValueError('CAD render pipeline expects triangulated evaluated meshes')
            digest.update(source.name.encode());digest.update(world.tobytes());digest.update(loops.tobytes())
            points.extend(world.tolist());triangles.extend((loops.reshape(-1,3)+offset).tolist());offset+=len(verts)
            records.append({'source':source,'matrix':matrix,'world':world,'arrays':arrays,'line':self.lines[source.name]})
            if temporary:
                mf._EDGE_CACHE.pop(mesh.name,None);evaluated.to_mesh_clear()
        bvh=BVHTree.FromPolygons(points,triangles,all_triangles=True,epsilon=1e-7)
        return records,bvh,digest.hexdigest()

    def prepare_frame(self,module,preview_3d=False):
        tic=time.perf_counter();scene=self.scene
        mf.set_focus(scene,module,refresh=False)
        face=bpy.data.materials[scene.name+'__Ghost_Faces']
        face.node_tree.nodes['Mix Shader'].inputs[0].default_value=self.style['context_face_opacity']
        bpy.context.view_layer.update()
        active=set(mf.membership()[0][module])
        override=self.profile.get('module_context_overrides',{}).get(module,{})
        roots=override.get('fully_transparent_root_source_names',[])
        components=mf.sources();by_name={o.get('source_name'):o for o in components.values()}
        excluded=set()
        for name in roots:
            if name not in by_name:raise ValueError('Missing full-transparency source root: '+name)
            root=by_name[name]
            for obj in [root,*root.children_recursive]:
                if obj.type=='EMPTY' and 'source_id' in obj:excluded.add(obj['source_id'])
        excluded-=active
        for name,alpha in override.get('protected_context_alpha',{}).items():
            if name not in by_name:raise ValueError('Missing protected context source: '+name)
            if abs(alpha-self.style['context_face_opacity'])>1e-6:raise ValueError('Unsupported protected context alpha')
            excluded.discard(by_name[name]['source_id'])
        transparent_name=scene.name+'__Ghost_FullTransparent'
        transparent=bpy.data.materials.get(transparent_name)
        if excluded and transparent is None:transparent=mf.ghost_material(scene,'FullTransparent',0.0,.65)
        for name,copy in self.copies.items():
            if 'context_override_alpha' in copy:del copy['context_override_alpha']
            if copy['source_id'] in excluded:
                for slot in copy.material_slots:slot.link='OBJECT';slot.material=transparent
                copy.hide_render=True;self.lines[name].hide_render=True;copy['context_override_alpha']=0.0
        bpy.context.view_layer.update()
        records,bvh,geometry_digest=self.geometry(excluded)
        width=round(scene.render.resolution_x*scene.render.resolution_percentage/100)
        height=round(scene.render.resolution_y*scene.render.resolution_percentage/100)
        camera=scene.camera;camera_matrix=camera.matrix_world.copy();camera_pos=camera_matrix.translation
        camera_inv=camera_matrix.inverted();projection=camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=width,y=height)
        vp=np.asarray(projection@camera_inv);ortho=camera.data.type=='ORTHO'
        toward_camera=camera_matrix.to_quaternion()@Vector((0,0,1))
        edge_px=self.style['edge_width_px']*height/self.style['reference_height_px']
        outer=module=='fasteners' and self.profile['fasteners_focus']['outer_context_contour_only']
        if outer:
            mf._OUTER_MASK_CACHE.clear()
            mask=mf.outer_context_mask(scene,records)
        else:mask=None
        lines=[];stats={'frame':scene.frame_current,'module':module,'edge_width_px':edge_px,'edge_opacity':self.style['edge_opacity'],
            'context_face_opacity':self.style['context_face_opacity'],'candidate_edges':0,'visible_segments':0,'occluded_samples':0,
            'fully_transparent_root_source_names':roots,'fully_transparent_component_ids':sorted(excluded),
            'fully_transparent_meshes':sum(o['source_id'] in excluded for o in self.sources),
            'small_loops_removed':0,'outline_outer_only':outer,'active_meshes':0,'context_meshes':0,
            'evaluated_geometry_sha256':geometry_digest,'camera_matrix':[[float(v) for v in row] for row in camera_matrix]}
        def project(points):
            clip=np.c_[points,np.ones(len(points))]@vp.T
            xy=clip[:,:2]/clip[:,3,None];xy=(xy+1)*[width/2,height/2];xy[:,1]=height-xy[:,1]
            return xy,clip[:,3]
        for record in records:
            source=record['source'];line=record['line'];line.hide_render=True
            if source['source_id'] in active:
                stats['active_meshes']+=1
                display=self.copies[source.name]
                assert all(a.material==b.material for a,b in zip(display.material_slots,source.material_slots))
                continue
            stats['context_meshes']+=1
            if line.get('is_fastener',False) and self.style['hide_context_fastener_edges']:continue
            verts,edges,normals,centers,a,b,valid,_=record['arrays'];matrix=record['matrix'];world=record['world']
            if ortho:
                local=matrix.inverted().to_3x3()@toward_camera
                facing=normals@np.asarray(local)>0
            else:
                local=matrix.inverted()@camera_pos
                facing=np.einsum('ij,ij->i',normals,np.asarray(local)-centers)>0
            silhouette=valid&(facing[a]!=facing[b]);front=valid&(facing[a]|facing[b])
            dots=np.einsum('ij,ij->i',normals[a],normals[b])
            major=valid&((a==b)|(dots<math.cos(math.radians(self.select['major_crease_angle_degrees']))))
            candidate=silhouette.copy() if outer else (silhouette|major)&front
            if not outer:
                for chain in mf.edge_chains(edges,np.flatnonzero(candidate&~silhouette).tolist()):
                    pairs=edges[chain];ids=np.unique(pairs)
                    degree=np.bincount(pairs.ravel(),minlength=len(verts))[ids]
                    if np.all(degree==2) and float(np.linalg.norm(np.ptp(verts[ids],axis=0)))<self.select['small_closed_feature_loop_max_diagonal_m']:
                        candidate[chain]=False;stats['small_loops_removed']+=1
            selected=np.flatnonzero(candidate);stats['candidate_edges']+=len(selected)
            local_segments=[]
            for index in selected:
                v0,v1=edges[index];p0,p1=world[[v0,v1]];pixel,clip_w=project(np.array([p0,p1]))
                if np.any(clip_w<=0) or not np.isfinite(pixel).all():continue
                length=float(np.linalg.norm(pixel[1]-pixel[0]))
                if length<.01:continue
                pieces=max(1,int(math.ceil(length/self.select.get('max_visibility_segment_px',8))))
                pieces=min(256,pieces)
                for part in range(pieces):
                    t0=part/pieces;t1=(part+1)/pieces
                    wa=p0+(p1-p0)*t0;wb=p0+(p1-p0)*t1;mid=Vector((wa+wb)/2)
                    origin=mid+toward_camera*5 if ortho else camera_pos
                    delta=mid-origin;distance=delta.length
                    hit,_,_,_=bvh.ray_cast(origin,delta.normalized(),max(0,distance-self.select['ray_distance_tolerance_m']))
                    if hit is not None:stats['occluded_samples']+=1;continue
                    xy,_=project(np.array([wa,wb]))
                    if max(xy[:,0])<0 or min(xy[:,0])>=width or max(xy[:,1])<0 or min(xy[:,1])>=height:continue
                    if mask is not None:
                        direction=xy[1]-xy[0];normal=np.array([-direction[1],direction[0]])/max(np.linalg.norm(direction),1e-6)
                        midpoint=xy.mean(axis=0)
                        left=np.rint(midpoint+normal*2).astype(int);right=np.rint(midpoint-normal*2).astype(int)
                        def inside(p):
                            x,y=p
                            return bool(mask[height-1-y,x]) if 0<=x<width and 0<=y<height else False
                        if inside(left)==inside(right):continue
                    lines.append(xy.tolist())
                    if preview_3d:
                        local_segments.append((verts[v0]+(verts[v1]-verts[v0])*t0,verts[v0]+(verts[v1]-verts[v0])*t1))
            if preview_3d and local_segments:
                curve=line.data;curve.splines.clear();curve.materials.clear();curve.materials.append(self.material)
                depth=max(.001,-(camera_inv@Vector(world.mean(axis=0))).z)
                focal=projection[0][0]*width/2;pixel_scale=focal if ortho else focal/depth
                scale=sum(matrix.to_scale())/3
                curve.bevel_depth=edge_px/(2*pixel_scale*max(scale,1e-8));curve.bevel_resolution=0
                for v0,v1 in local_segments:
                    spline=curve.splines.new('POLY');spline.points.add(1);spline.points.foreach_set('co',(*v0,1,*v1,1))
                line.hide_render=False
        stats['visible_segments']=len(lines);stats['outline_prepare_seconds']=time.perf_counter()-tic
        scene['approved_outline_profile']=self.profile['profile_id'];scene['approved_context_alpha']=self.style['context_face_opacity']
        scene['approved_edge_opacity']=self.style['edge_opacity'];scene['approved_edge_width_px']=edge_px
        scene['outline_preview_only']=preview_3d
        return {'lines':lines,'width_px':edge_px,'color':self.style['edge_color_srgb_hex'],'opacity':self.style['edge_opacity'],
            'resolution':[width,height],'frame':scene.frame_current,'profile_id':self.profile['profile_id'],'stats':stats}
