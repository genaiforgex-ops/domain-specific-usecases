"""On-brand GenAIForge performance banner template — the Figma Plugin-API code generator.

Ported from the standalone `generate_banners.py` so the backend owns its own copy
(it must not import a repo-root script). Builds the JavaScript that `use_figma`
runs inside a Figma file: one creative per content × the five ad sizes, on the
ink + bronze brand system with the GenAIForge logo lockup, a bronze/purple/teal
dot ribbon, the AI hero image, Inter headline/body, a bronze pill CTA, and a footer.

Each size has a dedicated builder tuned to the exact CSS spec of that format, and
each format's brand strip (dot ribbon + centred GenAIForge wordmark) is embedded from
`assets/<W>X<H>.svg`. Because `use_figma` caps its `code` argument at 50k chars,
the render loop injects only ONE size's strip per call (see build_figma_code) and
the export service issues one call per size.

Content is injected from Python (BRAND / CONTENTS / SIZES); the JS body never
hardcodes copy. The only per-call inputs are the content dicts — each carries the
Figma `image_hash` of an uploaded hero image (see the export service).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from app.config import settings

# Brand system — GenAIForge Marketing (ink + bronze).
BRAND = {
    "bg": "#0B0C10",  # ink background
    "gold": "#B8956C",  # bronze (primary)
    "purple": "#6D17CE",  # secondary accent
    "teal": "#1CBABA",  # sparkle accent
    "white": "#FFFFFF",
    "grey": "#F5F5F6",
    "cta_bg": "#B8956C",  # bronze pill
    "cta_fg": "#0B0C10",  # ink label on bronze
    "dots": ["#278BC1", "#B8956C", "#6D17CE"],  # ribbon = blue / bronze / purple
    "head": "Bold",  # Inter style for headlines
    "body": "Regular",  # Inter style for body
    "logo_aspect": round(180 / 32, 4),  # GenAIForge horizontal wordmark W/H
    "hero_aspect": round(420 / 284, 4),  # hero photo W/H; AI heroes are generated to match
}

# The 5 performance-ad formats. `pos` = where the hero image sits.
SIZES = [
    {"name": "square", "w": 1200, "h": 1200, "pos": "top"},
    {"name": "story", "w": 1080, "h": 1920, "pos": "bottom"},
    {"name": "portrait", "w": 1200, "h": 1500, "pos": "bottom"},
    {"name": "landscape", "w": 1920, "h": 1080, "pos": "left"},
    {"name": "link", "w": 1200, "h": 628, "pos": "left"},
]

FOOTER_LEFT = "Premium offers · limited time"
FOOTER_RIGHT = "*T&Cs apply"

# use_figma caps the `code` argument at 50k characters. build_figma_code embeds
# only one size's strip per call, keeping every payload under this limit.
CODE_LIMIT = 50000

# Per-size brand strip vectors (dot ribbon + centred GenAIForge wordmark),
# named by banner dimensions. Two transforms happen at load (see
# _shrink_strip_svg): clip-paths are stripped and each verbose dot path is
# rewritten as a compact <circle>.
_STRIP_FILES = {
    "square": "1200X1200.svg",
    "story": "1080X1920.svg",
    "portrait": "1200X1500.svg",
    "landscape": "1920X1080.svg",
    "link": "1200X628.svg",
}
_DOT_COLORS = {"#278BC1", "#6D17CE", "#D5A963"}


def _load_logo_svg() -> str:
    """The GenAIForge horizontal wordmark (on-dark) for the ink background."""
    path = os.path.join(settings.brand_assets_dir, "genaiforge_logo_horizontal_ondark.svg")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _shrink_strip_svg(raw: str) -> str:
    """Compact a brand strip SVG so the injected plugin code stays under
    use_figma's 50k-char limit. Each dot (a verbose 4-bezier circle path) becomes
    a <circle> from its bounding box; clip wrappers and inter-element whitespace
    are dropped. Logo paths (irregular fills) are left untouched."""

    def _dot(m):
        d, fill = m.group(1), m.group(2)
        if fill.upper() not in _DOT_COLORS:
            return m.group(0)  # logo paths are irregular — keep as-is
        nums = [float(x) for x in re.findall(r"-?\d+\.?\d*", d)]
        xs, ys = nums[0::2], nums[1::2]
        cx, cy, r = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (max(xs) - min(xs)) / 2
        return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}"/>'

    svg = re.sub(r'<path d="([^"]*)"\s*fill="(#[0-9A-Fa-f]{6})"\s*/>', _dot, raw)
    svg = re.sub(r'\s*clip-path="url\([^)]*\)"', "", svg)  # any clip wrapper
    return re.sub(r">\s+<", "><", svg).strip()  # drop inter-element whitespace


def _load_strips() -> dict[str, str]:
    """name -> shrunk strip SVG (only sizes whose asset file is present)."""
    strips: dict[str, str] = {}
    for name, fname in _STRIP_FILES.items():
        path = os.path.join(settings.brand_assets_dir, fname)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                strips[name] = _shrink_strip_svg(fh.read())
    return strips


# Loaded once at import — the strip assets are static brand vectors.
STRIPS = _load_strips()


def make_content(
    headline: str,
    body: str,
    cta: str,
    image_hash: str,
    footer_left: str = FOOTER_LEFT,
    footer_right: str = FOOTER_RIGHT,
) -> dict:
    """Shape one creative into the content dict the template consumes."""
    return {
        "headline": headline,
        "body": body,
        "cta": cta,
        "image_hash": image_hash,
        "footer_left": footer_left,
        "footer_right": footer_right,
    }


# Figma Plugin-API template (one creative per content x size). BRAND / CONTENTS
# / SIZES / LOGO_SVG / STRIP_SVG / ONLY_SIZE / CLEAR / HEADER are injected from
# Python; this body never hardcodes content.
FIGMA_JS_BODY = r"""
const C = BRAND;
const hx = h => { h=String(h).replace('#',''); return {r:parseInt(h.slice(0,2),16)/255,g:parseInt(h.slice(2,4),16)/255,b:parseInt(h.slice(4,6),16)/255}; };
const solid = (h,o)=>[{type:'SOLID',color:hx(h),opacity:o==null?1:o}];
const cl=(v,a,b)=>Math.max(a,Math.min(b,v));
await figma.loadFontAsync({family:'Inter', style:C.head});
await figma.loadFontAsync({family:'Inter', style:C.body});

