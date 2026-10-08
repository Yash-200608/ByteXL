import html

STATES = ("idle", "listening", "thinking", "searching", "speaking", "explaining", "celebrating", "error")
BUBBLE = {
    "idle": "Ready when you are!",
    "listening": "I'm listening…",
    "thinking": "Let me think…",
    "searching": "Checking your records…",
    "speaking": "Here's what I found.",
    "explaining": "Here's what your records say.",
    "celebrating": "Got it! I'm on it.",
    "error": "Oops — let's try that again.",
}
STATE_LABEL = {"idle": "Waiting", "listening": "Listening", "thinking": "Thinking", "searching": "Searching", "speaking": "Speaking",
               "explaining": "Explaining", "celebrating": "Celebrating", "error": "Confused"}
SLOTS = (("idle", "listening"), ("thinking", "searching"), ("speaking", "explaining", "celebrating", "error"))
LISTEN_HAS = 'body:has([data-testid="stChatInputMicButton"][aria-label="Stop recording"])'
ASSETS = "app/static/perry"
HERO = f"{ASSETS}/perry_idle.png"
HEAD = f"{ASSETS}/perry_head.png"

FX = """<svg class="pv-fx" viewBox="0 0 100 158" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
<g class="fx fx-listen" fill="none" stroke="#2EE6D6" stroke-width=".8">
<circle class="ring r1" cx="50" cy="30" r="30"/><circle class="ring r2" cx="50" cy="30" r="30"/><circle class="ring r3" cx="50" cy="30" r="30"/></g>
<g class="fx fx-think" fill="#BFFBF4" font-family="PerryHand, cursive" font-weight="700">
<text class="q q1" x="84" y="8" font-size="14">?</text><text class="q q2" x="95" y="0" font-size="9">?</text>
<circle class="d d1" cx="88" cy="20" r="1.4"/><circle class="d d2" cx="93" cy="17" r="1.4"/><circle class="d d3" cx="98" cy="14" r="1.4"/></g>
<g class="fx fx-search"><g class="glass"><circle cx="92" cy="62" r="7" fill="rgba(46,230,214,.18)" stroke="#2EE6D6" stroke-width="1.4"/>
<path d="M97 67 L103 73" stroke="#2EE6D6" stroke-width="2" stroke-linecap="round"/></g>
<rect x="82" y="76" width="18" height="23" rx="2" fill="rgba(232,251,248,.9)"/>
<path d="M85 82h12M85 87h12M85 92h8" stroke="#0E6F6A" stroke-width="1"/></g>
<g class="fx fx-speak" fill="none" stroke="#2EE6D6" stroke-width="1.4" stroke-linecap="round">
<path class="w w1" d="M101 30 q3 5 0 10"/><path class="w w2" d="M105 26 q5 9 0 18"/><path class="w w3" d="M109 22 q7 13 0 26"/></g>
<g class="fx fx-explain"><rect x="84" y="44" width="26" height="20" rx="2.5" fill="rgba(46,230,214,.14)" stroke="#2EE6D6" stroke-width=".8"/>
<path class="bar" d="M89 60v-5M94 60v-8M99 60v-6M104 60v-11" stroke="#7DF9EC" stroke-width="2.2"/></g>
<g class="fx fx-party"><rect class="cf c1" x="12" y="6" width="3" height="5" fill="#FFC857"/><rect class="cf c2" x="84" y="2" width="3" height="5" fill="#2EE6D6"/>
<rect class="cf c3" x="96" y="20" width="3" height="5" fill="#FF8FB8"/><rect class="cf c4" x="4" y="26" width="3" height="5" fill="#B79CFF"/>
<rect class="cf c5" x="52" y="-4" width="3" height="5" fill="#9FF0D9"/></g>
<g class="fx fx-error"><circle cx="90" cy="10" r="7" fill="#F59E0B"/>
<text x="90" y="14.5" text-anchor="middle" font-size="11" font-weight="800" fill="#1A0F00">!</text></g>
</svg>"""


