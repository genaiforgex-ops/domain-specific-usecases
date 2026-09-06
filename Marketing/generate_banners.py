#!/usr/bin/env python3
"""
GenAIForge on-brand static banner generator -> Figma (pure Python, no plugin).

WHAT THIS DOES
--------------
Builds on-brand GenAIForge creatives (ink bg, bronze/purple/teal dot ribbon,
GenAIForge logo vector, hero photo, Inter Bold headline + Inter Regular body,
bronze pill CTA, footer) across the 5 performance ad sizes, and pushes them
straight into a Figma file via the remote MCP (`use_figma`).

It cannot create frames through the read-only REST API, so it talks to
https://mcp.figma.com/mcp using the Claude Code OAuth token (PKCE login built in;
see do_login). The hero photo lives in Figma already (HERO_HASH), uploaded once.

CONTENT INJECTION (the part you drive dynamically)
--------------------------------------------------
Each creative is one `content` dict:

    {
        "headline":     "Start something new from just ₹10.",  # Inter Bold
        "body":         "Grow every month with a simple plan.",  # Inter Regular
        "cta":          "Buy Now",
        "image_hash":   HERO_HASH,            # a Figma imageHash (see upload_hero())
        "footer_left":  "Premium offers · limited time",
        "footer_right": "*T&Cs apply",
    }

Build your list of these (any length) and call render(contents). The template
enforces the layout budget: headline <=3 lines, body <=2 lines when the headline
takes 3 (mutual exclusion), auto-shrinking to fit. validate_contents() warns on
word/char overages.

USAGE
-----
    python3 generate_banners.py                 # render CONTENTS into FILE_KEY
    python3 generate_banners.py <fileKey|url>   # target another file
    python3 generate_banners.py --login         # re-authenticate
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import re
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #
FILE_KEY = "l21aQvndPCYEZBj0HZkpbF"

# Hero photo (gold coins) already uploaded to the Figma file. Re-upload with
# upload_hero() if you target a fresh file (image hashes are per-file).
HERO_HASH = "f06168b416e2ba00944ea3c7382f174f914d912d"

# Brand system — GenAIForge Marketing (ink + bronze).
BRAND = {
    "bg":      "#0B0C10",   # ink background
    "gold":    "#B8956C",   # bronze (primary)
    "purple":  "#6D17CE",   # secondary accent
    "teal":    "#1CBABA",   # sparkle accent
    "white":   "#FFFFFF",
    "grey":    "#F5F5F6",
    "cta_bg":  "#B8956C",   # bronze pill
    "cta_fg":  "#0B0C10",   # ink text on the bronze pill
    "dots":    ["#B8956C", "#6D17CE", "#1CBABA"],  # ribbon dots = bronze / purple / teal
    "head":    "Bold",      # Inter style for headlines
    "body":    "Regular",   # Inter style for body
    "logo_aspect": round(180 / 32, 4),  # GenAIForge horizontal wordmark W/H
    "hero_aspect": round(420 / 284, 4),  # hero photo W/H; update if you swap images
}

# GenAIForge logo wordmark — on-dark variant suits the ink background.
_LOGO_SVG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "backend", "assets", "genaiforge_logo_horizontal_ondark.svg")
with open(_LOGO_SVG_PATH, encoding="utf-8") as _fh:
    LOGO_SVG = _fh.read()

# The 5 ad formats. `pos` = where the hero photo sits.
SIZES = [
    {"name": "square",    "w": 1200, "h": 1200, "pos": "top"},
    {"name": "story",     "w": 1080, "h": 1920, "pos": "bottom"},
    {"name": "portrait",  "w": 1200, "h": 1500, "pos": "bottom"},
    {"name": "landscape", "w": 1920, "h": 1080, "pos": "left"},
    {"name": "link",      "w": 1200, "h": 628,  "pos": "left"},
]

FOOTER_LEFT = "Premium offers · limited time"
FOOTER_RIGHT = "*T&Cs apply"

# Layout budget rules.
HEAD_MAX_CHARS, HEAD_MAX_WORDS = 55, 9
BODY_MAX_CHARS, BODY_MAX_WORDS = 72, 12


def make_content(headline, body, cta, image_hash=HERO_HASH,
                 footer_left=FOOTER_LEFT, footer_right=FOOTER_RIGHT):
    return {"headline": headline, "body": body, "cta": cta,
            "image_hash": image_hash,
            "footer_left": footer_left, "footer_right": footer_right}


# Default content set — generic premium marketing copy. Replace/extend freely.
CONTENTS = [
    make_content("Start something new from just ₹10.",      "Grow every month with a simple plan.", "Buy Now"),
    make_content("A fresh beginning, made simple.",         "Build habits that last, starting small.", "Invest Now"),
    make_content("Secure what matters most.",               "Trusted, certified and easy to begin.", "Buy Now"),
    make_content("Your trusted savings, starting small.",   "Bring home peace of mind from just ₹10.", "Buy Now"),
    make_content("Build savings, one SIP at a time.",       "Start SIPs from just ₹10.", "Invest Now"),
    make_content("Build your family's future today.",       "Grow with SIPs and earn more over time.", "Invest Now"),
]


def validate_contents(contents):
    """Warn (don't fail) on copy that breaks the word/char budget."""
    warnings = []
    for i, c in enumerate(contents):
        h, b = c["headline"], c["body"]
        if len(h) > HEAD_MAX_CHARS:
            warnings.append(f"#{i} headline {len(h)} chars > {HEAD_MAX_CHARS}: {h!r}")
        if len(h.split()) > HEAD_MAX_WORDS:
            warnings.append(f"#{i} headline {len(h.split())} words > {HEAD_MAX_WORDS}: {h!r}")
        if len(b) > BODY_MAX_CHARS:
            warnings.append(f"#{i} body {len(b)} chars > {BODY_MAX_CHARS}: {b!r}")
        if len(b.split()) > BODY_MAX_WORDS:
            warnings.append(f"#{i} body {len(b.split())} words > {BODY_MAX_WORDS}: {b!r}")
    return warnings


# --------------------------------------------------------------------------- #
# Figma MCP plumbing
# --------------------------------------------------------------------------- #
OAUTH_PATH = os.path.expanduser("~/.config/figma_agent/oauth.json")
MCP_URL = "https://mcp.figma.com/mcp"
PROTOCOL_VERSION = "2025-06-18"

AS_METADATA_URL = "https://mcp.figma.com/.well-known/oauth-authorization-server"
OAUTH_SCOPE = "mcp:connect"
CALLBACK_PORT = 3030
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"
JSON_CT = "application/json"


def load_oauth():
    if not os.path.exists(OAUTH_PATH):
        return None
    with open(OAUTH_PATH) as fh:
        return json.load(fh)


def save_oauth(data: dict) -> None:
    os.makedirs(os.path.dirname(OAUTH_PATH), exist_ok=True)
    with open(OAUTH_PATH, "w") as fh:
        json.dump(data, fh, indent=2)


def _post(url: str, headers: dict, body, form: bool = False):
    data = urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=180)
        return resp.status, resp.headers, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode("utf-8", "replace")