const ids=[];
const mk=(t,st,sz,col,op)=>{const n=figma.createText();n.fontName={family:'Inter',style:st};n.characters=String(t);n.fontSize=sz;n.fills=solid(col,op);return n;};
const linesOf=(n,s)=>Math.max(1,Math.round(n.height/(s*1.22)));
// Dot ribbon geometry for the brand strip:
// a 6-row grid of round tiles, dot radius ~3.7% of band height, centres ~2.5x
// the diameter apart, colours split in equal thirds and scattered pseudo-randomly
// (not the old diagonal stripe). The brand "Vector" tiles are round dots, not
// sharp squares, so we emit <circle> not <rect>. `pick` is a deterministic hash so a
// given cell always lands on the same colour, while the mix stays even across the 3.
const dotSvg=(w,h,cf,ct)=>{const r=Math.max(2,h*0.037),gap=r*5.0;
  const pick=(ci,ri)=>{let x=(ci*374761393+ri*668265263)>>>0;x=((x^(x>>>13))*1274126177)>>>0;return C.dots[x%C.dots.length];};
  let c='';for(let ri=0,y=r;y<h-r*0.5;ri++,y+=gap)for(let ci=0,x=r;x<w-r*0.5;ci++,x+=gap){if(cf!=null&&x>cf&&x<ct)continue;c+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+r.toFixed(1)+'" fill="'+pick(ci,ri)+'"/>';}
  return '<svg width="'+w+'" height="'+h+'" xmlns="http://www.w3.org/2000/svg">'+c+'</svg>';};

// Official logo lockup + dot ribbon ("strips"). The ribbon dots flank the logo;
// the centre band of dots is cleared so the official vector reads cleanly.
const buildBandLogo=(f,bandX,bandW,bandY,bandH,logoCX,size)=>{
  if(STRIP_SVG){
    // This size's brand strip (dot ribbon + centred logo, one SVG). The strip is
    // exported at its target pixel size, so its native width already carries the
    // designer's intended side padding. Place it at native scale to preserve that
    // padding; only shrink (never enlarge) if it is wider than the band region,
    // then centre it in the region both ways. Band height follows the strip.
    const band=figma.createNodeFromSvg(STRIP_SVG);f.appendChild(band);ids.push(band.id);
    const sc=Math.min(1, bandW/band.width);
    if(sc<1) band.rescale(sc);
    band.x=Math.round(bandX+(bandW-band.width)/2);
    band.y=Math.round(bandY+Math.max(0,(bandH-band.height)/2));
    return Math.round(band.y+band.height);
  }
  // Fallback (no strip asset for this size): generated dot ribbon with the centre
  // cleared, plus the standalone logo lockup overlaid in the gap.
  const logoH=Math.round(bandH*0.86), logoW=Math.round(logoH*(C.logo_aspect||3.12));
  const clearHalf=logoW/2+Math.round(bandH*0.45);
  const cf=bandW/2-clearHalf, ct=bandW/2+clearHalf;
  const band=figma.createNodeFromSvg(dotSvg(bandW,bandH,cf,ct));band.x=bandX;band.y=bandY;f.appendChild(band);ids.push(band.id);
  const logo=figma.createNodeFromSvg(LOGO_SVG);f.appendChild(logo);ids.push(logo.id);
  logo.rescale(logoH/logo.height);
  logo.x=Math.round(logoCX-logo.width/2);logo.y=Math.round(bandY+bandH/2-logo.height/2);
  return bandY+bandH;
};

// Fit headline+body+CTA into availH; prominent headline, shrink only if needed.
// Returns {headline, body, cta, total, gapHB, gapBC, Hs, hL, bL}.
const fitBlock=(f,colW,availH,content,align)=>{
  const headline=mk(content.headline,C.head,40,C.white);headline.textAlignHorizontal=align;headline.textAutoResize='HEIGHT';
  const body=mk(content.body,C.body,30,C.white,0.92);body.textAlignHorizontal=align;body.textAutoResize='HEIGHT';
  f.appendChild(headline);f.appendChild(body);ids.push(headline.id,body.id);
  // Base sizes come from square.css: headline 68px, body 32px, CTA label 32px
  // on a 1080-wide creative (colW~=888..950), i.e. headline ~=0.072*colW; body
  // and CTA label are 32/68=0.47 of the headline. The loop only shrinks from
  // here to make long copy fit — it never grows past the brand size.
  let Hs=Math.round(colW*0.072);const minHs=Math.round(colW*0.05);
  let hL=2,bL=1,total=0,ctaH=0,gapHB=0,gapBC=0;
  const measure=()=>{
    headline.fontSize=Hs;headline.resize(colW,headline.height);hL=linesOf(headline,Hs);
    const bs=Math.round(Hs*0.47);body.fontSize=bs;body.resize(colW,body.height);bL=linesOf(body,bs);
    const cfs=Math.round(Hs*0.47);ctaH=Math.round(cfs*1.2)+2*Math.round(cfs*0.58);
    gapHB=Math.round(Hs*0.47);gapBC=Math.round(Hs*0.58);  // headline->body gap = 32/68 of headline
    total=headline.height+gapHB+body.height+gapBC+ctaH;
  };
  measure();
  while(Hs>minHs && (total>availH || hL>3 || bL>(hL>=3?2:3))){Hs-=3;measure();}
  const cta=figma.createFrame();cta.layoutMode='HORIZONTAL';cta.primaryAxisSizingMode='AUTO';cta.counterAxisSizingMode='AUTO';
  const ctaFs=Math.round(Hs*0.47);  // button label 32/68 of headline (square.css)
  cta.paddingLeft=cta.paddingRight=Math.round(ctaFs*1.16);cta.paddingTop=cta.paddingBottom=Math.round(ctaFs*0.58);  // 37.16 / 18.58 px @ 32px
  cta.cornerRadius=Math.round(Hs*1.6);cta.fills=solid(C.cta_bg);
  const ctaT=mk(content.cta,C.head,ctaFs,C.cta_fg);cta.appendChild(ctaT);f.appendChild(cta);ids.push(cta.id,ctaT.id);
  return {headline,body,cta,total,gapHB,gapBC,Hs,hL,bL};
};

