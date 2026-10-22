"""Fill enclosed holes in an opaque context alpha mask, keeping external contour."""
import sys
from PIL import Image,ImageDraw
source,target=sys.argv[1:3]
alpha=Image.open(source).convert('RGBA').getchannel('A').point(lambda x:255 if x>=128 else 0)
w,h=alpha.size
pad=Image.new('L',(w+2,h+2),0);pad.paste(alpha,(1,1))
ImageDraw.floodfill(pad,(0,0),128,thresh=0)
filled=pad.point(lambda x:0 if x==128 else 255).crop((1,1,w+1,h+1))
filled.save(target)
