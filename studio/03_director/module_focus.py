"""Nine-module historical CAD ghost presentation. Source meshes/materials remain unchanged.
For the approved 2026-10-21 35% outline style, see outline_approved/README.md
and 02_studio/presets/module_outline_approved.json. Legacy F12 is not that pipeline.
Context: transparent surfaces + geometric crease/silhouette curves, no triangle grid.
Every display object shares the original Mesh datablock, with OBJECT material overrides.
"""
from pathlib import Path
import json,math,sys,subprocess,shutil,os
import bpy
import numpy as np
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
CONFIG=json.loads((ROOT/'03_director/module_groups.json').read_text(encoding='utf-8'))
MODULES=CONFIG['modules']
_EDGE_CACHE={}
_OUTER_MASK_CACHE={}

def configure_mapping(path=None):
    """Select a versioned actual-object mapping without changing legacy projects."""
    global CONFIG,MODULES
    if path is None:
        current=ROOT/'project_current.json'
        path=ROOT/'03_director/module_groups.json'
        if current.exists():
            record=json.loads(current.read_text(encoding='utf-8'))
            projects=[(ROOT/record[k]).resolve() for k in ['studio_base','studio_emphasis']]
            if bpy.data.filepath and Path(bpy.data.filepath).resolve() in projects:
                path=ROOT/record['module_mapping']
    CONFIG=json.loads(Path(path).read_text(encoding='utf-8'));MODULES=CONFIG['modules']
    _EDGE_CACHE.clear();_OUTER_MASK_CACHE.clear()
    return CONFIG

configure_mapping()

def sources():
    return {o['source_id']:o for o in bpy.data.collections['MODEL_原始装配'].all_objects if o.type=='EMPTY' and 'source_id' in o}

def membership():
    components=sources();result={};claimed={}
    for m in MODULES:
        ids=set()
        roots=m['root_ids']
        if m.get('selector')=='all_standard_fasteners':
            roots=[sid for sid,o in components.items() if any(token in o.get('source_name','') for token in ['DIN7984','ISO4762','ISO4032','铜柱'])]
        for sid in roots:
            if sid not in components:raise ValueError('Missing actual component '+sid)
            for obj in [components[sid],*components[sid].children_recursive]:
                if obj.type=='EMPTY' and 'source_id' in obj:ids.add(obj['source_id'])
        for sid in ids:
            if sid in claimed and not m.get('aggregate'):raise ValueError(f'Overlapping membership {sid}: {claimed[sid]} / {m["key"]}')
            if sid not in claimed:claimed[sid]=m['key']
        result[m['key']]=sorted(ids)
    return result,claimed

def module(value):
    return next(m for m in MODULES if value in [m['key'],m['id'],m['name'],m['collection']])

def ghost_material(scene,kind,opacity,tone):
    name=scene.name+'__Ghost_'+kind
    mat=bpy.data.materials.get(name)
    if mat:return mat
    mat=bpy.data.materials.new(name);mat.use_nodes=True
    nodes=mat.node_tree.nodes;nodes.clear()
    out=nodes.new('ShaderNodeOutputMaterial');mix=nodes.new('ShaderNodeMixShader')
    trans=nodes.new('ShaderNodeBsdfTransparent');em=nodes.new('ShaderNodeEmission')
    v=tone/12.92 if tone<=.04045 else ((tone+.055)/1.055)**2.4
    v*=2**(-scene.view_settings.exposure)
    em.inputs['Color'].default_value=(v,v,v,1);em.inputs['Strength'].default_value=1
    mix.inputs[0].default_value=opacity
    mat.node_tree.links.new(trans.outputs[0],mix.inputs[1]);mat.node_tree.links.new(em.outputs[0],mix.inputs[2])
    mat.node_tree.links.new(mix.outputs[0],out.inputs['Surface'])
    mat['ghost_opacity']=opacity;mat['display_srgb']=tone
    return mat