// Shared chrome for every creative: navy frame, footer, dot-ribbon + logo band,
// and a hero-image helper. Layout-specific placement lives in the 5 per-size
// builders below, so each template can be tuned in isolation.
const setup=(content,size,ox,oy)=>{
  const left = size.pos==='left';
  const f=figma.createFrame();
  f.name='Performance / '+content.headline.slice(0,26)+' / '+size.name+' '+size.w+'x'+size.h;
  f.x=ox;f.y=oy;f.resize(size.w,size.h);f.fills=solid(C.bg);f.clipsContent=true;figma.currentPage.appendChild(f);
  const pad=Math.round(size.w*(left?0.038:0.06));
  const align = left?'LEFT':'CENTER';

  // footer — left: provider line (24px per square.css); right: wrapped,
  // right-aligned disclaimer, smaller (16px = 0.66x the provider line).
  const fs=Math.round(Math.min(size.w,size.h)*0.022);
  const fl=mk(content.footer_left,C.body,fs,C.white,0.85);f.appendChild(fl);ids.push(fl.id);
  const fr=mk(content.footer_right,C.body,Math.round(fs*0.66),C.white,0.85);fr.textAlignHorizontal='RIGHT';fr.textAutoResize='HEIGHT';fr.resize(Math.round(size.w*0.46),fr.height);f.appendChild(fr);ids.push(fr.id);
  const footH=Math.max(fl.height,fr.height);
  const footerTop=size.h-Math.round(pad*0.7)-footH;
  const footGap=Math.round(pad*0.7), gapHT=Math.round(pad*0.85);

  // band + logo region
  const colX = left ? Math.round(size.w*0.5)+pad : pad;
  const colW = left ? size.w-colX-pad : size.w-pad*2;
  const bandH=Math.round(Math.min(size.w,size.h)*(left?0.075:0.09));  // 0.09 ~= square.css ribbon (102px / 1080)
  const bandY=Math.round(pad*0.5);
  // Left layouts: band sits in the right half, inset by `pad` on the right so the
  // strip doesn't touch the banner edge. Top layouts: full width — the strip's own
  // native padding (it's narrower than the banner) provides the side margins.
  const bandX = left ? Math.round(size.w*0.5) : 0;
  const bandW = left ? size.w-bandX-pad : size.w;
  const logoCX = bandX+bandW/2;
  const bandBottom=buildBandLogo(f,bandX,bandW,bandY,bandH,logoCX,size);

  fl.x = left?colX:pad; fl.y=footerTop+footH-fl.height;
  fr.x = size.w-pad-fr.width; fr.y=footerTop+footH-fr.height;

  const heroR=Math.round(size.w*0.0296);  // 32px radius on a 1080-wide creative (square.css Frame 1 border-radius)
  const newHero=(w,h,x,y)=>{const r=figma.createRectangle();r.resize(w,h);r.cornerRadius=heroR;r.fills=[{type:'IMAGE',scaleMode:'FILL',imageHash:content.image_hash}];f.appendChild(r);ids.push(r.id);r.x=x;r.y=y;return r;};

  return {f,left,pad,align,colX,colW,footerTop,footGap,gapHT,bandBottom,newHero,fl,fr,footH};
};

// ---- Template 1: square (1200x1200) — hero on top, text block below. ----
const buildSquare=(content,size,ox,oy)=>{
  const s=setup(content,size,ox,oy);
  const heroPad=Math.round(size.w*0.0296), heroW=size.w-2*heroPad;  // 32px side margin @1080 (square.css image 1016/1080)
  const heroTop=s.bandBottom+Math.round(s.pad*0.7);
  const minH=Math.round(size.h*0.30),maxH=Math.round(size.h*0.42);
  const textBottom=s.footerTop-s.footGap;
  const availText=textBottom-(heroTop+minH+s.gapHT);
  const blk=fitBlock(s.f,s.colW,availText,content,s.align);
  const heroH=cl(textBottom-blk.total-s.gapHT-heroTop,minH,maxH);
  s.newHero(heroW,heroH,heroPad,heroTop);
  const contentTop=heroTop+heroH+s.gapHT, availH=textBottom-contentTop;
  let y=contentTop+Math.max(0,Math.round((availH-blk.total)/2));
  blk.headline.x=s.pad;blk.headline.y=y;y+=blk.headline.height+blk.gapHB;
  blk.body.x=s.pad;blk.body.y=y;y+=blk.body.height+blk.gapBC;
  blk.cta.x=Math.round((size.w-blk.cta.width)/2);blk.cta.y=y;
  return s.f;
};

