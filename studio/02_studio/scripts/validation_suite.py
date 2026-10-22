"""Small task-two validation suite only; no advertising timeline."""
import subprocess,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
detail=json.loads((ROOT/'03_director/detail_targets.json').read_text(encoding='utf-8'))
jobs=[
 ['--studio','light','--job','light_final_64','--samples','64'],
 ['--studio','light','--job','light_final_128','--samples','128'],
 ['--studio','dark','--job','dark_final_64','--samples','64'],
 ['--studio','dark','--job','dark_final_128','--samples','128'],
 ['--studio','light','--job','light_raw_64','--samples','64','--no-denoise'],
 ['--studio','dark','--job','dark_raw_64','--samples','64','--no-denoise'],
 ['--studio','dark','--job','dark_wheel_85','--samples','128','--target',detail['wheel_front'],'--view','macro','--lens','85'],
 ['--studio','light','--job','light_belt_85','--samples','128','--target','Timing Belt','--lens','85'],
 ['--studio','dark','--job','dark_gripper_dof','--samples','128','--target','Gripper','--lens','85','--dof','--fstop','8'],
 ['--studio','light','--job','light_top_35','--samples','64','--view','top','--lens','35'],
 ['--studio','dark','--job','dark_low_35','--samples','64','--view','low','--lens','35'],
 ['--studio','light','--job','light_preview_motion','--samples','32','--width','960','--height','540','--end','30','--motion','dolly'],
 ['--studio','dark','--job','dark_full_motion','--samples','128','--end','30','--motion','orbit'],
 ['--studio','dark','--job','dark_hold_check','--samples','64','--end','6','--sequence'],
]
for args in jobs:
    print('START',args[args.index('--job')+1],flush=True)
    subprocess.run([sys.executable,str(ROOT/'02_studio/scripts/run_render.py'),*args],check=True)
print('VALIDATION_SUITE_COMPLETE',flush=True)
