"""
From each deskewed card produce:
  1. a web-optimized full card  -> site/assets/cards/<name>.jpg  (820w)
  2. a tight hand-drawn illustration crop -> site/assets/illustrations/<name>.png
A contact sheet is written for visual QA.
"""
import os, glob
from PIL import Image

CARDS = r'D:/CLAUDE_ONLY/cocktail/work/cards'
WEBC  = r'D:/CLAUDE_ONLY/cocktail/site/assets/cards'
ILLU  = r'D:/CLAUDE_ONLY/cocktail/site/assets/illustrations'
for d in (WEBC, ILLU): os.makedirs(d, exist_ok=True)

def content_mask(im):
    """1 where there is drawn content (ink/wash) over the kraft background."""
    px = im.load(); w, h = im.size
    m = bytearray(w*h)
    for y in range(h):
        b = y*w
        for x in range(w):
            r, g, bl = px[x, y][:3]
            luma = (77*r + 150*g + 28*bl) >> 8
            mx = max(r,g,bl); mn = min(r,g,bl)
            sat = mx - mn
            # kraft bg is warm + bright + low-contrast. Real content is either
            # a dark outline (low luma) or a non-kraft colour wash.
            is_kraft = luma > 168 and 36 < (r-bl) < 122 and g >= bl-6
            if (luma < 150) or (sat > 30 and not is_kraft and luma < 230):
                m[b+x] = 1
    return m, w, h

def illustration_box(im):
    """Bound the drink art: the LEFT-most content block, cut at the kraft gap
    before the recipe text. Card's own border is skipped via the x-start inset."""
    m, w, h = content_mask(im)
    x0, x1 = int(w*0.05), int(w*0.50)       # drink zone; >0.05 skips left border
    y0, y1 = int(h*0.15), int(h*0.90)       # skip title band + footer
    colcnt = [0]*w
    for y in range(y0, y1):
        b = y*w
        for x in range(x0, x1):
            if m[b+x]: colcnt[x] += 1
    thr = max(6, int((y1-y0)*0.05))
    GAP = int(w*0.05)                        # kraft gap that separates art / text
    cx0 = x0
    while cx0 < x1 and colcnt[cx0] < thr: cx0 += 1
    last, gap, x = cx0, 0, cx0
    while x < x1:
        if colcnt[x] >= thr: last = x; gap = 0
        else:
            gap += 1
            if gap >= GAP: break
        x += 1
    cx1 = last
    # vertical trim measured only within the drink columns
    rthr = max(6, int((cx1-cx0)*0.04))
    rowc = [0]*h
    for y in range(y0, y1):
        b = y*w; c = 0
        for x in range(cx0, cx1+1):
            if m[b+x]: c += 1
        rowc[y] = c
    cy0 = y0
    while cy0 < y1 and rowc[cy0] < rthr: cy0 += 1
    cy1 = y1-1
    while cy1 > cy0 and rowc[cy1] < rthr: cy1 -= 1
    px_, py_ = int(w*0.03), int(h*0.02)
    return (max(0, cx0-px_), max(0, cy0-py_), min(w, cx1+px_), min(h, cy1+py_))

def process(path):
    name = os.path.splitext(os.path.basename(path))[0]
    im = Image.open(path).convert('RGB'); W, H = im.size
    # 1. web card
    cw = 820; ch = int(H*cw/W)
    im.resize((cw, ch), Image.LANCZOS).save(os.path.join(WEBC, name+'.jpg'),
                                            quality=84, optimize=True)
    # 2. illustration crop
    box = illustration_box(im)
    crop = im.crop(box)
    # downscale to <= 620 wide
    cwid = 620
    if crop.width > cwid:
        crop = crop.resize((cwid, int(crop.height*cwid/crop.width)), Image.LANCZOS)
    crop.save(os.path.join(ILLU, name+'.jpg'), quality=88, optimize=True)
    print(f'{name}: card {cw}x{ch}  illu box={box} -> {crop.size}')
    return name, im, box

def contact_sheet(items):
    cols = 5; rows = (len(items)+cols-1)//cols
    tw, th = 240, 320
    sheet = Image.new('RGB', (cols*tw, rows*th), (24,20,17))
    for i,(name, im, box) in enumerate(items):
        th_im = im.copy()
        # draw box
        from PIL import ImageDraw
        d = ImageDraw.Draw(th_im)
        d.rectangle(box, outline=(255,60,60), width=8)
        th_im = th_im.resize((tw-12, th-12))
        sheet.paste(th_im, ((i%cols)*tw+6, (i//cols)*th+6))
    sheet.save(r'D:/CLAUDE_ONLY/cocktail/work/debug/illu_contact.jpg', quality=85)

if __name__ == '__main__':
    items = []
    for f in sorted(glob.glob(os.path.join(CARDS, '*.jpg'))):
        items.append(process(f))
    contact_sheet(items)
    print('contact sheet written')