// ---- Template 2: story (1080x1920) — exact spec from the 1080x1920 CSS. ----
// Frame 5 copy block anchored at top 222 (headline 68 → body 32 → CTA 32 →
// provider 24, centred, gaps 32/64/20); Frame 1 image 1016x1050 at (32,774)
// r32; T&C footnote centred, width 894, bottom 46. All px scale with the frame.
const buildStory=(content,size,ox,oy)=>{
  const s=setup(content,size,ox,oy);
  const sx=size.w/1080, sy=size.h/1920;
  const px=v=>Math.round(v*sx), py=v=>Math.round(v*sy);
  const colW=px(888), colX=Math.round((size.w-colW)/2);

  // Copy block: headline + body, centred, at the fixed CSS sizes.
  const headline=mk(content.headline,C.head,px(68),C.white);headline.textAlignHorizontal='CENTER';headline.textAutoResize='HEIGHT';s.f.appendChild(headline);ids.push(headline.id);headline.resize(colW,headline.height);
  const body=mk(content.body,C.body,px(32),C.white);body.textAlignHorizontal='CENTER';body.textAutoResize='HEIGHT';s.f.appendChild(body);ids.push(body.id);body.resize(colW,body.height);

  // CTA pill: 32px label, black text, pill radius; padding 37.16 x / 18.58 y.
  const cta=figma.createFrame();cta.layoutMode='HORIZONTAL';cta.primaryAxisSizingMode='AUTO';cta.counterAxisSizingMode='AUTO';
  cta.paddingLeft=cta.paddingRight=px(37.16);cta.paddingTop=cta.paddingBottom=py(18.58);
  cta.cornerRadius=Math.round(py(75.16)/2);cta.fills=solid(C.cta_bg);
  const ctaT=mk(content.cta,C.head,px(32),C.cta_fg);cta.appendChild(ctaT);s.f.appendChild(cta);ids.push(cta.id,ctaT.id);

  // Provider line (footer_left) — 24px, centred, directly under the CTA.
  const prov=s.fl;prov.fontSize=px(24);prov.textAlignHorizontal='CENTER';prov.textAutoResize='HEIGHT';prov.resize(colW,prov.height);

  // Stack Frame 5: headline, +32, body, +64, CTA, +20, provider. The internal
  // gaps (32/64/20) are the fixed brand spacing from the CSS; only the block's
  // start-Y adapts. The CSS pins the block to top 222 assuming a full 505px
  // (3-line) headline, but copy varies and shorter text left an oversized gap
  // before the image. So centre the block in the region [222, 774-47] = the
  // exact CSS Frame 5 box: full-size copy still starts at 222 (identical to the
  // CSS), and shorter copy is balanced instead of clinging to the top.
  const imageTop=py(774), regionTop=py(222), regionBottom=imageTop-py(47);
  const blockH=headline.height+py(32)+body.height+py(64)+cta.height+py(20)+prov.height;
  let y=regionTop+Math.max(0,Math.round(((regionBottom-regionTop)-blockH)/2));
  headline.x=colX;headline.y=y;y+=headline.height+py(32);
  body.x=colX;body.y=y;y+=body.height+py(64);
  cta.x=Math.round((size.w-cta.width)/2);cta.y=y;y+=cta.height+py(20);
  prov.x=colX;prov.y=y;

  // Frame 1 image: 1016 x 1050 at (32, 774), radius 32.
  s.newHero(px(1016),py(1050),px(32),imageTop);

  // T&C footnote (footer_right) — 16px, centred, width 894, bottom 46.
  const tc=s.fr;tc.fontSize=px(16);tc.textAlignHorizontal='CENTER';tc.textAutoResize='HEIGHT';tc.resize(px(894),tc.height);
  tc.x=Math.round((size.w-tc.width)/2);tc.y=size.h-py(46)-tc.height;
  return s.f;
};

// ---- Template 3: portrait (1200x1500) — text block on top, hero below. ----
const buildPortrait=(content,size,ox,oy)=>{
  const s=setup(content,size,ox,oy);
  const textTop=s.bandBottom+s.gapHT;
  // Hero rectangle per square.css proportions: full width with a 32px side
  // margin (0.0296*w), up to ~0.547*h tall.
  const heroMargin=Math.round(size.w*0.0296), heroW=size.w-2*heroMargin;
  const minH=Math.round(size.h*0.40),maxH=Math.round(size.h*0.55);
  const heroBottom=s.footerTop-s.footGap;
  const availText=(heroBottom-minH-s.gapHT)-textTop;
  const blk=fitBlock(s.f,s.colW,availText,content,s.align);
  let y=textTop;
  blk.headline.x=s.pad;blk.headline.y=y;y+=blk.headline.height+blk.gapHB;
  blk.body.x=s.pad;blk.body.y=y;y+=blk.body.height+blk.gapBC;
  blk.cta.x=Math.round((size.w-blk.cta.width)/2);blk.cta.y=y;
  const heroTop=y+blk.cta.height+s.gapHT;
  const heroH=cl(heroBottom-heroTop,minH,maxH);
  s.newHero(heroW,heroH,heroMargin,heroTop);
  return s.f;
};

// ---- Template 4: landscape (1920x1080) — exact spec from the 1920x1080 CSS. ----
// Frame 1 image 854x1008 at (33, vertically centred), r32 on the left;
// Frame 4 copy block on the right (x 968.84, width 901.16): headline 72 → body 44 →
// CTA (label 40), gaps 32/64, block centred vertically; provider line 24 at (968,989);
// T&C footnote 14, right-aligned, width 429, bottom 60. All px scale with the frame.
const buildLandscape=(content,size,ox,oy)=>{
  const s=setup(content,size,ox,oy);
  const sx=size.w/1920, sy=size.h/1080;
  const px=v=>Math.round(v*sx), py=v=>Math.round(v*sy);

  // Frame 1 image: 854 x 1008 at left 33, vertically centred, radius 32.
  // (Override newHero's default radius: it scales off the 1080-wide baseline, so
  // on this 1920-wide frame it would render ~57px instead of the CSS's 32px.)
  const heroH=py(1008);
  const hero=s.newHero(px(854),heroH,px(33),Math.round((size.h-heroH)/2));
  hero.cornerRadius=px(32);

  // Frame 4 copy column: x 968.84, width 901.16 (right margin 50).
  const colX=px(968.84), colW=size.w-colX-px(50);

  // Headline 72px Black + body 44px Regular, left-aligned, white.
  const headline=mk(content.headline,C.head,px(72),C.white);headline.textAlignHorizontal='LEFT';headline.textAutoResize='HEIGHT';s.f.appendChild(headline);ids.push(headline.id);headline.resize(colW,headline.height);
  const body=mk(content.body,C.body,px(44),C.white);body.textAlignHorizontal='LEFT';body.textAutoResize='HEIGHT';s.f.appendChild(body);ids.push(body.id);body.resize(colW,body.height);

  // CTA pill: 40px label, black text, pill radius; padding 37.16 x / 18.58 y.
  const cta=figma.createFrame();cta.layoutMode='HORIZONTAL';cta.primaryAxisSizingMode='AUTO';cta.counterAxisSizingMode='AUTO';
  cta.paddingLeft=cta.paddingRight=px(37.16);cta.paddingTop=cta.paddingBottom=py(18.58);
  cta.cornerRadius=Math.round(py(85.16)/2);cta.fills=solid(C.cta_bg);
  const ctaT=mk(content.cta,C.head,px(40),C.cta_fg);cta.appendChild(ctaT);s.f.appendChild(cta);ids.push(cta.id,ctaT.id);

  // Stack Frame 4: headline, +32, body, +64, CTA. The internal gaps (32/64) are
  // the fixed brand spacing from the CSS; the block is centred vertically so
  // full-size copy starts at the CSS top 285 and shorter copy stays balanced.
  const blockH=headline.height+py(32)+body.height+py(64)+cta.height;
  let y=Math.round((size.h-blockH)/2);
  headline.x=colX;headline.y=y;y+=headline.height+py(32);
  body.x=colX;body.y=y;y+=body.height+py(64);
  cta.x=colX;cta.y=y;

  // Provider line (footer_left) — 24px, left-aligned at (968, 989), width 398.
  const prov=s.fl;prov.fontSize=px(24);prov.textAlignHorizontal='LEFT';prov.textAutoResize='HEIGHT';prov.resize(px(398),prov.height);
  prov.x=px(968);prov.y=py(989);

  // T&C footnote (footer_right) — 14px, right-aligned, width 429, bottom 60.
  const tc=s.fr;tc.fontSize=px(14);tc.textAlignHorizontal='RIGHT';tc.textAutoResize='HEIGHT';tc.resize(px(429),tc.height);
  tc.x=size.w-px(50)-tc.width;tc.y=size.h-py(60)-tc.height;
  return s.f;
};

