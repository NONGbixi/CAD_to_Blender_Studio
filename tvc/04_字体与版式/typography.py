"""One audited font profile for every shot; no fallback fonts.

Environment:
  CAD_STUDIO_ROOT          path to the studio project (default: <repo>/studio)
  CAD_TYPOGRAPHY_PROFILE   profile JSON with per-role font file + sha256
"""
import os,sys,json,hashlib
from pathlib import Path
from PIL import ImageFont
TVC=Path(__file__).resolve().parents[1]
STUDIO=Path(os.environ.get('CAD_STUDIO_ROOT',TVC.parent/'studio')).resolve()
sys.path.insert(0,str(STUDIO/'03_director/typography'))
from title_template import FontMap,tracked,smoothstep
PROFILE=json.loads((Path(os.environ.get('CAD_TYPOGRAPHY_PROFILE',TVC/'04_字体与版式/typography_profile.json'))).read_text(encoding='utf-8'))
def path(role):return TVC/PROFILE['roles'][role]['file']
def audit(role,text):
    p=path(role);record=PROFILE['roles'][role];digest=hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest==record['sha256'],'Font file differs from the validated profile'
    cmap=FontMap(p);missing=[c for c in set(text) if not c.isspace() and not cmap.glyph(ord(c))]
    assert not missing,(role,missing)
    return {'role':role,'family':record['family'],'style':record['style'],'weight':record['weight'],
      'path':str(p),'sha256':digest,'text':text,'missing':missing}
def font(role,size):return ImageFont.truetype(str(path(role)),round(size))