def edge_arrays(mesh):
    """Feature edges from adjacency/dihedral; coplanar CAD triangle diagonals excluded."""
    key=mesh.name
    if key in _EDGE_CACHE:return _EDGE_CACHE[key]
    n=len(mesh.polygons);e=len(mesh.edges)
    verts=np.empty(len(mesh.vertices)*3,np.float32);mesh.vertices.foreach_get('co',verts);verts=verts.reshape(-1,3)
    edges=np.empty(e*2,np.int32);mesh.edges.foreach_get('vertices',edges);edges=edges.reshape(-1,2)
    normals=np.empty(n*3,np.float32);mesh.polygons.foreach_get('normal',normals);normals=normals.reshape(-1,3)
    centers=np.empty(n*3,np.float32);mesh.polygons.foreach_get('center',centers);centers=centers.reshape(-1,3)
    loops=np.empty(len(mesh.loops),np.int32);mesh.loops.foreach_get('edge_index',loops)
    counts=np.empty(n,np.int32);mesh.polygons.foreach_get('loop_total',counts)
    faces=np.repeat(np.arange(n,dtype=np.int32),counts)
    a=np.full(e,n,np.int32);b=np.full(e,-1,np.int32)
    np.minimum.at(a,loops,faces);np.maximum.at(b,loops,faces)
    valid=(a<n)&(b>=0);ai=np.minimum(a,max(0,n-1));bi=np.maximum(b,0)
    dots=np.einsum('ij,ij->i',normals[ai],normals[bi])
    feature=valid&((a==b)|(dots<math.cos(math.radians(CONFIG['style']['crease_angle_degrees']))))
    data=(verts,edges,normals,centers,ai,bi,valid,feature)
    _EDGE_CACHE[key]=data
    return data

def selected_edges(source,camera):
    verts,edges,normals,centers,a,b,valid,feature=edge_arrays(source.data)
    local=source.matrix_world.inverted()@camera.matrix_world.translation
    facing=np.einsum('ij,ij->i',normals,np.asarray(local,dtype=np.float32)-centers)>0
    silhouette=valid&(facing[a]!=facing[b])
    selected=feature|silhouette
    return verts,edges[selected],int(feature.sum()),int(silhouette.sum()),silhouette[selected]

def edge_chains(edges,indices):
    """Connected paths preserve continuous contours when reducing detail density."""
    adjacency={}
    for i in indices:
        a,b=edges[i];adjacency.setdefault(int(a),[]).append(i);adjacency.setdefault(int(b),[]).append(i)
    unused=set(indices);chains=[]
    def walk(first,start):
        chain=[];current=first;v=start
        while current in unused:
            unused.remove(current);chain.append(current)
            a,b=map(int,edges[current]);v=b if a==v else a
            if len(adjacency[v])!=2:break
            nxt=[i for i in adjacency[v] if i in unused]
            if not nxt:break
            current=nxt[0]
        return chain
    for v,items in adjacency.items():
        if len(items)==2:continue
        for i in items:
            if i in unused:chains.append(walk(i,v))
    while unused:
        first=min(unused);chains.append(walk(first,int(edges[first,0])))
    return chains