// ---- Template 5: link (1200x628) — exact spec from the 1200x628 CSS. ----
// Frame 1 image 520x580 at (32.1, vertically centred), r32 on the left;
// Copy-block+CTA box on the right (left 552, width 614, padding 0 48 → content
// x 600, width 518): headline 48 Black → body 26 Regular → CTA (label 24),
// gaps 32/32, block centred vertically in its 340.16px box; footer at left 600,
// bottom 26 — provider 16 left-aligned, T&C 9 right-aligned. All px scale with
// the frame.
const buildLink=(content,size,ox,oy)=>{
  const s=setup(content,size,ox,oy);
  const sx=size.w/1200, sy=size.h/628;
  const px=v=>Math.round(v*sx), py=v=>Math.round(v*sy);

  // Frame 1 image: 520 x 580 at left 32.1, vertically centred, radius 32.
  // (Override newHero's default radius so it renders the CSS's 32px, not the
  // ~36px its 1080-wide baseline would give on this frame.)
  const heroH=py(580);
  const hero=s.newHero(px(520),heroH,px(32.1),Math.round((size.h-heroH)/2));
  hero.cornerRadius=px(32);

  // Copy-block+CTA box: left 552, width 614, padding 0 48 → content x 600, width 518.
  const colX=px(600), colW=px(518);

  // Headline 48px Black + body 26px Regular, left-aligned, white.
  const headline=mk(content.headline,C.head,px(48),C.white);headline.textAlignHorizontal='LEFT';headline.textAutoResize='HEIGHT';s.f.appendChild(headline);ids.push(headline.id);headline.resize(colW,headline.height);
  const body=mk(content.body,C.body,px(26),C.white);body.textAlignHorizontal='LEFT';body.textAutoResize='HEIGHT';s.f.appendChild(body);ids.push(body.id);body.resize(colW,body.height);

  // CTA pill: 24px label, black text, pill radius; padding 37.16 x / 18.58 y.
  const cta=figma.createFrame();cta.layoutMode='HORIZONTAL';cta.primaryAxisSizingMode='AUTO';cta.counterAxisSizingMode='AUTO';
  cta.paddingLeft=cta.paddingRight=px(37.16);cta.paddingTop=cta.paddingBottom=py(18.58);
  cta.cornerRadius=Math.round(py(66.16)/2);cta.fills=solid(C.cta_bg);
  const ctaT=mk(content.cta,C.head,px(24),C.cta_fg);cta.appendChild(ctaT);s.f.appendChild(cta);ids.push(cta.id,ctaT.id);

  // Stack: headline, +32, body, +32, CTA. Internal gaps (32/32) are the fixed
  // brand spacing from the CSS; the block is centred vertically in its 340.16px
  // box (top calc(50% - 340.16/2)) so full-size copy matches the CSS and shorter
  // copy stays balanced.
  const boxH=py(340.16), boxTop=Math.round((size.h-boxH)/2);
  const blockH=headline.height+py(32)+body.height+py(32)+cta.height;
  let y=boxTop+Math.max(0,Math.round((boxH-blockH)/2));
  headline.x=colX;headline.y=y;y+=headline.height+py(32);
  body.x=colX;body.y=y;y+=body.height+py(32);
  cta.x=colX;cta.y=y;

  // Footer at bottom 26. Provider line (footer_left) — 16px, left-aligned at 600.
  const prov=s.fl;prov.fontSize=px(16);prov.textAlignHorizontal='LEFT';prov.textAutoResize='HEIGHT';prov.resize(px(281.5),prov.height);
  prov.x=px(600);prov.y=size.h-py(26)-prov.height;

  // T&C footnote (footer_right) — 9px, right-aligned, ending at right margin 37.
  const tc=s.fr;tc.fontSize=px(9);tc.textAlignHorizontal='RIGHT';tc.textAutoResize='HEIGHT';tc.resize(px(281.5),tc.height);
  tc.x=size.w-px(37)-tc.width;tc.y=size.h-py(26)-tc.height;
  return s.f;
};

// Dispatch by size name → its dedicated template builder.
const BUILDERS={square:buildSquare,story:buildStory,portrait:buildPortrait,landscape:buildLandscape,link:buildLink};

if(CLEAR){ for(const n of figma.currentPage.children.slice()) n.remove(); }
if(HEADER){ const t=mk('Performance creatives (on-brand template)',C.body,48,'#111827');t.x=0;t.y=40;figma.currentPage.appendChild(t);ids.push(t.id); }

