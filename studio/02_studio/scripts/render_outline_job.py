"""Current version renderer: per-frame evaluated CAD, denoise then approved outlines."""
import argparse,sys,json,hashlib,time,os,shutil,subprocess
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'02_studio/scripts'));sys.path.insert(0,str(ROOT/'03_director'))
sys.path.insert(0,str(ROOT/'03_director/outline_approved'))
from studio_core import fingerprint,dump,configure_device,render_settings,setup_paths,gpu_snapshot
from render_job import valid_png
from camera_control import CameraRig
from outline_pipeline import OutlinePipeline
from render_static_reference import rear_camera
import module_focus as mf

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job',required=True);p.add_argument('--studio',choices=['light','dark'],default='light')
    p.add_argument('--module',default='whole');p.add_argument('--view',choices=['original','rear'],default='original')
    p.add_argument('--shot',choices=['hero','rear','low','top','macro'],default='hero')
    p.add_argument('--target',default=None);p.add_argument('--samples',type=int,default=256)
    p.add_argument('--width',type=int,default=1920);p.add_argument('--height',type=int,default=1080)
    p.add_argument('--start',type=int,default=1);p.add_argument('--end',type=int,default=1)
    p.add_argument('--motion',choices=['none','dolly','orbit'],default='none')
    p.add_argument('--motion-start',type=int,default=1);p.add_argument('--motion-end',type=int,default=30)
    p.add_argument('--motion-degrees',type=float,default=6)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if not a.job.replace('_','').replace('-','').isalnum():raise ValueError('Invalid job')
    if min(a.width,a.height,a.samples,a.start)<1 or a.end<a.start:raise ValueError('Invalid render range')
    setup_paths();current=json.loads((ROOT/'project_current.json').read_text(encoding='utf-8'))
    profile=ROOT/current['outline_profile'];profile_data=json.loads(profile.read_text(encoding='utf-8'))
    project=ROOT/current['studio_emphasis'];assert sha(project)==current['studio_emphasis_sha256']
    assert sha(ROOT/current['source_model'])==current['source_model_sha256']
    bpy.ops.wm.open_mainfile(filepath=str(project))
    bpy.context.window.scene=bpy.data.scenes['Studio_Light'];bpy.context.view_layer.update()
    scene=bpy.data.scenes[('Studio_' if a.module=='whole' else 'Emphasis_')+a.studio.title()]
    bpy.context.window.scene=scene;bpy.context.view_layer.update()
    expected=json.loads((ROOT/current['model_fingerprint']).read_text(encoding='utf-8'))
    assert fingerprint()==expected,'Versioned source model fingerprint mismatch'
    transparent=scene.render.film_transparent
    render_settings(scene,a.samples,a.width,a.height,preview=a.height<1080)
    scene.render.film_transparent=transparent
    scene.cycles.transparent_max_bounces=128;scene.cycles.use_denoising=True
    scene.cycles.adaptive_threshold=.002 if a.samples>=512 else .005
    scene.cycles.adaptive_min_samples=min(a.samples,128 if a.height>=1080 else 32)
    scene.render.fps=30
    mf.configure_mapping(ROOT/current['module_mapping'])
    pipeline=None if a.module=='whole' else OutlinePipeline(scene,profile)
    if a.module!='whole':mf.module(a.module)
    if a.target:
        if a.target=='module':target=scene.name+'__'+mf.module(a.module)['collection']
        else:
            target=next((o for o in bpy.data.collections['MODEL_原始装配'].all_objects if o.type=='EMPTY' and o.get('source_name')==a.target),None)
            if target is None:raise ValueError('Target source component not found: '+a.target)
        CameraRig(scene).fit(target,lens=85,view=a.shot,margin=1.75,shift_x=0,dof=False)
    if a.view=='rear':
        if a.motion!='none':raise ValueError('Motion tests currently use the original rig; rear is a static reference')
        rear,preset=rear_camera(scene);scene.camera=rear
        reference_aspect=preset['resolution'][0]/preset['resolution'][1]
        if a.width/a.height>reference_aspect:
            rear.data.ortho_scale*=a.width/a.height/reference_aspect
    if a.motion!='none':
        if a.motion_end<=a.motion_start:raise ValueError('Invalid motion range')
        rig=CameraRig(scene)
        if a.motion=='orbit':rig.orbit(a.motion_start,a.motion_end,a.motion_degrees)
        else:rig.dolly(a.motion_start,a.motion_end,.96)
    device=configure_device(scene)
    config={k:v for k,v in vars(a).items() if k not in ['start','end']}
    config.update(version=current['version'],project_sha256=sha(project),source_sha256=current['source_model_sha256'],
        mapping_sha256=sha(ROOT/current['module_mapping']),
        outline={k:profile_data[k] for k in ['style','edge_selection','fasteners_focus']},
        module_context_override=profile_data.get('module_context_overrides',{}).get(a.module,{}),
        code={str(f.relative_to(ROOT)):sha(f) for f in [Path(__file__),ROOT/'03_director/outline_approved/outline_pipeline.py',
            ROOT/'03_director/outline_approved/compose_edges.py',ROOT/'03_director/module_focus.py',ROOT/'03_director/camera_control.py']})
    identity=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    report_path=ROOT/f'04_output/reports/{a.job}.json'
    folder=ROOT/'04_output/frames'/a.job;folder.mkdir(parents=True,exist_ok=True)
    cache=ROOT/'04_output/cache/outline_jobs'/a.job;cache.mkdir(parents=True,exist_ok=True)
    report={'job':a.job,'identity':identity,'config':config,'resolution':[a.width,a.height],'fps':30,
        'device':device,'frame_measurements':[],'skipped_frames':[],'failed_attempts':[],
        'source_model_fingerprint_match':True,'pipeline':'surface denoise, then one screen outline pass, then optional typography'}
    if report_path.exists():
        previous=json.loads(report_path.read_text(encoding='utf-8'))
        if previous['identity']!=identity:raise RuntimeError('Job inputs changed; select a new job name')
        report['frame_measurements']=previous['frame_measurements']
    dump(report_path,report)
    python=os.environ.get('CAD_PYTHON') or shutil.which('python')
    for frame in range(a.start,a.end+1):
        scene.frame_set(frame);bpy.context.view_layer.update()
        out=folder/f'frame_{frame:04d}.png'
        existing=next((v for v in report['frame_measurements'] if v['frame']==frame),None)
        if valid_png(out,a.width,a.height) and existing and sha(out)==existing['sha256']:
            report['skipped_frames'].append(frame);print('OUTLINE_RESUME_SKIP',frame,flush=True);continue
        tic=time.perf_counter();edges=None;edge_path=cache/f'edges_{frame:04d}.json'
        if pipeline:
            edges=pipeline.prepare_frame(a.module);dump(edge_path,edges)
        prepare_seconds=time.perf_counter()-tic
        surfaces=cache/f'surface_{frame:04d}.png' if pipeline else out
        scene.render.filepath=str(surfaces);render_tic=time.perf_counter()
        for backend in dict.fromkeys([device['backend'],'OPTIX','CUDA','CPU']):
            selected=configure_device(scene,backend)
            if selected['backend']!=backend:continue
            try:
                bpy.ops.render.render(write_still=True)
                if not valid_png(surfaces,a.width,a.height):raise RuntimeError('Surface PNG CRC/dimension validation failed')
                device=selected;device['status']='actual Cycles render completed';report['device']=device
                break
            except Exception as error:
                report['failed_attempts'].append({'frame':frame,'backend':backend,'error':str(error)})
                if backend=='CPU':raise
        render_seconds=time.perf_counter()-render_tic;post_tic=time.perf_counter()
        if pipeline:
            if not python:raise RuntimeError('System Python with Pillow is required for screen outlines')
            subprocess.run([python,str(ROOT/'03_director/outline_approved/compose_edges.py'),
                '--faces',str(surfaces),'--edges',str(edge_path),'--output',str(out),'--profile',str(profile)],check=True)
        if not valid_png(out,a.width,a.height):raise RuntimeError('Final PNG failed CRC/dimension validation')
        item={'frame':frame,'prepare_seconds':prepare_seconds,'seconds_render_and_save':render_seconds,
            'compose_seconds':time.perf_counter()-post_tic,'total_frame_seconds':time.perf_counter()-tic,
            'filepath':str(out.relative_to(ROOT)),'sha256':sha(out),'gpu_after':gpu_snapshot()}
        if edges:item['outline_stats']=edges['stats']
        report['frame_measurements']=[v for v in report['frame_measurements'] if v['frame']!=frame]+[item]
        dump(report_path,report);print('OUTLINE_FRAME_DONE',a.job,frame,round(item['total_frame_seconds'],3),flush=True)
    assert fingerprint()==expected,'Rendering modified source CAD'
    assert sha(project)==current['studio_emphasis_sha256'],'Saved project changed during rendering'
    report['status']='complete';report['source_model_unchanged_after_render']=True
    dump(report_path,report);print('OUTLINE_JOB_COMPLETE',a.job,flush=True)

if __name__=='__main__':main()