HOLO = """<div class="pv-holo pv-holo-l" aria-hidden="true"><div class="ht">VITAL INSIGHTS</div>
<svg viewBox="0 0 120 34"><path d="M12 10 a6 6 0 0 1 10 -3 a6 6 0 0 1 10 3 c0 7 -10 13 -10 13 c0 0 -10 -6 -10 -13z" fill="none" stroke="#7DF9EC" stroke-width="1.6"/>
<path class="ecg" d="M38 18 h16 l4 -10 l5 18 l5 -14 l3 6 h40" fill="none" stroke="#2EE6D6" stroke-width="1.6"/></svg>
<ul><li>♡ Heart Health</li><li>▤ Blood Tests</li><li>◇ Medications</li><li>◷ Your Timeline</li></ul></div>
<div class="pv-holo pv-holo-r" aria-hidden="true"><svg viewBox="0 0 80 120">
<circle cx="40" cy="14" r="7" fill="none" stroke="#7DF9EC" stroke-width="1.2"/>
<path d="M40 21 v40 M40 28 l-16 20 M40 28 l16 20 M40 61 l-10 34 M40 61 l10 34 M32 34 h16 M31 40 h18 M32 46 h16 M33 52 h14" fill="none" stroke="#7DF9EC" stroke-width="1.2"/>
<path d="M6 112 v-10 M12 112 v-16 M18 112 v-7 M24 112 v-13" stroke="#2EE6D6" stroke-width="3"/>
<path class="ecg" d="M46 106 h8 l3 -6 l3 10 l3 -4 h12" fill="none" stroke="#2EE6D6" stroke-width="1.2"/></svg></div>"""


def _platform() -> str:
    return ('<div class="pv-platform" aria-hidden="true"><div class="pv-base"></div><div class="pv-band"><i></i><i></i><i></i><i></i><i></i></div>'
            '<div class="pv-disc"></div><div class="pv-ring"></div><div class="pv-pulse"></div></div>')


def perry_avatar(state: str = "idle", size: int = 340, uid: str = "main", live: bool = False, platform: bool = True) -> str:
    state = state if state in STATES else "idle"
    return (f'<div class="pv{" pv-live" if live else ""}" data-state="{state}" id="pv-{uid}" style="width:{size}px" '
            f'role="img" aria-label="PERRY, {state}"><div class="pv-float"><img class="pv-char" src="{HERO}" alt="" '
            f'draggable="false">{" ".join(FX.split())}</div>{_platform() if platform else ""}</div>')


def perry_head(size: int = 44, uid: str = "head", state: str = "idle") -> str:
    return (f'<img class="pv-head" data-state="{state}" src="{HEAD}" width="{size}" height="{size}" alt="PERRY" '
            f'style="width:{size}px;height:{size}px">')


def head_data_uri(size: int = 40) -> str:
    return HEAD


def bubble(state: str, live: bool = True) -> str:
    spans = "".join(f'<span class="st st-{s}">{html.escape(t)}</span>' for s, t in BUBBLE.items())
    return f'<div class="pv-bubble{" pv-live" if live else ""}" data-state="{state}">{spans}</div>'


def state_cards(current: str) -> str:
    cards = []
    for n, slot in enumerate(SLOTS):
        shown = current if current in slot else slot[0]
        imgs = "".join(f'<img class="v v-{s}" src="{ASSETS}/state_{s}.png" alt="" draggable="false">' for s in slot)
        labels = "".join(f'<span class="v v-{s}">{STATE_LABEL[s]}</span>' for s in slot)
        cards.append(f'<div class="pv-card slot{n}{" on" if current in slot else ""}" data-show="{shown}"><div class="pv-card-img">{imgs}</div>'
                     f'<div class="pv-card-label">{labels}</div></div>')
    return f'<div class="pv-cards pv-live" data-state="{current}">{"".join(cards)}</div>'


def mascot(state: str = "idle", size: int = 160) -> str:
    return perry_avatar(state, size, uid=f"m{size}{state}", platform=size > 80)