def outer_context_mask(scene,records):
    """Opaque auxiliary mask finds the external envelope, not hidden inner edges.
    Only presentation copies are changed temporarily; all state is restored.
    """
    camera=scene.camera;w=scene.render.resolution_x;h=scene.render.resolution_y
    key=(scene.name,scene.frame_current,w,h,camera.data.lens,camera.data.shift_x,camera.data.shift_y,
         tuple(v for row in camera.matrix_world for v in row),
         tuple(v for rec in records for row in bpy.data.objects[rec['line']['source_object']].matrix_world for v in row))
    if key in _OUTER_MASK_CACHE:return _OUTER_MASK_CACHE[key]
    main=bpy.data.collections[scene.name+'__Display']
    meshes=[o for o in main.all_objects if o.type=='MESH'];curves=[o for o in main.all_objects if o.type=='CURVE']
    environment=[o for o in bpy.data.collections[scene.name+'__Environment'].all_objects if o.type=='MESH']
    objects=[*meshes,*curves,*environment];visibility=[(o,o.hide_render) for o in objects]
    engine=scene.render.engine;nodes=scene.use_nodes;transparent=scene.render.film_transparent
    path=scene.render.filepath;mode=scene.render.image_settings.color_mode
    shading=scene.display.shading
    settings={p:getattr(shading,p) for p in ['light','color_type','single_color','show_shadows','show_cavity','show_object_outline','show_xray']}
    settings['single_color']=tuple(settings['single_color'])
    cache=ROOT/'04_output/cache';cache.mkdir(parents=True,exist_ok=True)
    raw=cache/(scene.name+'_outer_alpha.png');filled=cache/(scene.name+'_outer_filled.png')
    try:
        selected=set(membership()[0][scene['focus_module']])
        for o in meshes:o.hide_render=o['source_id'] in selected or o.get('original_hidden',False)
        for o in [*curves,*environment]:o.hide_render=True
        scene.render.engine='BLENDER_WORKBENCH';scene.use_nodes=False;scene.render.film_transparent=True
        scene.render.image_settings.color_mode='RGBA';scene.render.filepath=str(raw)
        shading.light='FLAT';shading.color_type='SINGLE';shading.single_color=(1,1,1)
        shading.show_shadows=False;shading.show_cavity=False;shading.show_object_outline=False;shading.show_xray=False
        bpy.context.view_layer.update();bpy.ops.render.render(write_still=True)
    finally:
        scene.render.engine=engine;scene.use_nodes=nodes;scene.render.film_transparent=transparent
        scene.render.filepath=path;scene.render.image_settings.color_mode=mode
        for prop,value in settings.items():setattr(shading,prop,value)
        for o,hidden in visibility:o.hide_render=hidden
        bpy.context.view_layer.update()
    python=os.environ.get('CAD_PYTHON') or shutil.which('python')
    if not python:raise RuntimeError('System Python + Pillow is required for external-contour extraction')
    subprocess.run([python,str(ROOT/'03_director/typography/fill_outer_mask.py'),str(raw),str(filled)],check=True)
    image=bpy.data.images.load(str(filled),check_existing=False)
    data=np.empty(w*h*4,np.float32);image.pixels.foreach_get(data)
    mask=data.reshape(h,w,4)[:,:,0]>.5;bpy.data.images.remove(image)
    _OUTER_MASK_CACHE[key]=mask
    return mask

def outer_edges(scene,record,mask):
    """Keep only camera silhouette segments adjacent to the filled outer envelope."""
    w=scene.render.resolution_x;h=scene.render.resolution_y;camera=scene.camera
    source=bpy.data.objects[record['line']['source_object']]
    projection=camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(),x=w,y=h)
    matrix=np.asarray(projection@camera.matrix_world.inverted()@source.matrix_world,dtype=np.float32)
    edges=record['edges'];vertices=record['verts']
    def project(v):
        p=v@matrix[:3,:3].T+matrix[:3,3]
        divisor=v@matrix[3,:3]+matrix[3,3]
        xy=p[:,:2]/divisor[:,None]
        xy=(xy+1)*np.array([w/2,h/2]);return xy
    a=project(vertices[edges[:,0]]);b=project(vertices[edges[:,1]])
    midpoint=(a+b)/2;direction=b-a
    lengths=np.linalg.norm(direction,axis=1);normal=np.stack([-direction[:,1],direction[:,0]],axis=1)/np.maximum(lengths[:,None],1e-6)
    left=np.rint(midpoint+normal*2).astype(np.int32);right=np.rint(midpoint-normal*2).astype(np.int32)
    valid=(left[:,0]>=0)&(left[:,0]<w)&(left[:,1]>=0)&(left[:,1]<h)&(right[:,0]>=0)&(right[:,0]<w)&(right[:,1]>=0)&(right[:,1]<h)
    keep=np.zeros(len(edges),np.bool_)
    indices=np.flatnonzero(valid & record['silhouette_mask'])
    keep[indices]=mask[left[indices,1],left[indices,0]]!=mask[right[indices,1],right[indices,0]]
    return keep

