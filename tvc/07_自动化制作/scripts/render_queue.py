"""Two resumable GPU workers. Fasteners use one worker to serialize mask cache."""
import sys,os,shutil,json,subprocess,argparse,hashlib,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];TASK=ROOT.parent
BLENDER=Path(os.environ.get('CAD_BLENDER') or shutil.which('blender') or 'blender')
def read(p):return json.loads(p.read_text(encoding='utf-8'))
ap=argparse.ArgumentParser();ap.add_argument('--worker',choices=['a','b'],required=True);args=ap.parse_args()
manifest=read(ROOT/'remaining_shots.json');progress=ROOT/f'reports/queue_{args.worker}.json';rows=[]
while True:
 try:
  if read(ROOT/'reports/visual_gate.json')['status']=='passed':break
 except (FileNotFoundError,json.JSONDecodeError):pass
 time.sleep(2)
for item in manifest:
 while item['id'] not in read(ROOT/'reports/visual_gate.json').get('passed_shots',[]):time.sleep(2)
 shot=Path(item['directory']);a,b=item['frames'];mid=(a+b)//2
 if item['id']=='S10':
  if args.worker=='b':continue
  start,end=a,b
 else:start,end=(a,mid) if args.worker=='a' else (mid+1,b)
 log=shot/f'reports/render_queue_{args.worker}.log'
 with log.open('a',encoding='utf-8') as stream:
  result=subprocess.run([str(BLENDER),'-b','--python-exit-code','1','--python',str(shot/'scripts/render.py'),'--','--mode','sequence','--reuse',
   '--start',str(start),'--end',str(end),'--worker',args.worker],stdout=stream,stderr=subprocess.STDOUT)
 assert result.returncode==0,(item['id'],args.worker,log)
 report=read(shot/f'reports/render_sequence_{args.worker}.json');assert report['status']=='complete'
 rows.append({'id':item['id'],'frames':[start,end],'status':'complete'});progress.write_text(json.dumps({'status':'running','shots':rows},ensure_ascii=False,indent=2),encoding='utf-8')
 print('QUEUE_SHOT_DONE',args.worker,item['id'],flush=True)
progress.write_text(json.dumps({'status':'complete','shots':rows},ensure_ascii=False,indent=2),encoding='utf-8');print('QUEUE_COMPLETE',args.worker,flush=True)