STATE_RULES = {
    "idle": {"show": [], "rules": []},
    "listening": {"show": [".fx-listen"], "rules": [
        (".pv-char", "animation: pvBreathe 3.4s ease-in-out infinite, pvLean 1.4s ease-in-out infinite;"),
        (".pv-pulse", "animation: pvPulse .9s ease-out infinite;"),
        (".pv-ring", "box-shadow: 0 0 26px 6px rgba(46,230,214,.75), inset 0 0 16px rgba(46,230,214,.6);")]},
    "thinking": {"show": [".fx-think"], "rules": [
        (".pv-char", "animation: pvBreathe 3.4s ease-in-out infinite, pvTilt 2.4s ease-in-out infinite;")]},
    "searching": {"show": [".fx-search"], "rules": [
        (".pv-char", "animation: pvBreathe 3.4s ease-in-out infinite, pvSway 1.6s ease-in-out infinite;"),
        (".pv-pulse", "animation: pvPulse .8s ease-out infinite;")]},
    "speaking": {"show": [".fx-speak"], "rules": [
        (".pv-char", "animation: pvTalkBob .42s ease-in-out infinite alternate;"),
        (".pv-ring", "box-shadow: 0 0 22px 4px rgba(46,230,214,.6), inset 0 0 14px rgba(46,230,214,.5);")]},
    "explaining": {"show": [".fx-explain"], "rules": [
        (".pv-char", "animation: pvBreathe 3.4s ease-in-out infinite, pvSway 3s ease-in-out infinite;")]},
    "celebrating": {"show": [".fx-party"], "rules": [
        (".pv-char", "animation: pvHop .7s ease-in-out infinite;"),
        (".pv-pulse", "animation: pvPulse 1.1s ease-out infinite;")]},
    "error": {"show": [".fx-error"], "rules": [
        (".pv-ring", "border-color: #F59E0B; box-shadow: 0 0 20px 3px rgba(245,158,11,.55), inset 0 0 12px rgba(245,158,11,.4);"),
        (".pv-pulse", "border-color: #F59E0B;"), (".pv-char", "filter: saturate(.6) drop-shadow(0 18px 24px rgba(0,0,0,.5));")]},
}
LIVE_OVERRIDES = {
    "listening": ["body.perry-listening", LISTEN_HAS],
    "speaking": ["body.perry-speaking"],
}


def card_css() -> str:
    out = [".pv-cards .v {display:none;}"]
    for n, slot in enumerate(SLOTS):
        for st_ in slot:
            out.append(f'.pv-cards .slot{n}[data-show="{st_}"] .v-{st_} {{display:block;}}')
    for st_, prefixes in LIVE_OVERRIDES.items():
        n = next(i for i, slot in enumerate(SLOTS) if st_ in slot)
        for prefix in prefixes:
            out.append(f"{prefix} .pv-cards.pv-live .slot{n} .v {{display:none;}}")
            out.append(f"{prefix} .pv-cards.pv-live .slot{n} .v-{st_} {{display:block;}}")
            out.append(f"{prefix} .pv-cards.pv-live .pv-card {{opacity:.72; border-color:rgba(46,230,214,.16); box-shadow:none; transform:none;}}")
            out.append(f"{prefix} .pv-cards.pv-live .slot{n} {{opacity:1; border-color:var(--p-cyan); box-shadow:0 0 20px rgba(46,230,214,.3); transform:translateY(-3px);}}")
    return "\n".join(out)


def state_css() -> str:
    out = [".pv .fx {display:none;}", ".pv-bubble .st {display:none;}", card_css()]
    for state, spec in STATE_RULES.items():
        scopes = [f'.pv[data-state="{state}"]']
        bubble_scopes = [f'.pv-bubble[data-state="{state}"]']
        for prefix in LIVE_OVERRIDES.get(state, []):
            out.append(f"{prefix} .pv-live .fx {{display:none;}}")
            out.append(f"{prefix} .pv-bubble.pv-live .st {{display:none;}}")
            scopes.append(f"{prefix} .pv-live")
            bubble_scopes.append(f"{prefix} .pv-bubble.pv-live")
        if spec["show"]:
            out.append(", ".join(f"{s} {sel}" for s in scopes for sel in spec["show"]) + " {display:inline;}")
        out.append(", ".join(f"{s} .st-{state}" for s in bubble_scopes) + " {display:inline;}")
        for sel, decl in spec["rules"]:
            out.append(", ".join(f"{s} {sel}" for s in scopes) + f" {{{decl}}}")
    return "\n".join(out)