def update_edges(scene):
    """Refresh camera-dependent silhouettes. Call after frame_set for moving cameras."""
    context=bpy.data.collections[scene.name+'__Display']
    camera=scene.camera
    target=camera.constraints['AlwaysTrack'].target
    distance=(camera.matrix_world.translation-target.matrix_world.translation).length
    relative_width=(distance/max(scene.get('ghost_reference_distance',distance),1e-6))*(scene.get('ghost_reference_lens',camera.data.lens)/camera.data.lens)
    relative_width=max(.05,min(4,relative_width))
    records=[];total=0
    for obj in list(context.all_objects):
        if obj.type!='MESH' or 'source_object' not in obj:continue
        line=bpy.data.objects.get(obj.name+'__Edges')
        if line is None:continue
        source=bpy.data.objects[obj['source_object']]
        verts,edges,features,silhouettes,is_silhouette=selected_edges(source,camera)
        records.append({'line':line,'verts':verts,'edges':edges,'features':features,'silhouettes':silhouettes,
                        'silhouette_mask':is_silhouette,'keep':np.ones(len(edges),np.bool_)})
    override=CONFIG['style'].get('overrides',{}).get(scene.get('focus_module'),{})
    fraction=override.get('edge_fraction',1)
    visible=[r for r in records if not r['line'].hide_render]
    full_count=sum(len(r['edges']) for r in visible)
    if override.get('outer_only',False):
        mask=outer_context_mask(scene,visible)
        for rec in visible:rec['keep']=outer_edges(scene,rec,mask)
    elif fraction<1:
        mandatory=sum(int(r['silhouette_mask'].sum()) for r in visible)
        candidates=[]
        for record_index,rec in enumerate(visible):
            rec['keep']=rec['silhouette_mask'].copy()
            indices=np.flatnonzero(~rec['silhouette_mask']).tolist()
            for chain in edge_chains(rec['edges'],indices):
                pair=rec['edges'][chain];v=rec['verts']
                length=float(np.linalg.norm(v[pair[:,0]]-v[pair[:,1]],axis=1).sum())
                candidates.append((length,record_index,chain))
        remaining=max(0,round(full_count*fraction)-mandatory)
        for _,record_index,chain in sorted(candidates,key=lambda a:(-a[0],a[1],a[2][0])):
            if len(chain)<=remaining:
                visible[record_index]['keep'][chain]=True;remaining-=len(chain)
    for rec in records:
        line=rec['line'];verts=rec['verts'];edges=rec['edges'][rec['keep']]
        curve=line.data;curve.splines.clear()
        curve.bevel_depth=CONFIG['style']['edge_radius_m']*relative_width*(.60 if line.get('is_fastener',False) else 1)
        for a,b in edges:
            spline=curve.splines.new('POLY');spline.points.add(1)
            spline.points.foreach_set('co',(*verts[a],1,*verts[b],1))
        line['feature_edges']=rec['features'];line['silhouette_edges']=rec['silhouettes']
        line['rendered_segments']=len(edges);total+=len(edges)
    scene['ghost_edge_segments']=total
    kept_visible=sum(int(r['keep'].sum()) for r in visible)
    scene['ghost_visible_edges_before_reduction']=full_count
    scene['ghost_visible_edges_after_reduction']=kept_visible
    scene['ghost_edge_retention_actual']=kept_visible/max(1,full_count)
    scene['ghost_reduction_mode']='outer' if override.get('outer_only',False) else str(fraction)
    return total

def build_display(scene):
    members,claimed=membership()
    target=scene.camera.constraints['AlwaysTrack'].target
    scene['ghost_reference_distance']=(scene.camera.matrix_world.translation-target.matrix_world.translation).length
    scene['ghost_reference_lens']=scene.camera.data.lens
    main=bpy.data.collections.new(scene.name+'__Display');scene.collection.children.link(main)
    groups={}
    for m in MODULES:
        col=bpy.data.collections.new(scene.name+'__'+m['collection']);main.children.link(col);groups[m['key']]=col
    unknown=bpy.data.collections.new(scene.name+'__Context_Unassigned');main.children.link(unknown)
    style=CONFIG['style'];key=scene['studio_preset'];tone=style[key]
    fasteners=set(members['fasteners'])
    face=ghost_material(scene,'Faces',style['face_opacity'],tone['face_srgb'])
    edge=ghost_material(scene,'Edges',style['edge_opacity'],tone['edge_srgb'])
    fine=ghost_material(scene,'SmallEdges',style['edge_opacity']*style['small_hardware_edge_factor'],tone.get('small_edge_srgb',tone['edge_srgb']))
    for source in list(bpy.data.collections['MODEL_原始装配'].all_objects):
        if source.type!='MESH':continue
        sid=source['source_id'];group=claimed.get(sid,'unassigned');col=groups.get(group,unknown)
        # Blender truncates ID names at its byte limit. Keep stable short names,
        # especially for Chinese wheel/motor names, so no edge object is missed.
        ob=bpy.data.objects.new(scene.name+'__D__'+source.data.name,source.data);col.objects.link(ob)
        ob.matrix_world=source.matrix_world.copy()
        con=ob.constraints.new('COPY_TRANSFORMS');con.name='FollowOriginalCAD';con.target=source
        ob['source_object']=source.name;ob['source_id']=sid;ob['focus_module']=group
        ob['original_hidden']=source.hide_render
        for slot in ob.material_slots:slot.link='OBJECT';slot.material=face
        ob.visible_shadow=False;ob.visible_diffuse=False;ob.visible_glossy=False
        data=bpy.data.curves.new(ob.name+'__Curve','CURVE');data.dimensions='3D'
        data.resolution_u=1;data.bevel_depth=style['edge_radius_m']*(.60 if sid in fasteners else 1);data.bevel_resolution=0;data.resolution_u=1
        line=bpy.data.objects.new(ob.name+'__Edges',data);col.objects.link(line)
        line.parent=ob;line.matrix_parent_inverse.identity()
        line['focus_module']=group;line['source_object']=source.name;line['source_id']=sid;line['is_fastener']=sid in fasteners
        data.materials.append(fine if sid in fasteners else edge)
        line.visible_shadow=False;line.visible_diffuse=False;line.visible_glossy=False
        # Cross-module aggregate links reference the same display objects.
        if sid in fasteners and group!='fasteners':
            groups['fasteners'].objects.link(ob);groups['fasteners'].objects.link(line)
    scene.view_layers[0].layer_collection.children['MODEL_原始装配'].exclude=True
    scene.cycles.transparent_max_bounces=128
    bpy.context.view_layer.update()
    update_edges(scene)
    set_focus(scene,'lift')
    return members

