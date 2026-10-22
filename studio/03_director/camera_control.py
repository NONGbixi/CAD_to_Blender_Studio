"""Blender camera controls. No CAD object is moved or reparented.
Coordinates are relative to the chassis, not world Z. Distances are metres.
Example: rig = CameraRig(bpy.context.scene); rig.fit('Gripper', lens=85)
"""
import math
import bpy
from mathutils import Vector, Matrix

MECHANISMS = {
    'Mecanum Wheels': '01_四驱麦轮', 'Gimbal': '02_云台',
    'Timing Belt': '03_同步带升降', 'Gripper': '04_夹爪',
    'Extension': '05_前伸', 'Turntable': '06_转盘',
    'Whole': 'MODEL_原始装配',
}

def objects_for(target='Whole'):
    if isinstance(target, bpy.types.Object):
        return [o for o in [target, *target.children_recursive] if o.type == 'MESH']
    if target in bpy.data.objects:
        return objects_for(bpy.data.objects[target])
    name = MECHANISMS.get(target, target)
    col = bpy.data.collections.get(name)
    if not col:
        raise ValueError(f'Unknown actual mechanism collection/object: {target}')
    result = [o for o in col.all_objects if o.type == 'MESH' and not o.hide_render]
    if not result:
        raise ValueError(f'No visible mesh in {name}')
    return result

def corners(target='Whole'):
    return [o.matrix_world @ Vector(p) for o in objects_for(target) for p in o.bound_box]

def center_of(target='Whole'):
    pts = corners(target)
    return Vector([(min(p[i] for p in pts)+max(p[i] for p in pts))/2 for i in range(3)])

def chassis_axes():
    plate = next(o for o in bpy.data.collections['MODEL_原始装配'].all_objects
                 if o.type == 'EMPTY' and '底板_' in o.get('source_name', ''))
    f = plate.matrix_world.to_3x3().col[0].normalized()
    u = plate.matrix_world.to_3x3().col[1].normalized()
    return f, f.cross(u).normalized(), u

def smooth_keys(idblock):
    ad = getattr(idblock, 'animation_data', None)
    if ad and ad.action:
        for fc in ad.action.fcurves:
            for k in fc.keyframe_points:
                k.interpolation='BEZIER'
                k.handle_left_type=k.handle_right_type='AUTO_CLAMPED'

def aim(obj, target, up):
    z = (obj.location-Vector(target)).normalized()
    x = Vector(up).cross(z).normalized()
    y = z.cross(x).normalized()
    obj.rotation_euler=Matrix((x,y,z)).transposed().to_euler()

