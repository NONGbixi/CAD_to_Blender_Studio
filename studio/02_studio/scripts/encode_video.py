"""Validate contiguous frames, optionally composite 2D titles, encode H.264 MP4.
python encode_video.py --job dark_full_motion --titles
Uses CAD_FFMPEG or the imageio_ffmpeg bundled executable; no online service.
"""
import argparse,os,json,re,sys,subprocess,time,hashlib
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'03_director/typography'))
from title_template import overlay

def ffmpeg_path():
    if os.environ.get('CAD_FFMPEG'):return os.environ['CAD_FFMPEG']
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def main():
    p=argparse.ArgumentParser();p.add_argument('--job',required=True)
    p.add_argument('--titles',action='store_true');p.add_argument('--expected-frames',type=int,default=30)
    a=p.parse_args()
    if not a.job.replace('_','').replace('-','').isalnum():raise ValueError('Invalid job')
    report=json.loads((ROOT/f'04_output/reports/{a.job}.json').read_text(encoding='utf-8'))
    folder=ROOT/f'04_output/frames/{a.job}';width,height=report['resolution']
    expected=[folder/f'frame_{i:04d}.png' for i in range(1,a.expected_frames+1)]
    existing=sorted(folder.glob('frame_*.png'))
    if existing!=expected:raise ValueError('Frame sequence has missing or unexpected frames')
    t0=time.perf_counter()
    for file in expected:
        with Image.open(file) as image:
            if image.size!=(width,height):raise ValueError('Frame resolution changed')
            image.verify()
    if a.titles:
        composed=ROOT/f'04_output/composited/{a.job}';composed.mkdir(parents=True,exist_ok=True)
        for i,file in enumerate(expected,1):
            with Image.open(file) as image:
                frame=Image.alpha_composite(image.convert('RGBA'),overlay(width,height,report['config']['studio'],i,a.expected_frames))
                frame.convert('RGB').save(composed/file.name,compress_level=3)
        folder=composed
    composition_seconds=time.perf_counter()-t0
    output=ROOT/f'04_output/videos/{a.job}{"_titles" if a.titles else "_clean"}.mp4'
    ff=ffmpeg_path()
    cmd=[ff,'-y','-hide_banner','-loglevel','error','-framerate','30','-start_number','1',
        '-i',str(folder/'frame_%04d.png'),'-frames:v',str(a.expected_frames),
        '-vf','scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p',
        '-c:v','libx264','-preset','slow','-crf','18','-pix_fmt','yuv420p',
        '-color_range','tv','-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709',
        '-movflags','+faststart','-an',str(output)]
    tic=time.perf_counter();subprocess.run(cmd,check=True);encode_seconds=time.perf_counter()-tic
    metadata=subprocess.run([ff,'-hide_banner','-i',str(output)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    decode=subprocess.run([ff,'-v','error','-i',str(output),'-progress','pipe:1','-nostats','-f','null','-'],capture_output=True,text=True,check=True)
    frames=[int(v) for v in re.findall(r'^frame=(\d+)',decode.stdout,re.M)]
    assert frames and frames[-1]==a.expected_frames,'Encoded frame count mismatch'
    assert 'h264' in metadata.stderr and f'{width}x{height}' in metadata.stderr and '30 fps' in metadata.stderr
    data={'job':a.job,'output':str(output.relative_to(ROOT)),'resolution':[width,height],'fps':30,
          'frames':frames[-1],'duration_seconds':a.expected_frames/30,'codec':'H.264 / libx264',
          'pixel_format':'yuv420p','crf':18,'titles_2d':a.titles,'frame_validation_and_composition_seconds':composition_seconds,
          'encode_seconds':encode_seconds,'full_decode_verified':True,'ffmpeg':ff,
          'ffmpeg_metadata':metadata.stderr,'command':cmd,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
    name=a.job+('_titles' if a.titles else '_clean')
    (ROOT/f'04_output/reports/{name}_encode.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ENCODE_VERIFIED',name,frames[-1],width,height)

if __name__=='__main__':main()