def set_focus(scene,which='lift',strength=1.0,refresh=True):
    """Switch all eight modules by ID/key/name. strength=0 restores original full color."""
    selected=module(which);style=CONFIG['style'];main=bpy.data.collections[scene.name+'__Display']
    selected_ids=set(membership()[0][selected['key']])
    strength=max(0,min(1,float(strength)))
    face=bpy.data.materials[scene.name+'__Ghost_Faces']
    for ob in list(main.all_objects):
        group=ob.get('focus_module');active=ob.get('source_id') in selected_ids or strength==0
        hidden=bool(ob.get('original_hidden',False))
        if ob.type=='MESH':
            source=bpy.data.objects[ob['source_object']]
            for i,slot in enumerate(ob.material_slots):
                slot.link='OBJECT';slot.material=source.material_slots[i].material if active else face
            ob.hide_render=hidden
            ob.visible_shadow=active;ob.visible_diffuse=active;ob.visible_glossy=active
            ob.color=(1,1,1,1) if active else (.65,.65,.65,.08)
        elif ob.type=='CURVE':ob.hide_render=active or strength==0 or (ob.get('is_fastener',False) and style.get('hide_fastener_context_edges',False))
    # Opacity is independently controllable, without touching source material nodes.
    opacity=style.get('overrides',{}).get(selected['key'],{}).get('face_opacity',style['face_opacity'])
    face.node_tree.nodes.get('Mix Shader').inputs[0].default_value=1-(1-opacity)*strength
    scene['focus_module']=selected['key'];scene['focus_label']=selected['name'];scene['focus_strength']=strength
    bpy.context.view_layer.update()
    override=style.get('overrides',{}).get(selected['key'],{}) if strength else {}
    desired='outer' if override.get('outer_only',False) else str(override.get('edge_fraction',1))
    if refresh and scene.get('ghost_reduction_mode',str(1))!=desired:update_edges(scene)
    return selected

def animate_focus(scene,which,start=1,end=15):
    """Smooth face/edge transition. This template animates only presentation overrides."""
    from camera_control import smooth_keys
    selected=set_focus(scene,which)
    style=CONFIG['style']
    opacity=style.get('overrides',{}).get(selected['key'],{}).get('face_opacity',style['face_opacity'])
    for kind,endvalue in [('Faces',opacity),('Edges',style['edge_opacity']),
                          ('SmallEdges',style['edge_opacity']*style['small_hardware_edge_factor'])]:
        tree=bpy.data.materials[scene.name+'__Ghost_'+kind].node_tree
        factor=tree.nodes.get('Mix Shader').inputs[0]
        factor.default_value=1 if kind=='Faces' else 0
        factor.keyframe_insert('default_value',frame=start)
        factor.default_value=endvalue;factor.keyframe_insert('default_value',frame=end)
        smooth_keys(tree)
    scene.frame_set(start)
    return selected