// Grid layout: columns = contents, rows = sizes. Only ONLY_SIZE is built in this
// call (its strip is the one embedded), so we build that one row for every content
// at the absolute row-Y it would occupy in the full grid.
const GAPX=160, GAPY=140, headerY=160;
const maxColW=Math.max.apply(null, SIZES.map(s=>s.w));
const rowY=[];let acc=headerY;for(let r=0;r<SIZES.length;r++){rowY.push(acc);acc+=SIZES[r].h+GAPY;}
const onlyIdx=SIZES.findIndex(s=>s.name===ONLY_SIZE);
const size=SIZES[onlyIdx];
for(const item of CONTENTS){
  const f=(BUILDERS[size.name]||buildSquare)(item, size, item.col*(maxColW+GAPX), rowY[onlyIdx]);
  ids.push(f.id);
}
figma.viewport.scrollAndZoomIntoView(figma.currentPage.children);
return { built: ids.length };
"""


@dataclass(frozen=True)
class TemplateBundle:
    """Everything needed to render one banner template — sourced either from a
    DB `BannerTemplate` row (see banner_template_service) or from the built-in
    definition below (`builtin_bundle`)."""

    brand: dict
    sizes: list[dict]
    js_body: str
    strips: dict[str, str]  # size name -> shrunk strip SVG
    footer_left: str
    footer_right: str
    # Hero-photo art-direction fed to the image model so the subject is composed to
    # leave this template's copy area clear (see banner_image_service).
    image_brief: str = ""
    # Image model output shape/resolution for this format (real params, not prompt
    # text). image_aspect = Gemini aspect ratio; image_size = "1K"/"2K"/"4K". Empty
    # = model default.
    image_aspect: str = ""
    image_size: str = ""


# Where the hero photo sits in each performance layout, as fractions of the creative's
# width/height. The photo is placed with scaleMode FILL, so it is CENTRE-CROPPED to
# this rectangle's aspect — which is what the Designer's crop guides need to show.
#
# MUST stay in sync with FIGMA_JS_BODY's per-size builders above; each entry cites
# the line it mirrors. Square and portrait size the hero from the copy block's
# height, so their aspect is a range, not a value — the guide marks those inexact.
_W_MARGIN = 1 - 2 * 0.0296  # heroW = size.w - 2*round(size.w*0.0296)
PERFORMANCE_HERO_RECTS: dict[str, dict] = {
    # buildSquare: heroW = 0.9408w, heroH = clamp(…, 0.30h, 0.42h)
    "square": {"w": _W_MARGIN, "h_min": 0.30, "h_max": 0.42},
    # buildStory: Frame 1 image 1016x1050 of the 1080x1920 reference
    "story": {"w": 1016 / 1080, "h_min": 1050 / 1920, "h_max": 1050 / 1920},
    # buildPortrait: heroW = 0.9408w, heroH = clamp(…, 0.40h, 0.55h)
    "portrait": {"w": _W_MARGIN, "h_min": 0.40, "h_max": 0.55},
    # buildLandscape: Frame 1 image 854x1008 of the 1920x1080 reference
    "landscape": {"w": 854 / 1920, "h_min": 1008 / 1080, "h_max": 1008 / 1080},
    # buildLink: Frame 1 image 520x580 of the 1200x628 reference
    "link": {"w": 520 / 1200, "h_min": 580 / 628, "h_max": 580 / 628},
}

# The copy block's footer band, as a fraction of height (MESSAGING_JS_BODY footBand).
_MESSAGING_FOOTER_BAND = 0.18


def hero_guides_for(brand: dict, sizes: list[dict]) -> dict:
    """Describe, for the Designer's crop guides, how this template crops the hero.

    Derived from data every template row already carries, so it works for built-in
    and DB-defined templates alike:

    * A **full-bleed** template (every size has ``pos == "full"``, e.g. messaging)
      centre-crops the hero to the creative's own aspect, and lays copy *over* it —
      so the copy column is reported too, from the brand's pad/col/copy_side.
    * A **framed** template (performance) centre-crops the hero into a sub-rectangle per
      layout (see PERFORMANCE_HERO_RECTS) and puts copy outside the photo, so there is
      no copy zone to avoid — only crop shapes to survive.

    Sizes whose hero rect isn't known are omitted rather than guessed at.
    """
    sizes = sizes or []
    full_bleed = bool(sizes) and all((s.get("pos") or "") == "full" for s in sizes)

    crops: list[dict] = []
    for s in sizes:
        w, h = float(s.get("w") or 0), float(s.get("h") or 0)
        if w <= 0 or h <= 0:
            continue
        name = s.get("name", "")
        if full_bleed:
            crops.append({"name": name, "aspect": w / h, "min": w / h, "max": w / h, "exact": True})
            continue
        rect = PERFORMANCE_HERO_RECTS.get(name)
        if rect is None:
            continue  # unknown layout — say nothing rather than draw a fiction
        # Widest crop comes from the SHORTEST hero, and vice versa.
        lo = (rect["w"] * w) / (rect["h_max"] * h)
        hi = (rect["w"] * w) / (rect["h_min"] * h)
        crops.append(
            {
                "name": name,
                "aspect": (lo + hi) / 2,
                "min": lo,
                "max": hi,
                "exact": rect["h_min"] == rect["h_max"],
            }
        )

    copy_zone = None
    if full_bleed and brand:
        pad = brand.get("pad")
        col = brand.get("col")
        if isinstance(pad, (int, float)) and isinstance(col, (int, float)):
            side = "right" if brand.get("copy_side") == "right" else "left"
            x0 = 1 - pad - col if side == "right" else pad
            copy_zone = {
                "side": side,
                "x0": max(0.0, min(1.0, x0)),
                "x1": max(0.0, min(1.0, x0 + col)),
                "footer": _MESSAGING_FOOTER_BAND,
            }

    return {"mode": "full-bleed" if full_bleed else "framed", "crops": crops, "copy": copy_zone}


def builtin_bundle() -> TemplateBundle:
    """The brand-baked performance template. This is what the banner_templates
    migration seeds as the default, and the safe fallback the export uses if no
    template row exists yet."""
    return TemplateBundle(
        brand=BRAND,
        sizes=SIZES,
        js_body=FIGMA_JS_BODY,
        strips=STRIPS,
        footer_left=FOOTER_LEFT,
        footer_right=FOOTER_RIGHT,
        image_brief=PERFORMANCE_IMAGE_BRIEF,
        # Heroes are generated 16:9 (same shape as the messaging template), then
        # centre-cropped into each performance format.
        image_aspect="16:9",
    )


# --------------------------------------------------------------------------- #
# Messaging template — WhatsApp / RCS / Rich Push Notification.
#
# Ported from the standalone `generate_credit_banners.py`. A very different design
# from the performance template: a full-bleed lifestyle hero photo, a left dark→transparent gradient
# scrim for legibility, an Inter Bold headline, an Inter Regular body line, and a
# small footer. It reuses the same DB-backed template plumbing (build_figma_code's
# injection contract), so the export renders it exactly like the performance template — one size per
# use_figma call, contents laid out as columns and sizes as rows.
# --------------------------------------------------------------------------- #

# Brand system for the messaging formats (GenAIForge Marketing). Copy sits
# white over the dark scrim; layout ratios are calibrated from the WA 1125x600 ref.
MESSAGING_BRAND = {
    "head": "Bold",  # Inter style for headlines
    "body": "Regular",  # Inter style for body / footer
    "text": "#FFFFFF",  # headline + body over the dark scrim
    "footer": "#F6F7F8",  # "Vibrancy/Text & Icon/light/secondary"
    "footer_op": 0.63,  # footer opacity (design: rgba(246,247,248,0.63))
    # Left-anchored scrim: near-opaque dark on the copy side, fading to clear over
    # the subject, for reliable legibility.
    "scrim": "#060606",
    "scrim_stops": [[0.0, 0.80], [0.45, 0.55], [0.72, 0.12], [1.0, 0.0]],
    # Layout ratios (of frame width), calibrated from the WA 1125x600 reference:
    "pad": 0.064,  # left/edge padding      (72/1125)
    "col": 0.50,  # text column width       (~537/1125 + slack)
    "head_size": 0.0489,  # headline font       (55/1125)
    "body_size": 0.0284,  # body font           (32/1125)
    "foot_size": 0.0107,  # footer font         (12/1125)
    "gap": 0.0293,  # headline→body gap       (33/1125)
    # Which side the copy (scrim + headline/body/footer) sits on. The hero subject
    # is composed on the OPPOSITE side (see MESSAGING_IMAGE_BRIEF), so the two never
    # collide. "left" = copy left, subject right (the original messaging design).
    "copy_side": "left",
}

# Art-direction for the hero photo, per template. Fed to the image model so the
# subject is composed to leave the copy area as clean negative space. The messaging
# template overlays copy on the left, so the subject goes RIGHT; performance keeps the
# subject slightly off-centre with space for the framed overlay.
PERFORMANCE_IMAGE_BRIEF = (
    "Place the subject slightly off-centre and keep calm, uncluttered negative space "
    "to one side so a headline and logo can be added later. Frame so it crops cleanly "
    "to both tall (story/portrait) and wide (landscape) formats."
)
MESSAGING_IMAGE_BRIEF = (
    "Compose the person/subject firmly on the RIGHT side of the frame and keep the "
    "LEFT half as calm, uncluttered negative space — the banner overlays its headline "
    "and body copy on the left, over a dark scrim, so the left side must stay clean. "
    "Frame for a wide, landscape messaging-card crop."
)

# The three messaging formats and their pixel dimensions (from the source design).
# `pos` satisfies the size schema; the full-bleed layout doesn't use it.
MESSAGING_SIZES = [
    {"name": "WA", "w": 1125, "h": 600, "pos": "full"},  # WhatsApp
    {"name": "RCS", "w": 1440, "h": 720, "pos": "full"},  # Rich Communication Services
    {"name": "RPN", "w": 600, "h": 300, "pos": "full"},  # Rich Push Notification
]

MESSAGING_FOOTER_LEFT = ""
MESSAGING_FOOTER_RIGHT = "*T&C Apply"

# Figma Plugin-API template for the messaging formats. Consumes the SAME injected
# globals as the performance body (BRAND / CONTENTS / SIZES / ONLY_SIZE / CLEAR /
# HEADER); LOGO_SVG / STRIP_SVG are injected but unused. Builds one full-bleed
# creative per content: hero (FILL) → left scrim → headline → body → footer, laid
# out as columns (contents) × rows (sizes), one size per call.
MESSAGING_JS_BODY = r"""
const C = BRAND;
const hx = h => { h=String(h).replace('#',''); return {r:parseInt(h.slice(0,2),16)/255,g:parseInt(h.slice(2,4),16)/255,b:parseInt(h.slice(4,6),16)/255}; };
const solid = (h,o)=>[{type:'SOLID',color:hx(h),opacity:o==null?1:o}];
const linesOf=(n,s)=>Math.max(1,Math.round(n.height/(s*1.25)));
await figma.loadFontAsync({family:'Inter', style:C.head});
await figma.loadFontAsync({family:'Inter', style:C.body});

