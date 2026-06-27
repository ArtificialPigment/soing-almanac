"""
Detect the cream recipe card, deskew via perspective (QUAD) warp, save clean
high-res portrait. Pure Pillow.

Key idea: the recipe card is a large SOLID cream block; the fanned card-backs
are cream-with-drawings (textured), so they survive as only thin/holey cream.
Eroding the cream mask deletes those thin bridges and isolates the real card.
"""
import os, sys, glob, math
from PIL import Image, ImageFilter
from collections import deque

SRC = r'D:/CLAUDE_ONLY/cocktail'
OUT = r'D:/CLAUDE_ONLY/cocktail/work/cards'
DBG = r'D:/CLAUDE_ONLY/cocktail/work/debug'
os.makedirs(OUT, exist_ok=True); os.makedirs(DBG, exist_ok=True)

NAMES = {
    '20260626-223603': 'caipirinha', '20260626-223615': 'basil-smash',
    '20260626-223618': 'aviation', '20260626-223622': 'lychee-gimlet',
    '20260626-223632': 'spicy-lemon-drop', '20260626-223636': 'negroni',
    '20260626-223639': 'gin-fizz', '20260626-223642': 'sidecar',
    '20260626-223645': 'americano', '20260626-223648': 'blue-hawaii',
    '20260626-223651': 'pina-colada', '20260626-223654': 'bloody-mary',
    '20260626-223657': 'tequila-sunrise', '20260626-223700': 'moscow-mule',
    '20260626-223704': 'whiskey-sour', '20260626-223709': 'manhattan',
    '20260626-223712': 'old-fashioned', '20260626-223715': 'mojito',
    '20260626-223719': 'strawberry-daiquiri', '20260626-223728': 'margarita',
}

def cream_mask(small):
    """Return a bytearray mask (1=warm kraft card) and a PIL 'L' image.

    The recipe card is warm kraft: high luma, low blue (R-B large). Wood is
    dark (low luma); the fanned card-backs are neutral whitish (R-B small).
    """
    px = small.load(); w, h = small.size
    raw = bytearray(w * h)
    limg = Image.new('L', (w, h)); lpx = limg.load()
    for y in range(h):
        base = y * w
        for x in range(w):
            r, g, b = px[x, y][:3]
            luma = (77*r + 150*g + 28*b) >> 8     # ~0.30/0.59/0.11
            warm = r - b
            if luma > 150 and r > 182 and 40 < warm < 118 and g >= b - 4:
                raw[base + x] = 1; lpx[x, y] = 255
    return raw, limg, w, h

def components(mask, w, h, topn=8):
    seen = bytearray(w * h); comps = []
    for s in range(w * h):
        if mask[s] and not seen[s]:
            q = deque([s]); seen[s] = 1; n = 0
            minx = miny = 10**9; maxx = maxy = -1
            while q:
                i = q.popleft(); n += 1
                yy, xx = divmod(i, w)
                if xx < minx: minx = xx
                if xx > maxx: maxx = xx
                if yy < miny: miny = yy
                if yy > maxy: maxy = yy
                if xx > 0 and mask[i-1] and not seen[i-1]: seen[i-1]=1; q.append(i-1)
                if xx < w-1 and mask[i+1] and not seen[i+1]: seen[i+1]=1; q.append(i+1)
                if yy > 0 and mask[i-w] and not seen[i-w]: seen[i-w]=1; q.append(i-w)
                if yy < h-1 and mask[i+w] and not seen[i+w]: seen[i+w]=1; q.append(i+w)
            comps.append((n, (minx, miny, maxx, maxy)))
    comps.sort(key=lambda c: c[0], reverse=True)
    return comps[:topn]

def pick(comps, w, h):
    best = None; bs = -1
    for area, bb in comps:
        minx, miny, maxx, maxy = bb
        bw = maxx-minx+1; bh = maxy-miny+1
        if bw < w*0.16 or bh < h*0.16: continue
        ar = bh/bw; fill = area/(bw*bh)
        if fill < 0.32: continue                  # card body (has art/text holes)
        ar_score = max(0.0, 1 - abs(ar-1.40)/0.9)
        score = area * (0.3+0.7*fill) * (0.25+0.75*ar_score)
        if score > bs: bs = score; best = (area, bb)
    return best