def _extract_jsonrpc(raw: str, want_id):
    raw = raw.strip()
    msgs = []
    if raw[:1] in "{[":
        try:
            msgs.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    else:
        for block in re.split(r"\n\s*\n", raw):
            datas = [ln[5:].lstrip() for ln in block.splitlines() if ln.startswith("data:")]
            if datas:
                try:
                    msgs.append(json.loads("".join(datas)))
                except json.JSONDecodeError:
                    pass
    for m in msgs:
        if isinstance(m, dict) and m.get("id") == want_id:
            return m
    return msgs[-1] if msgs else None


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read().decode())


def auth_metadata() -> dict:
    return _get_json(AS_METADATA_URL)


def register_client(meta: dict) -> dict:
    status, _, text = _post(meta["registration_endpoint"],
                            {"Content-Type": JSON_CT, "Accept": JSON_CT},
                            {"redirect_uris": [REDIRECT_URI],
                             "token_endpoint_auth_method": "none",
                             "grant_types": ["authorization_code", "refresh_token"],
                             "response_types": ["code"],
                             "scope": OAUTH_SCOPE, "client_name": "Claude Code"})
    if status >= 400:
        sys.exit(f"Client registration failed HTTP {status}: {text[:500]}")
    return json.loads(text)


class _CodeCatcher(http.server.BaseHTTPRequestHandler):
    code = None
    state = None

    def do_GET(self):  # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CodeCatcher.code = (params.get("code") or [None])[0]
        _CodeCatcher.state = (params.get("state") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        msg = (b"<h2>Authenticated.</h2><p>You can close this tab.</p>"
               if _CodeCatcher.code else b"<h2>No code received.</h2>")
        self.wfile.write(b"<html><body style='font-family:sans-serif;padding:40px'>" + msg + b"</body></html>")

    def log_message(self, *args):
        pass


def do_login(existing=None) -> dict:
    meta = auth_metadata()
    client_info = (existing or {}).get("client_info") if existing else None
    if not client_info or not client_info.get("client_id"):
        client_info = register_client(meta)
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    authorize_url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode({
        "client_id": client_info["client_id"], "response_type": "code",
        "redirect_uri": REDIRECT_URI, "scope": OAUTH_SCOPE, "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    server = http.server.HTTPServer(("127.0.0.1", CALLBACK_PORT), _CodeCatcher)
    print("Opening browser to authenticate with Figma...")
    print(f"  If it doesn't open, visit:\n  {authorize_url}\n")
    webbrowser.open(authorize_url)
    threading.Thread(target=server.handle_request, daemon=True).start()
    import time
    for _ in range(300):
        if _CodeCatcher.code is not None:
            break
        time.sleep(1)
    server.server_close()
    if not _CodeCatcher.code:
        sys.exit("Timed out waiting for the OAuth callback.")
    if _CodeCatcher.state != state:
        sys.exit("OAuth state mismatch - aborting.")
    status, _, text = _post(meta["token_endpoint"],
                            {"Content-Type": "application/x-www-form-urlencoded", "Accept": JSON_CT},
                            {"grant_type": "authorization_code", "code": _CodeCatcher.code,
                             "redirect_uri": REDIRECT_URI, "client_id": client_info["client_id"],
                             "client_secret": client_info.get("client_secret", ""),
                             "code_verifier": verifier}, form=True)
    if status >= 400:
        sys.exit(f"Token exchange failed HTTP {status}: {text[:500]}")
    oauth = {"client_info": client_info, "tokens": json.loads(text)}
    save_oauth(oauth)
    print("Authenticated. Token saved to", OAUTH_PATH)
    return oauth


def _discover_token_endpoint():
    for url in (AS_METADATA_URL, "https://www.figma.com/.well-known/oauth-authorization-server"):
        try:
            meta = _get_json(url)
            if meta.get("token_endpoint"):
                return meta["token_endpoint"]
        except Exception:
            continue
    return None


def refresh_access_token(oauth: dict):
    te = _discover_token_endpoint()
    if not te:
        return None
    ci, tok = oauth["client_info"], oauth["tokens"]
    status, _, text = _post(te, {"Content-Type": "application/x-www-form-urlencoded", "Accept": JSON_CT},
                            {"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                             "client_id": ci["client_id"], "client_secret": ci.get("client_secret", "")},
                            form=True)
    if status != 200:
        return None
    new = json.loads(text)
    oauth["tokens"]["access_token"] = new["access_token"]
    if new.get("refresh_token"):
        oauth["tokens"]["refresh_token"] = new["refresh_token"]
    save_oauth(oauth)
    return new["access_token"]


class FigmaMCP:
    def __init__(self, token: str):
        self.token = token
        self.session_id = None
        self._id = 0

    def _headers(self):
        h = {"Authorization": f"Bearer {self.token}", "Content-Type": JSON_CT,
             "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": PROTOCOL_VERSION}
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _next_id(self):
        self._id += 1
        return self._id

    def initialize(self):
        rid = self._next_id()
        status, headers, text = _post(MCP_URL, self._headers(), {
            "jsonrpc": "2.0", "id": rid, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                       "clientInfo": {"name": "claude-code", "version": "1.0.0"}}})
        if status == 401:
            raise PermissionError("401 on initialize")
        sid = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        if status >= 400:
            raise RuntimeError(f"initialize failed HTTP {status}: {text[:500]}")
        _post(MCP_URL, self._headers(), {"jsonrpc": "2.0", "method": "notifications/initialized"})
        return _extract_jsonrpc(text, rid)

    def call_tool(self, name: str, arguments: dict):
        rid = self._next_id()
        status, _, text = _post(MCP_URL, self._headers(), {
            "jsonrpc": "2.0", "id": rid, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}})
        if status == 401:
            raise PermissionError("401 on tools/call")
        if status >= 400:
            raise RuntimeError(f"tools/call failed HTTP {status}: {text[:800]}")
        return _extract_jsonrpc(text, rid)


# --------------------------------------------------------------------------- #
# Figma Plugin-API template (one creative per content x size). BRAND / CONTENTS
# / SIZES are injected from Python; this body never hardcodes content.
# --------------------------------------------------------------------------- #
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
const dotSvg=(w,h,cf,ct)=>{const r=Math.max(3,Math.round(h*0.07)),gap=r*4.4;let c='';for(let y=gap*0.6;y<h-gap*0.3;y+=gap)for(let x=gap;x<w-gap*0.3;x+=gap){if(cf!=null&&x>cf&&x<ct)continue;const col=C.dots[(((x/gap)|0)+((y/gap)|0))%C.dots.length];c+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+r+'" fill="'+col+'"/>';}return '<svg width="'+w+'" height="'+h+'" xmlns="http://www.w3.org/2000/svg">'+c+'</svg>';};

// Official logo lockup + dot ribbon ("strips"). The ribbon dots flank the logo;
// the centre band of dots is cleared so the official vector reads cleanly.
const buildBandLogo=(f,bandX,bandW,bandY,bandH,logoCX)=>{
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
  let Hs=Math.round(colW*0.105);const minHs=Math.round(colW*0.05);
  let hL=2,bL=1,total=0,ctaH=0,gapHB=0,gapBC=0;
  const measure=()=>{
    headline.fontSize=Hs;headline.resize(colW,headline.height);hL=linesOf(headline,Hs);
    const bs=Math.round(Hs*0.44);body.fontSize=bs;body.resize(colW,body.height);bL=linesOf(body,bs);
    ctaH=Math.round(Hs*0.5*1.2)+2*Math.round(Hs*0.46);
    gapHB=Math.round(Hs*0.32);gapBC=Math.round(Hs*0.58);
    total=headline.height+gapHB+body.height+gapBC+ctaH;
  };
  measure();
  while(Hs>minHs && (total>availH || hL>3 || bL>(hL>=3?2:3))){Hs-=3;measure();}
  const cta=figma.createFrame();cta.layoutMode='HORIZONTAL';cta.primaryAxisSizingMode='AUTO';cta.counterAxisSizingMode='AUTO';
  cta.paddingLeft=cta.paddingRight=Math.round(Hs*0.95);cta.paddingTop=cta.paddingBottom=Math.round(Hs*0.46);
  cta.cornerRadius=Math.round(Hs*1.6);cta.fills=solid(C.cta_bg);
  const ctaT=mk(content.cta,C.head,Math.round(Hs*0.5),C.cta_fg);cta.appendChild(ctaT);f.appendChild(cta);ids.push(cta.id,ctaT.id);
  return {headline,body,cta,total,gapHB,gapBC,Hs,hL,bL};
};

const buildCreative=(content,size,ox,oy)=>{
  const left = size.pos==='left';
  const f=figma.createFrame();
  f.name='Performance / '+content.headline.slice(0,26)+' / '+size.name+' '+size.w+'x'+size.h;
  f.x=ox;f.y=oy;f.resize(size.w,size.h);f.fills=solid(C.bg);f.clipsContent=true;figma.currentPage.appendChild(f);
  const pad=Math.round(size.w*(left?0.038:0.06));
  const align = left?'LEFT':'CENTER';

  // footer
  const fs=Math.round(Math.min(size.w,size.h)*0.024);
  const fl=mk(content.footer_left,C.body,fs,C.white,0.85);f.appendChild(fl);ids.push(fl.id);
  const fr=mk(content.footer_right,C.body,fs,C.white,0.85);f.appendChild(fr);ids.push(fr.id);
  const footerTop=size.h-Math.round(pad*0.7)-Math.max(fl.height,fr.height);
  const footGap=Math.round(pad*0.7), gapHT=Math.round(pad*0.85);

  // band + logo region
  const colX = left ? Math.round(size.w*0.5)+pad : pad;
  const colW = left ? size.w-colX-pad : size.w-pad*2;
  const bandH=Math.round(Math.min(size.w,size.h)*(left?0.075:0.08));
  const bandY=Math.round(pad*0.5);
  const bandX = left ? Math.round(size.w*0.5) : 0;
  const bandW = left ? size.w-bandX : size.w;
  const logoCX = bandX+bandW/2;
  const bandBottom=buildBandLogo(f,bandX,bandW,bandY,bandH,logoCX);

  fl.x = left?colX:pad; fl.y=footerTop;
  fr.x = size.w-pad-fr.width; fr.y=footerTop;

  const heroR=Math.round(size.w*0.025);
  const newHero=(w,h,x,y)=>{const r=figma.createRectangle();r.resize(w,h);r.cornerRadius=heroR;r.fills=[{type:'IMAGE',scaleMode:'FILL',imageHash:content.image_hash}];f.appendChild(r);ids.push(r.id);r.x=x;r.y=y;return r;};

  if(size.pos==='top'){
    const heroTop=bandBottom+Math.round(pad*0.7);
    const minH=Math.round(size.h*0.30),maxH=Math.round(size.h*0.42);
    const textBottom=footerTop-footGap;
    const availText=textBottom-(heroTop+minH+gapHT);
    const blk=fitBlock(f,colW,availText,content,align);
    const heroH=cl(textBottom-blk.total-gapHT-heroTop,minH,maxH);
    newHero(colW,heroH,pad,heroTop);
    const contentTop=heroTop+heroH+gapHT, availH=textBottom-contentTop;
    let y=contentTop+Math.max(0,Math.round((availH-blk.total)/2));
    blk.headline.x=pad;blk.headline.y=y;y+=blk.headline.height+blk.gapHB;
    blk.body.x=pad;blk.body.y=y;y+=blk.body.height+blk.gapBC;
    blk.cta.x=Math.round((size.w-blk.cta.width)/2);blk.cta.y=y;
  } else if(size.pos==='bottom'){
    const textTop=bandBottom+gapHT;
    const minH=Math.round(size.h*0.34),maxH=Math.round(size.h*0.46);
    const heroBottom=footerTop-footGap;
    const availText=(heroBottom-minH-gapHT)-textTop;
    const blk=fitBlock(f,colW,availText,content,align);
    let y=textTop;
    blk.headline.x=pad;blk.headline.y=y;y+=blk.headline.height+blk.gapHB;
    blk.body.x=pad;blk.body.y=y;y+=blk.body.height+blk.gapBC;
    blk.cta.x=Math.round((size.w-blk.cta.width)/2);blk.cta.y=y;
    const heroTop=y+blk.cta.height+gapHT;
    const heroH=cl(heroBottom-heroTop,minH,maxH);
    newHero(colW,heroH,pad,heroTop);
  } else { // left: hero sized to photo aspect, vertically centered (no awkward crop)
    const regTop=Math.round(pad*0.5);
    const regH=(footerTop-footGap)-regTop;
    const regW=Math.round(size.w*0.5)-pad-Math.round(pad*0.4);
    const ar=C.hero_aspect||1.48;
    let hw=regW, hh=Math.round(hw/ar);
    if(hh>regH){ hh=regH; hw=Math.round(hh*ar); }
    newHero(hw,hh,pad,regTop+Math.round((regH-hh)/2));
    const textTop=bandBottom+gapHT, textBottom=footerTop-footGap;
    const blk=fitBlock(f,colW,textBottom-textTop,content,align);
    let y=textTop+Math.max(0,Math.round(((textBottom-textTop)-blk.total)/2));
    blk.headline.x=colX;blk.headline.y=y;y+=blk.headline.height+blk.gapHB;
    blk.body.x=colX;blk.body.y=y;y+=blk.body.height+blk.gapBC;
    blk.cta.x=colX;blk.cta.y=y;
  }
  return f;
};

if(CLEAR){ for(const n of figma.currentPage.children.slice()) n.remove(); }
if(HEADER){ const t=mk('Performance creatives (on-brand template)',C.body,48,'#111827');t.x=0;t.y=40;figma.currentPage.appendChild(t);ids.push(t.id); }

const GAPX=160, GAPY=140, headerY=160;
const maxColW=Math.max.apply(null, SIZES.map(s=>s.w));
const rowY=[];let acc=headerY;for(let r=0;r<SIZES.length;r++){rowY.push(acc);acc+=SIZES[r].h+GAPY;}
for(const item of CONTENTS){
  for(let r=0;r<SIZES.length;r++){
    const f=buildCreative(item, SIZES[r], item.col*(maxColW+GAPX), rowY[r]);
    ids.push(f.id);
  }
}
figma.viewport.scrollAndZoomIntoView(figma.currentPage.children);
return { built: ids.length };
"""


def build_figma_code(contents_batch, clear: bool, header: bool) -> str:
    inject = (
        "const BRAND = "    + json.dumps(BRAND)           + ";\n"
        "const LOGO_SVG = " + json.dumps(LOGO_SVG)        + ";\n"
        "const CONTENTS = " + json.dumps(contents_batch)  + ";\n"
        "const SIZES = "    + json.dumps(SIZES)           + ";\n"
        "const CLEAR = "    + json.dumps(clear)           + ";\n"
        "const HEADER = "   + json.dumps(header)          + ";\n"
    )
    return inject + FIGMA_JS_BODY


def parse_file_key(arg: str) -> str:
    m = re.search(r"figma\.com/(?:design|file)/([A-Za-z0-9]+)", arg)
    return m.group(1) if m else arg


def _connect(oauth):
    token = oauth["tokens"]["access_token"]
    client = FigmaMCP(token)
    try:
        client.initialize()
        return client, oauth
    except PermissionError:
        print("Token rejected (401). Trying to refresh...")
        token = refresh_access_token(oauth)
        if not token:
            print("Refresh failed. Starting a fresh OAuth login...")
            oauth = do_login(oauth)
            token = oauth["tokens"]["access_token"]
        client = FigmaMCP(token)
        client.initialize()
        return client, oauth


def render(contents, file_key=FILE_KEY, oauth=None):
    """Push `contents` (list of content dicts) into Figma, one column per content."""
    for w in validate_contents(contents):
        print("  budget warning:", w)
    if oauth is None:
        oauth = load_oauth() or do_login(None)
    client, oauth = _connect(oauth)
    total = 0
    for i, c in enumerate(contents):
        batch = [dict(c, col=i)]
        args = {"fileKey": file_key,
                "code": build_figma_code(batch, clear=(i == 0), header=(i == 0)),
                "description": f"Performance creative '{c['headline'][:40]}' x {len(SIZES)} sizes.",
                "skillNames": "resource:figma-use"}
        result = client.call_tool("use_figma", args)
        if not result or "error" in result:
            sys.exit(f"Figma MCP error on content {i}: {json.dumps(result, indent=2) if result else 'no response'}")
        total += len(SIZES)
        print(f"  [{i+1}/{len(contents)}] {c['headline'][:42]!r} x {len(SIZES)} sizes")
    print("Done.")
    print(f"  File: https://www.figma.com/design/{file_key}")
    print(f"  Banners pushed: {total} ({len(contents)} copies x {len(SIZES)} sizes)")


def main():
    argv = [a for a in sys.argv[1:] if a != "--login"]
    force_login = "--login" in sys.argv
    file_key = parse_file_key(argv[0]) if argv else FILE_KEY
    oauth = load_oauth()
    if oauth is None or force_login:
        print("Not authenticated - starting OAuth login..." if oauth is None else "Forcing re-login...")
        oauth = do_login(oauth)
    render(CONTENTS, file_key=file_key, oauth=oauth)


if __name__ == "__main__":
    main()