const ids=[];
const mk=(t,st,sz,col,op)=>{const n=figma.createText();n.fontName={family:'Inter',style:st};n.characters=String(t);n.fontSize=sz;n.fills=solid(col,op);n.textAutoResize='HEIGHT';return n;};

const buildCreative=(content,size,ox,oy)=>{
  const f=figma.createFrame();
  f.name='Messaging / '+String(content.headline).slice(0,26)+' / '+size.name+' '+size.w+'x'+size.h;
  f.x=ox;f.y=oy;f.resize(size.w,size.h);f.fills=solid('#000000');f.clipsContent=true;
  figma.currentPage.appendChild(f);

  // full-bleed hero photo (centre-crop FILL keeps the subject on the right)
  const hero=figma.createRectangle();hero.resize(size.w,size.h);hero.x=0;hero.y=0;
  hero.fills=[{type:'IMAGE',scaleMode:'FILL',imageHash:content.image_hash}];
  f.appendChild(hero);ids.push(hero.id);

  // dark→transparent scrim for copy legibility, anchored on the copy side. When
  // copy sits on the right, the gradient stops are mirrored so the dark end lands
  // on the right (the hero subject is composed on the opposite, clear side).
  const right=C.copy_side==='right';
  const stops=C.scrim_stops
    .map(s=>({position:right?(1-s[0]):s[0],color:Object.assign({},hx(C.scrim),{a:s[1]})}))
    .sort((a,b)=>a.position-b.position);
  const scrim=figma.createRectangle();scrim.resize(size.w,size.h);scrim.x=0;scrim.y=0;
  scrim.fills=[{type:'GRADIENT_LINEAR',gradientTransform:[[1,0,0],[0,1,0]],gradientStops:stops}];
  f.appendChild(scrim);ids.push(scrim.id);

  const pad=Math.round(size.w*C.pad);
  const colW=Math.round(size.w*C.col);
  const colX=right?(size.w-pad-colW):pad;
  let hs=Math.round(size.w*C.head_size);
  let bs=Math.round(size.w*C.body_size);
  const fs=Math.round(size.w*C.foot_size);
  const gap=Math.round(size.w*C.gap);

  const headline=mk(content.headline,C.head,hs,C.text);headline.lineHeight={unit:'PERCENT',value:100};
  const body=mk(content.body,C.body,bs,C.text);body.lineHeight={unit:'PERCENT',value:125};
  f.appendChild(headline);f.appendChild(body);ids.push(headline.id,body.id);
  headline.resize(colW,headline.height);
  body.resize(colW,body.height);

  // shrink the headline until it fits <=2 lines and the block clears the footer band
  const footBand=Math.round(size.h*0.18);
  const minHs=Math.round(size.w*0.03);
  const fits=()=>{
    headline.fontSize=hs;headline.resize(colW,headline.height);
    bs=Math.round(hs*(C.body_size/C.head_size));body.fontSize=bs;body.resize(colW,body.height);
    const total=headline.height+gap+body.height;
    return linesOf(headline,hs)<=2 && total<=(size.h-footBand);
  };
  while(hs>minHs && !fits()){hs-=2;}

  // vertically centre the headline + body block, on the copy side
  const total=headline.height+gap+body.height;
  let y=Math.round((size.h-total)/2);
  headline.x=colX;headline.y=y;
  body.x=colX;body.y=y+headline.height+gap;

  // footer pinned to the bottom of the copy side (terms line; falls back to attribution)
  const footTxt=String(content.footer_right||content.footer_left||'');
  if(footTxt){
    const footer=mk(footTxt,C.body,fs,C.footer,C.footer_op);
    f.appendChild(footer);ids.push(footer.id);
    footer.x=colX;footer.y=size.h-Math.round(pad*0.55)-footer.height;
  }
  return f;
};

