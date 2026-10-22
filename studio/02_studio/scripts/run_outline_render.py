"""Launch the current version renderer and sample real Windows/NVIDIA resources."""
import sys,os,time,subprocess,json
from pathlib import Path
from run_render import memory,gpu,BLENDER
ROOT=Path(__file__).resolve().parents[2]

def main():
    args=sys.argv[1:]
    if '--job' not in args:raise SystemExit('--job is required')
    job=args[args.index('--job')+1]
    if not job.replace('_','').replace('-','').isalnum():raise SystemExit('Invalid job')
    cache=ROOT/'04_output/cache';cache.mkdir(exist_ok=True)
    env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
    for key,name in [('TEMP','temp'),('TMP','temp'),('CUDA_CACHE_PATH','cuda'),('OPTIX_CACHE_PATH','optix')]:
        path=cache/name;path.mkdir(exist_ok=True);env[key]=str(path)
    log=ROOT/f'04_output/logs/{job}.log';samples=[];tic=time.perf_counter()
    with log.open('a',encoding='utf-8') as f:
        command=[str(BLENDER),'-b','--factory-startup','--python-exit-code','1','--python',str(ROOT/'02_studio/scripts/render_outline_job.py'),'--',*args]
        process=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT,env=env,cwd=ROOT)
        while process.poll() is None:
            samples.append({'seconds':time.perf_counter()-tic,**memory(process.pid),**gpu()});time.sleep(.5)
    maxima={key:max(s[key] for s in samples if isinstance(s.get(key),(int,float))) for key in set().union(*(s.keys() for s in samples)) if key!='seconds' and any(isinstance(s.get(key),(int,float)) for s in samples)}
    report={'exit_code':process.returncode,'wall_seconds':time.perf_counter()-tic,'arguments':args,'samples':samples,
        'maxima':maxima,'scope':'GPU memory is device-wide, including other apps; Windows working set sampled per Blender process.'}
    (ROOT/f'04_output/reports/{job}_resources.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'job':job,'exit_code':process.returncode,'maxima':maxima}));raise SystemExit(process.returncode)

if __name__=='__main__':main()
