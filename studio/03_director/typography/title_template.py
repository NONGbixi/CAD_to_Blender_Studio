"""Deterministic 2D RGBA titles, CJK cmap audit, fade and vertical easing.
Runs with system Python + Pillow; independent of the 3D camera and lights.
"""
import json,struct,hashlib,argparse
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageColor
ROOT=Path(__file__).resolve().parents[2]
CONFIG=json.loads((Path(__file__).with_name('styles.json')).read_text(encoding='utf-8'))
FONT=ROOT/CONFIG['font']

class FontMap:
    """Read cmap 12/4 and name records directly; no fontTools dependency."""
    def __init__(self,path):
        self.data=Path(path).read_bytes();d=self.data
        count=struct.unpack_from('>H',d,4)[0]
        self.tables={}
        for i in range(count):
            tag,crc,off,length=struct.unpack_from('>4sIII',d,12+16*i)
            self.tables[tag.decode()]=(off,length)
        cmap=self.tables['cmap'][0];n=struct.unpack_from('>H',d,cmap+2)[0]
        maps=[]
        for i in range(n):
            platform,encoding,off=struct.unpack_from('>HHI',d,cmap+4+8*i)
            start=cmap+off;fmt=struct.unpack_from('>H',d,start)[0]
            if platform in (0,3) and fmt in (4,12):maps.append((fmt,start))
        self.maps=sorted(set(maps),reverse=True)
    def glyph(self,cp):
        d=self.data
        for fmt,s in self.maps:
            if fmt==12:
                groups=struct.unpack_from('>I',d,s+12)[0]
                lo=0;hi=groups-1
                while lo<=hi:
                    mid=(lo+hi)//2;a,b,g=struct.unpack_from('>III',d,s+16+12*mid)
                    if cp<a:hi=mid-1
                    elif cp>b:lo=mid+1
                    else:return g+cp-a
            elif cp<=0xffff:
                n=struct.unpack_from('>H',d,s+6)[0]//2
                for i in range(n):
                    end=struct.unpack_from('>H',d,s+14+2*i)[0]
                    start=struct.unpack_from('>H',d,s+16+2*n+2*i)[0]
                    if not start<=cp<=end:continue
                    delta=struct.unpack_from('>h',d,s+16+4*n+2*i)[0]
                    addr=s+16+6*n+2*i;roff=struct.unpack_from('>H',d,addr)[0]
                    if not roff:return (cp+delta)&0xffff
                    gid=struct.unpack_from('>H',d,addr+roff+2*(cp-start))[0]
                    return ((gid+delta)&0xffff) if gid else 0
        return 0
    def names(self):
        d=self.data;s=self.tables['name'][0];fmt,n,string=struct.unpack_from('>HHH',d,s)
        result={}
        for i in range(n):
            plat,enc,lang,key,length,off=struct.unpack_from('>HHHHHH',d,s+6+12*i)
            if key not in (0,1,2,5,13,14):continue
            raw=d[s+string+off:s+string+off+length]
            val=raw.decode('utf-16-be' if plat in (0,3) else 'mac_roman',errors='replace')
            result.setdefault(str(key),[])
            if val not in result[str(key)]:result[str(key)].append(val)
        return result

CMAP=FontMap(FONT)
def validate_text(text):
    missing=[ch for ch in set(text) if ch not in '\n\r\t' and not CMAP.glyph(ord(ch))]
    if missing:raise ValueError('Font lacks characters: '+''.join(missing))

def smoothstep(t):
    t=max(0,min(1,t));return t*t*(3-2*t)

def tracked(draw,xy,text,font,tracking,fill,align='left'):
    length=sum(font.getlength(ch) for ch in text)+max(0,len(text)-1)*tracking
    x,y=xy
    if align=='center':x-=length/2
    if align=='right':x-=length
    bounds=font.getbbox(text)
    for ch in text:
        draw.text((x,y-bounds[1]),ch,font=font,fill=fill)
        x+=font.getlength(ch)+tracking
    return length

def overlay(width,height,studio='light',frame=15,total=30,template='studio_validation',animate=True):
    scale=width/1920;ss=2
    out=Image.new('RGBA',(width*ss,height*ss),(0,0,0,0));draw=ImageDraw.Draw(out)
    motion=CONFIG['motion']
    if animate:
        alpha=min(smoothstep((frame-1)/max(1,motion['fade_in_frames']-1)),
                  smoothstep((total-frame)/max(1,motion['fade_out_frames']-1)))
        dy=motion['vertical_pixels']*scale*(1-smoothstep((frame-1)/max(1,motion['fade_in_frames']-1)))
    else:alpha=1;dy=0
    for block in CONFIG['templates'][template]:
        text=block['text'];validate_text(text)
        style=CONFIG['styles'][block['style']]
        font=ImageFont.truetype(str(FONT),round(style['size']*scale*ss))
        rgb=ImageColor.getrgb(CONFIG['colors'][studio][block['color']])
        tracked(draw,(block['x']*width*ss,(block['y']*height+dy)*ss),text,font,
                style['tracking']*scale*ss,(*rgb,round(255*alpha)),block['align'])
    return out.resize((width,height),Image.Resampling.LANCZOS)

def create_samples():
    folder=ROOT/'04_output/typography';folder.mkdir(parents=True,exist_ok=True)
    text=''.join(b['text'] for blocks in CONFIG['templates'].values() for b in blocks)
    validate_text(text)
    for studio in ['light','dark']:
        for template in CONFIG['templates']:
            layer=overlay(1920,1080,studio,template=template,animate=False)
            layer.save(folder/f'{studio}_{template}_rgba.png')
            bg=Image.new('RGBA',layer.size,'#F0F0F0' if studio=='light' else '#171717')
            Image.alpha_composite(bg,layer).convert('RGB').save(folder/f'{studio}_{template}_sample.png')
        base=Image.open(ROOT/f'04_output/stills/{studio}_final_128.png').convert('RGBA')
        Image.alpha_composite(base,overlay(*base.size,studio,animate=False)).convert('RGB').save(ROOT/f'04_output/stills/{studio}_with_titles.png')
    audit={'font':str(FONT.relative_to(ROOT)),'sha256':hashlib.sha256(FONT.read_bytes()).hexdigest(),
           'font_names':CMAP.names(),'checked_characters':sorted(set(text)),
           'missing_characters':[],'glyph_ids':{ch:CMAP.glyph(ord(ch)) for ch in sorted(set(text))},
           'license_source':'https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE',
           'font_origin':'Existing local C:/Windows/Fonts/NotoSansSC-Medium.otf; copied unchanged'}
    (ROOT/'04_output/reports/font_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print('TYPOGRAPHY_SAMPLES_COMPLETE')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--samples',action='store_true');a=p.parse_args()
    if a.samples:create_samples()