class CameraRig:
    def __init__(self, scene):
        self.scene=scene
        self.f,self.r,self.u=chassis_axes()
        name=scene.name+'__CameraRig'
        col=bpy.data.collections.get(name)
        if col is None:
            col=bpy.data.collections.new(name); scene.collection.children.link(col)
        self.collection=col
        def node(suffix, data=None):
            name=scene.name+'__'+suffix
            o=bpy.data.objects.get(name)
            if o is None:
                o=bpy.data.objects.new(name,data);col.objects.link(o)
            return o
        self.anchor=node('TrackingTarget')
        self.anchor.empty_display_size=.012
        self.focus=node('FocusTarget');self.focus.empty_display_size=.008
        self.boom=node('CameraMotion')
        data=bpy.data.cameras.get(scene.name+'__Lens')
        if data is None:data=bpy.data.cameras.new(scene.name+'__Lens')
        self.camera=node('Camera', data)
        self.camera.parent=self.boom
        self.camera.location=(0,0,0)
        self.camera.data.type='PERSP';self.camera.data.sensor_width=36
        self.camera.data.clip_start=.0005;self.camera.data.clip_end=100
        con=self.camera.constraints.get('AlwaysTrack') or self.camera.constraints.new('TRACK_TO')
        con.name='AlwaysTrack';con.target=self.anchor;con.track_axis='TRACK_NEGATIVE_Z';con.up_axis='UP_Y'
        con.use_target_z=True
        # Target local Z is the camera up reference; keep original CAD world orientation.
        self.anchor.rotation_euler=self.u.to_track_quat('Z','Y').to_euler()
        self.camera.data.dof.focus_object=self.focus
        scene.camera=self.camera

    def clear_animation(self):
        for ob in [self.boom,self.anchor,self.focus,self.camera,self.camera.data]:
            ob.animation_data_clear()

    def track_object(self, obj, local_offset=(0,0,0)):
        if isinstance(obj,str):obj=bpy.data.objects[obj]
        if self.anchor.constraints.get('FollowActualPart'):
            self.anchor.constraints.remove(self.anchor.constraints['FollowActualPart'])
        c=self.anchor.constraints.new('COPY_LOCATION');c.name='FollowActualPart';c.target=obj
        self.anchor.location=Vector(local_offset)
        c.use_offset=True
        self.focus.constraints.clear()
        c=self.focus.constraints.new('COPY_LOCATION');c.target=self.anchor
        return obj

    def fit(self,target='Whole',lens=50,view='hero',margin=1.22,dof=False,fstop=8,shift_x=-.09):
        self.clear_animation()
        self.anchor.constraints.clear();self.focus.constraints.clear()
        point=center_of(target)
        self.anchor.location=point;self.focus.location=point
        directions={'hero':self.f+self.r+self.u*.72,
                    'rear':-self.f-self.r+self.u*.72,
                    'low':self.f+self.r+self.u*.12,
                    'top':self.u+self.f*.0001,
                    'macro':self.f+self.r+self.u*.4}
        direction=directions[view].normalized()
        # Build a temporary optical frame with stable top-view up direction.
        up=self.f if view=='top' else self.u
        self.anchor.rotation_euler=up.to_track_quat('Z','Y').to_euler()
        z=direction;x=up.cross(z).normalized();y=z.cross(x).normalized()
        aspect=self.scene.render.resolution_x/self.scene.render.resolution_y
        tanx=18/lens;tany=tanx/aspect
        pts=[p-point for p in corners(target)]
        # shift_x changes safe horizontal half extent; all corners remain within frame.
        safe_x=max(.45,1-2*abs(shift_x))
        distance=max(max(abs(p.dot(x))*margin/(tanx*safe_x)+p.dot(z),
                         abs(p.dot(y))*margin/tany+p.dot(z)) for p in pts)
        self.boom.location=point+direction*distance
        self.camera.data.lens=lens;self.camera.data.shift_x=shift_x;self.camera.data.shift_y=0
        self.camera.data.dof.use_dof=dof;self.camera.data.dof.aperture_fstop=fstop
        self.scene['camera_target']=str(target);self.scene['camera_view']=view
        bpy.context.view_layer.update()
        return self

    def dolly(self,start=1,end=30,factor=0.96):
        p=self.anchor.matrix_world.translation.copy()
        initial=self.boom.location.copy()
        self.boom.location=initial;self.boom.keyframe_insert('location',frame=start)
        self.boom.location=p+(initial-p)*factor;self.boom.keyframe_insert('location',frame=end)
        smooth_keys(self.boom);self.scene.frame_set(start)
        return self

    def orbit(self,start=1,end=30,degrees=12):
        from mathutils import Quaternion
        p=self.anchor.location.copy();offset=self.boom.location-p
        # Bake a smooth arc (not a straight chord) with gentle ease in/out.
        for frame in range(start,end+1):
            t=(frame-start)/max(1,end-start);s=t*t*(3-2*t)
            self.boom.location=p+Quaternion(self.u,math.radians(degrees)*s)@offset
            self.boom.keyframe_insert('location',frame=frame)
        smooth_keys(self.boom);self.scene.frame_set(start)
        return self

    def animate_lens(self,start=1,end=30,from_mm=50,to_mm=85):
        self.camera.data.lens=from_mm;self.camera.data.keyframe_insert('lens',frame=start)
        self.camera.data.lens=to_mm;self.camera.data.keyframe_insert('lens',frame=end)
        smooth_keys(self.camera.data);self.scene.frame_set(start)
        return self

    def follow(self,obj,start=1,end=30):
        """Follow the actual part with camera and focus; does not animate the part."""
        if isinstance(obj,str):obj=bpy.data.objects[obj]
        self.scene.frame_set(start);bpy.context.view_layer.update()
        p=obj.matrix_world.translation.copy()
        offset=self.boom.location-p
        self.track_object(obj)
        for frame in range(start,end+1):
            self.scene.frame_set(frame);bpy.context.view_layer.update()
            self.boom.location=obj.matrix_world.translation+offset
            self.boom.keyframe_insert('location',frame=frame)
        smooth_keys(self.boom);self.scene.frame_set(start)
        return self
