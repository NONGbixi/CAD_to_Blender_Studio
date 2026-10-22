"""System Python launcher and Windows/NVIDIA resource sampler.
python run_render.py --studio light --job light_64 --samples 64
Pass-through arguments are documented by render_job.py --help inside Blender.
"""
import ctypes,ctypes.wintypes as wt,datetime,json,os,shutil,subprocess,sys,time,threading
from pathlib import Path
ROOT=Path(os.environ.get('CAD_ROOT',Path(__file__).resolve().parents[2])).resolve()
# Point CAD_BLENDER at blender.exe, or leave unset to use the one on PATH.
BLENDER=Path(os.environ.get('CAD_BLENDER') or shutil.which('blender') or 'blender')

class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_=[('cb',wt.DWORD),('PageFaultCount',wt.DWORD)]+[(x,ctypes.c_size_t) for x in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
class MEMORYSTATUSEX(ctypes.Structure):
    _fields_=[('dwLength',wt.DWORD),('dwMemoryLoad',wt.DWORD)]+[(x,ctypes.c_ulonglong) for x in ['ullTotalPhys','ullAvailPhys','ullTotalPageFile','ullAvailPageFile','ullTotalVirtual','ullAvailVirtual','ullAvailExtendedVirtual']]

def memory(pid):
    if os.name!='nt':return {'unavailable':'Windows memory sampler'}
    k=ctypes.WinDLL('kernel32',use_last_error=True);p=ctypes.WinDLL('psapi',use_last_error=True)
    k.OpenProcess.restype=wt.HANDLE;k.OpenProcess.argtypes=[wt.DWORD,wt.BOOL,wt.DWORD]
    k.CloseHandle.argtypes=[wt.HANDLE]
    p.GetProcessMemoryInfo.argtypes=[wt.HANDLE,ctypes.POINTER(PROCESS_MEMORY_COUNTERS),wt.DWORD]
    h=k.OpenProcess(0x410,False,pid);m=PROCESS_MEMORY_COUNTERS();m.cb=ctypes.sizeof(m)
    result={}
    if h:
        if p.GetProcessMemoryInfo(h,ctypes.byref(m),m.cb):
            result.update(process_working_set_MiB=m.WorkingSetSize/1048576,process_peak_working_set_MiB=m.PeakWorkingSetSize/1048576,
                          process_commit_MiB=m.PagefileUsage/1048576)
        k.CloseHandle(h)
    g=MEMORYSTATUSEX();g.dwLength=ctypes.sizeof(g)
    if k.GlobalMemoryStatusEx(ctypes.byref(g)):
        result.update(system_total_MiB=g.ullTotalPhys/1048576,system_used_MiB=(g.ullTotalPhys-g.ullAvailPhys)/1048576)
    return result

def gpu():
    try:
        r=subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
        vals=r.stdout.strip().split(',')
        return {k:float(v.strip()) for k,v in zip(['gpu_total_used_MiB','gpu_free_MiB','gpu_utilization_percent','gpu_temperature_C','gpu_power_W'],vals)}
    except Exception as e:return {'gpu_unavailable':str(e)}

def main():
    args=sys.argv[1:]
    if '--job' not in args:raise SystemExit('A unique --job is required')
    job=args[args.index('--job')+1]
    if not job.replace('_','').replace('-','').isalnum():raise SystemExit('Invalid job name')
    cache=ROOT/'04_output/cache';cache.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy()
    for key,sub in [('TEMP','temp'),('TMP','temp'),('CUDA_CACHE_PATH','cuda'),('OPTIX_CACHE_PATH','optix'),('CYCLES_KERNEL_CACHE_DIR','cycles')]:
        path=cache/sub;path.mkdir(exist_ok=True);env[key]=str(path)
    env['PYTHONIOENCODING']='utf-8'
    log=ROOT/f'04_output/logs/{job}.log';metric=ROOT/f'04_output/reports/{job}_resources.json'
    baseline=gpu();start=time.perf_counter();samples=[]
    command=[str(BLENDER),'-b','--factory-startup','--python-exit-code','1','--python',str(ROOT/'02_studio/scripts/render_job.py'),'--',*args]
    with log.open('a',encoding='utf-8') as f:
        f.write('\nRUN '+datetime.datetime.now().astimezone().isoformat()+'\n');f.flush()
        proc=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT,env=env,cwd=ROOT)
        while proc.poll() is None:
            sample={'seconds':time.perf_counter()-start,**memory(proc.pid),**gpu()};samples.append(sample)
            time.sleep(.5)
    result={'pid':proc.pid,'exit_code':proc.returncode,'wall_seconds':time.perf_counter()-start,
            'recorded_local':datetime.datetime.now().astimezone().isoformat(),'arguments':args,
            'baseline_gpu':baseline,'samples':samples,'scope':'GPU numbers are device-wide including other applications. WDDM per-process dedicated VRAM may be unavailable.',
            'maxima':{key:max(s[key] for s in samples if isinstance(s.get(key),(int,float))) for key in samples[0] if key!='seconds' and any(isinstance(s.get(key),(int,float)) for s in samples)} if samples else {}}
    if metric.exists():
        stamp=datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')
        history=ROOT/f'04_output/reports/{job}_resources_before_{stamp}.json'
        history.write_text(metric.read_text(encoding='utf-8'),encoding='utf-8')
    metric.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'job':job,'exit_code':proc.returncode,'wall_seconds':result['wall_seconds'],'log':str(log),'maxima':result['maxima']},ensure_ascii=False),flush=True)
    raise SystemExit(proc.returncode)

if __name__=='__main__':main()