AVATAR_CSS = """
@keyframes pvFloat {0%,100%{transform:translateY(0)} 50%{transform:translateY(-8px)}}
@keyframes pvBreathe {0%,100%{transform:scale(1,1)} 50%{transform:scale(1.012,1.022)}}
@keyframes pvLean {0%,100%{rotate:-1.5deg; translate:0 -2px} 50%{rotate:-3deg; translate:-3px -5px}}
@keyframes pvTilt {0%,100%{rotate:0deg} 50%{rotate:2.5deg}}
@keyframes pvSway {0%,100%{rotate:-1.5deg} 50%{rotate:1.5deg}}
@keyframes pvTalkBob {0%{transform:translateY(0) scale(1,1)} 100%{transform:translateY(-4px) scale(1.01,1.025)}}
@keyframes pvPulse {0%{transform:scale(.92); opacity:.9} 100%{transform:scale(1.22); opacity:0}}
@keyframes pvSpin {0%{rotate:0deg} 100%{rotate:360deg}}
@keyframes pvRing {0%{transform:scale(.6); opacity:.9} 100%{transform:scale(1.5); opacity:0}}
@keyframes pvBob {0%,100%{transform:translateY(0); opacity:.6} 50%{transform:translateY(-3px); opacity:1}}
@keyframes pvWave {0%,100%{opacity:.15} 50%{opacity:1}}
@keyframes pvHop {0%,100%{transform:translateY(0) scale(1,1)} 40%{transform:translateY(-12px) scale(.99,1.02)} 80%{transform:translateY(0) scale(1.02,.98)}}
@keyframes pvFall {0%{transform:translateY(-6px) rotate(0); opacity:0} 20%{opacity:1} 100%{transform:translateY(40px) rotate(220deg); opacity:0}}
@keyframes pvBar {0%,100%{transform:scaleY(.6)} 50%{transform:scaleY(1.1)}}
@keyframes pvScan {0%,100%{transform:translate(-14px,4px)} 50%{transform:translate(0,0)}}
.pv {position:relative; max-width:100%; margin:0 auto; display:flex; flex-direction:column; align-items:center; user-select:none;}
.pv-float {position:relative; width:74%; z-index:2; animation: pvFloat 3.6s ease-in-out infinite;}
.pv-char {display:block; width:100%; height:auto; transform-origin:50% 100%; animation: pvBreathe 3.4s ease-in-out infinite;
  filter: drop-shadow(0 18px 24px rgba(0,0,0,.5)) drop-shadow(0 0 18px rgba(46,230,214,.12));}
.pv-fx {position:absolute; inset:0; width:100%; height:100%; overflow:visible; pointer-events:none;}
.pv-fx * {transform-box: fill-box; transform-origin: 50% 50%;}
.fx-listen .ring {animation: pvRing 1.8s ease-out infinite;}
.fx-listen .r2 {animation-delay:.6s;} .fx-listen .r3 {animation-delay:1.2s;}
.fx-think .q, .fx-think .d {animation: pvBob 1.4s ease-in-out infinite;}
.fx-think .q2 {animation-delay:.3s;} .fx-think .d2 {animation-delay:.2s;} .fx-think .d3 {animation-delay:.4s;}
.fx-search .glass {animation: pvScan 1.4s ease-in-out infinite;}
.fx-party .cf {animation: pvFall 1.6s linear infinite;} .fx-party .c2 {animation-delay:.3s;} .fx-party .c3 {animation-delay:.7s;}
.fx-party .c4 {animation-delay:1s;} .fx-party .c5 {animation-delay:1.3s;}
.fx-explain .bar {transform-origin: 50% 100%; animation: pvBar 1.4s ease-in-out infinite;}
.fx-speak .w {animation: pvWave 1s ease-in-out infinite;}
.fx-speak .w2 {animation-delay:.18s;} .fx-speak .w3 {animation-delay:.36s;}
.pv-platform {position:relative; width:100%; aspect-ratio: 3.3 / 1; margin-top:-13%; z-index:1;}
.pv-base {position:absolute; left:2%; right:2%; top:34%; bottom:0; border-radius:50% / 34%;
  background: linear-gradient(180deg, #0F2E33, #071518 70%); box-shadow: 0 18px 34px rgba(0,0,0,.65), 0 0 30px rgba(46,230,214,.12);}
.pv-band {position:absolute; left:6%; right:6%; top:44%; height:22%; display:flex; justify-content:space-around; align-items:center;}
.pv-band i {width:9%; height:5px; border-radius:3px; background:#2EE6D6; box-shadow:0 0 10px 2px rgba(46,230,214,.75); opacity:.85;}
.pv-band i:nth-child(1), .pv-band i:nth-child(5) {width:5%; opacity:.45;}
.pv-disc {position:absolute; left:8%; right:8%; top:0; height:52%; border-radius:50%;
  background: radial-gradient(ellipse at 50% 42%, #2E5559 0%, #183A3F 40%, #0C2226 70%, #071518 100%);
  box-shadow: inset 0 -5px 12px rgba(0,0,0,.6), inset 0 3px 8px rgba(255,255,255,.08);}
.pv-ring {position:absolute; left:11%; right:11%; top:5%; height:42%; border-radius:50%; border:2px solid #2EE6D6;
  box-shadow: 0 0 16px 2px rgba(46,230,214,.55), inset 0 0 12px rgba(46,230,214,.45); transition: box-shadow .4s, border-color .4s;}
.pv-ring::after {content:""; position:absolute; left:50%; top:-3px; width:22%; height:5px; margin-left:-11%; border-radius:50%;
  background: radial-gradient(ellipse, #BFFFFA, transparent 70%);}
.pv-pulse {position:absolute; left:11%; right:11%; top:5%; height:42%; border-radius:50%; border:2px solid #2EE6D6; animation: pvPulse 2.8s ease-out infinite;}
.pv-holo {position:absolute; z-index:0; padding:10px 12px; border-radius:12px; color:#BFFBF4; font-size:.68rem; letter-spacing:.02em;
  background: linear-gradient(160deg, rgba(46,230,214,.16), rgba(46,230,214,.04)); border:1px solid rgba(46,230,214,.45);
  box-shadow: 0 0 24px rgba(46,230,214,.18), inset 0 0 20px rgba(46,230,214,.08); backdrop-filter: blur(3px);
  animation: pvHolo 5s ease-in-out infinite;}
.pv-holo-l {left:-4%; top:22%; width:34%; transform: perspective(500px) rotateY(24deg);}
.pv-holo-r {right:-6%; top:30%; width:26%; transform: perspective(500px) rotateY(-24deg); animation-delay:-2.5s;}
.pv-holo .ht {font-weight:800; font-size:.72rem; letter-spacing:.08em; color:#7DF9EC; margin-bottom:4px;}
.pv-holo ul {list-style:none; margin:4px 0 0; padding:0;} .pv-holo li {margin:3px 0; opacity:.9;}
.pv-holo svg {width:100%; height:auto; display:block;}
.pv-holo .ecg {stroke-dasharray: 140; animation: pvEcg 2.6s linear infinite;}
@keyframes pvHolo {0%,100%{opacity:.78} 50%{opacity:.98}}
@keyframes pvEcg {0%{stroke-dashoffset:140} 100%{stroke-dashoffset:0}}
.pv-head {border-radius:50%; object-fit:cover; display:block;}
@media (prefers-reduced-motion: reduce) {.pv *, .pv, .pv-fx * {animation: none !important; transition: none !important;}}
"""


def avatar_css() -> str:
    return AVATAR_CSS + state_css()