def refine_corners(rawmask, w, h, bb, pad):
    """Precise rotated-rect corners from the *un-eroded* mask within padded bb."""
    minx, miny, maxx, maxy = bb
    minx = max(0, minx-pad); miny = max(0, miny-pad)
    maxx = min(w-1, maxx+pad); maxy = min(h-1, maxy+pad)
    best = {'tl':(None,1e18),'br':(None,-1e18),'tr':(None,-1e18),'bl':(None,1e18)}
    tl=br=tr=bl=None; vtl=1e18; vbr=-1e18; vtr=-1e18; vbl=1e18
    for y in range(miny, maxy+1):
        rowb = y*w
        for x in range(minx, maxx+1):
            if rawmask[rowb+x]:
                s = x+y; d = x-y
                if s < vtl: vtl=s; tl=(x,y)
                if s > vbr: vbr=s; br=(x,y)
                if d > vtr: vtr=d; tr=(x,y)
                if d < vbl: vbl=d; bl=(x,y)
    return tl, tr, br, bl

def process(path, dump=False):
    base = os.path.splitext(os.path.basename(path))[0]
    name = NAMES.get(base, base)
    im = Image.open(path).convert('RGB'); W, H = im.size
    AW = 1000; scale = W/AW
    small = im.resize((AW, int(H/scale)), Image.BILINEAR)
    raw, limg, w, h = cream_mask(small)
    eroded = limg.filter(ImageFilter.MinFilter(3))    # light erode ~1px
    epx = eroded.load()
    emask = bytearray(w*h)
    for y in range(h):
        for x in range(w):
            if epx[x, y] > 127: emask[y*w+x] = 1
    comps = components(emask, w, h)
    card = pick(comps, w, h)
    if not card:
        print(f'{name}: NO CARD'); return None
    area, bb = card
    tl, tr, br, bl = refine_corners(raw, w, h, bb, pad=8)
    fc = [(p[0]*scale, p[1]*scale) for p in (tl, tr, br, bl)]
    def dist(a,b): return math.hypot(a[0]-b[0], a[1]-b[1])
    wpx = (dist(fc[0],fc[1])+dist(fc[3],fc[2]))/2
    hpx = (dist(fc[0],fc[3])+dist(fc[1],fc[2]))/2
    outw = 1240; outh = int(round(outw*(hpx/wpx)))
    (tlx,tly),(trx,try_),(brx,bry),(blx,bly) = fc
    quad = (tlx,tly, blx,bly, brx,bry, trx,try_)   # UL, LL, LR, UR
    warped = im.transform((outw, outh), Image.QUAD, quad, Image.BICUBIC)
    warped.save(os.path.join(OUT, name+'.jpg'), quality=94)
    if dump:
        dbg = small.copy(); dp = dbg.load()
        for (x,y) in (tl,tr,br,bl):
            for dx in range(-6,7):
                for dy in range(-6,7):
                    xx,yy=x+dx,y+dy
                    if 0<=xx<w and 0<=yy<h: dp[xx,yy]=(255,0,0)
        dbg.save(os.path.join(DBG, name+'_dbg.jpg'), quality=80)
    print(f'{name}: bb={bb} ar={hpx/wpx:.3f} -> {outw}x{outh}')
    return name

if __name__ == '__main__':
    args = sys.argv[1:]
    dump = '--dump' in args
    only = [a for a in args if not a.startswith('--')]
    for f in sorted(glob.glob(os.path.join(SRC, '*.jpg'))):
        base = os.path.splitext(os.path.basename(f))[0]
        if only and NAMES.get(base, base) not in only and base not in only: continue
        try: process(f, dump=dump)
        except Exception as e:
            import traceback; print(f'{base}: ERROR {e}'); traceback.print_exc()
