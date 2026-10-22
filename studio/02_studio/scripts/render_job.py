"""Run with blender -b --factory-startup --python render_job.py -- [arguments]."""
import argparse,datetime,hashlib,json,os,sys,time,struct,zlib
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from studio_core import *

def valid_png(path,width,height):
    try:
        with open(path,'rb') as f:
            if f.read(8)!=b'\x89PNG\r\n\x1a\n':return False
            first=True
            while True:
                raw=f.read(8)
                if len(raw)!=8:return False
                n,kind=struct.unpack('>I4s',raw);data=f.read(n);crc=f.read(4)
                if len(data)!=n or len(crc)!=4 or zlib.crc32(kind+data)&0xffffffff!=struct.unpack('>I',crc)[0]:return False
                if first:
                    if kind!=b'IHDR' or struct.unpack('>II',data[:8])!=(width,height):return False
                    first=False
                if kind==b'IEND':return True
    except (OSError,ValueError):return False

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--studio',choices=['light','dark'],default='light')
    parser.add_argument('--job',required=True)
    parser.add_argument('--target',default='Whole')
    parser.add_argument('--view',choices=['hero','rear','low','top','macro'],default='hero')
    parser.add_argument('--lens',type=float,default=50)
    parser.add_argument('--samples',type=int,default=64)
    parser.add_argument('--width',type=int,default=1920);parser.add_argument('--height',type=int,default=1080)
    parser.add_argument('--start',type=int,default=1);parser.add_argument('--end',type=int,default=1)
    parser.add_argument('--motion',choices=['none','dolly','orbit'],default='none')
    parser.add_argument('--motion-start',type=int,default=1);parser.add_argument('--motion-end',type=int,default=30)
    parser.add_argument('--no-denoise',action='store_true');parser.add_argument('--dof',action='store_true')
    parser.add_argument('--fstop',type=float,default=8)
    parser.add_argument('--backend',default=None)
    parser.add_argument('--sequence',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if not args.job.replace('_','').replace('-','').isalnum():raise ValueError('Use a simple job name')
    if args.start<1 or args.end<args.start or args.motion_end<=args.motion_start:
        raise ValueError('Invalid frame range')
    if min(args.width,args.height,args.samples)<=0:raise ValueError('Resolution/samples must be positive')
    setup_paths();t0=time.perf_counter()
    project=Path(os.environ.get('CAD_STUDIO_BLEND',ROOT/'02_studio/studio.blend'))
    bpy.ops.wm.open_mainfile(filepath=str(project))
    scene=bpy.data.scenes['Studio_'+args.studio.title()];bpy.context.window.scene=scene
    render_settings(scene,args.samples,args.width,args.height,preview=args.width<1920)
    # Load JSON on every job: changing a preset takes effect without rebuilding geometry.
    preset=json.loads((ROOT/f'02_studio/presets/{args.studio}.json').read_text(encoding='utf-8'))
    bg=scene.world.node_tree.nodes['Background'];bg.inputs[0].default_value=(*preset['world_color'],1)
    bg.inputs[1].default_value=preset['world_strength'];scene.view_settings.exposure=preset['exposure']
    floor=bpy.data.objects[scene.name+'__Floor'];floor.data.materials[0].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(*preset['floor_color'],1)
    f,r,u=chassis_axes();point=center_of();scale=scene['studio_scale']
    existing={o.name.split('__')[-1]:o for o in bpy.data.collections[scene.name+'__Environment'].objects if o.type=='LIGHT'}
    for key,obj in existing.items():obj.hide_render=key not in {l['name'] for l in preset['lights']}
    for light in preset['lights']:
        obj=existing.get(light['name'])
        if obj is None:raise ValueError('Added lights require running build_studio.py first')
        a,b,c=light['offset_FRU'];obj.location=point+(f*a+r*b+u*c)*scale
        obj.data.energy=light['watts']*scale**2;obj.data.size=light['size']*scale;aim(obj,point,u)
    apply_background(scene,preset)
    scene.cycles.use_denoising=not args.no_denoise
    rig=CameraRig(scene).fit(args.target,args.lens,args.view,dof=args.dof,fstop=args.fstop)
    if args.motion=='dolly':rig.dolly(args.motion_start,args.motion_end)
    if args.motion=='orbit':rig.orbit(args.motion_start,args.motion_end)
    device=configure_device(scene,args.backend)
    gpu=gpu_snapshot()
    if device['backend']!='CPU' and float(gpu.get('free_MiB',99999))<512:
        raise RuntimeError('Less than 512 MiB free GPU memory. Close other GPU workloads and retry.')
    sequence=args.sequence or args.end>args.start
    folder=ROOT/'04_output/frames'/args.job if sequence else ROOT/'04_output/stills'
    folder.mkdir(parents=True,exist_ok=True)
    report_path=ROOT/f'04_output/reports/{args.job}.json'
    # start/end may change on resume; motion time range stays part of the identity.
    config={k:v for k,v in vars(args).items() if k not in ['start','end']}
    config.update(preset=preset,blender=bpy.app.version_string,
        project_sha256=hashlib.sha256(project.read_bytes()).hexdigest(),
        script_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'02_studio/scripts/studio_core.py',ROOT/'03_director/camera_control.py']})
    identity=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    report={'job':args.job,'config':config,'identity':identity,'device':device,'gpu_before':gpu,
       'frame_measurements':[],'skipped_frames':[],'failed_attempts':[],
       'started_local':datetime.datetime.now().astimezone().isoformat(),
       'resolution':[args.width,args.height],'fps':30,'setup_seconds':time.perf_counter()-t0}
    if report_path.exists():
        previous=json.loads(report_path.read_text(encoding='utf-8'))
        if previous.get('identity')!=identity:raise RuntimeError('Job identity changed; use a new --job to keep resume safe')
        report['frame_measurements']=previous.get('frame_measurements',[])
        report['previous_runs']=previous.get('previous_runs',0)+1
    dump(report_path,report)
    for frame in range(args.start,args.end+1):
        scene.frame_set(frame)
        filepath=folder/(f'frame_{frame:04d}.png' if sequence else f'{args.job}.png')
        if valid_png(filepath,args.width,args.height):
            report['skipped_frames'].append(frame);dump(report_path,report)
            print('RESUME_SKIP',frame,flush=True);continue
        scene.render.filepath=str(filepath)
        pending=[device['backend']]+[b for b in ['OPTIX','CUDA','HIP','ONEAPI','CPU'] if b!=device['backend']]
        rendered=False
        for backend in pending:
            current=configure_device(scene,backend)
            if current['backend']!=backend:continue
            tic=time.perf_counter()
            try:
                bpy.ops.render.render(write_still=True)
                elapsed=time.perf_counter()-tic
                if not valid_png(filepath,args.width,args.height):raise RuntimeError('Output PNG failed CRC/dimension validation')
                current['status']='actual render completed'
                report['device']=current;device=current
                report['frame_measurements'].append({'frame':frame,'seconds_render_and_save':elapsed,
                    'backend':backend,'filepath':str(filepath.relative_to(ROOT)),'gpu_after':gpu_snapshot()})
                rendered=True;break
            except Exception as exc:
                report['failed_attempts'].append({'frame':frame,'backend':backend,'error':str(exc),'seconds':time.perf_counter()-tic})
                dump(report_path,report)
                print('BACKEND_FAILED',backend,repr(exc),flush=True)
        if not rendered:raise RuntimeError('All actual render backends failed; see job report')
        dump(report_path,report)
        print('FRAME_COMPLETE',args.job,frame,round(elapsed,3),backend,flush=True)
    report['invocation_seconds']=time.perf_counter()-t0;report['status']='complete'
    dump(report_path,report)
    print('JOB_COMPLETE',args.job,round(report['invocation_seconds'],3),flush=True)

if __name__=='__main__':main()