if(CLEAR){ for(const n of figma.currentPage.children.slice()) n.remove(); }
if(HEADER){ const t=mk('Messaging creatives (WhatsApp / RCS / RPN)',C.body,48,'#111827');t.x=0;t.y=40;figma.currentPage.appendChild(t);ids.push(t.id); }

// Grid layout: columns = contents, rows = sizes. Only ONLY_SIZE is built in this
// call, so we build that one row for every content at the absolute row-Y it would
// occupy in the full grid.
const GAPX=160, GAPY=140, headerY=160;
const maxColW=Math.max.apply(null, SIZES.map(s=>s.w));
const rowY=[];let acc=headerY;for(let r=0;r<SIZES.length;r++){rowY.push(acc);acc+=SIZES[r].h+GAPY;}
const onlyIdx=SIZES.findIndex(s=>s.name===ONLY_SIZE);
const size=SIZES[onlyIdx];
for(const item of CONTENTS){
  const f=buildCreative(item, size, item.col*(maxColW+GAPX), rowY[onlyIdx]);
  ids.push(f.id);
}
figma.viewport.scrollAndZoomIntoView(figma.currentPage.children);
return { built: ids.length };
"""


def messaging_bundle() -> TemplateBundle:
    """The WhatsApp / RCS / RPN messaging template (full-bleed hero + scrim). Seeded
    by the messaging-template migration as a non-default built-in."""
    return TemplateBundle(
        brand=MESSAGING_BRAND,
        sizes=MESSAGING_SIZES,
        js_body=MESSAGING_JS_BODY,
        strips={},  # no brand strips — the design is a full-bleed photo
        footer_left=MESSAGING_FOOTER_LEFT,
        footer_right=MESSAGING_FOOTER_RIGHT,
        image_brief=MESSAGING_IMAGE_BRIEF,
        # WA (≈1.9:1), RCS/RPN (2:1) are all wide — a 16:9 source matches far better
        # than the default square, so the left-subject / right-copy layout survives.
        image_aspect="16:9",
    )


def build_figma_code(
    bundle: TemplateBundle, contents_batch: list[dict], size: dict, clear: bool, header: bool
) -> str:
    """Build the plugin code for one size across all contents, driven by a
    template bundle. Only this size's strip is embedded, keeping the payload under
    use_figma's 50k-char limit.

    LOGO_SVG is only used by the fallback (no-strip) path, so it is embedded only
    when this size has no strip — saving ~5k and keeping every payload under the
    limit."""
    strip = bundle.strips.get(size["name"], "")
    logo = "" if strip else _load_logo_svg()
    inject = (
        "const BRAND = " + json.dumps(bundle.brand) + ";\n"
        "const LOGO_SVG = " + json.dumps(logo) + ";\n"
        "const STRIP_SVG = " + json.dumps(strip) + ";\n"
        "const ONLY_SIZE = " + json.dumps(size["name"]) + ";\n"
        "const CONTENTS = " + json.dumps(contents_batch) + ";\n"
        "const SIZES = " + json.dumps(bundle.sizes) + ";\n"
        "const CLEAR = " + json.dumps(clear) + ";\n"
        "const HEADER = " + json.dumps(header) + ";\n"
    )
    return inject + bundle.js_body
