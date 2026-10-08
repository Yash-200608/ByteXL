def mascot(state: str = "idle", size: int = 160) -> str:
    mouth = {
        "idle": '<path d="M86 118 Q100 130 114 118" stroke="#0b3b44" stroke-width="4" fill="none" stroke-linecap="round"/>',
        "thinking": '<ellipse cx="100" cy="121" rx="6" ry="5" fill="#0b3b44"/>',
        "happy": '<path d="M84 114 Q100 134 116 114 Z" fill="#0b3b44"/><path d="M92 122 Q100 128 108 122" fill="#f472b6"/>',
        "error": '<path d="M88 123 Q100 116 112 123" stroke="#0b3b44" stroke-width="4" fill="none" stroke-linecap="round"/>',
    }.get(state, "")
    brows = ('<path d="M66 72 L84 78" stroke="#0b3b44" stroke-width="4" stroke-linecap="round"/>'
             '<path d="M134 72 L116 78" stroke="#0b3b44" stroke-width="4" stroke-linecap="round"/>') if state == "error" else ""
    svg = f"""
<svg class="perry-svg perry-{state}" width="{size}" height="{size}" viewBox="0 0 200 200" role="img" aria-label="PERRY">
  <defs>
    <linearGradient id="pbody-{state}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#2dd4bf"/><stop offset="1" stop-color="#0e7490"/>
    </linearGradient>
    <radialGradient id="pglow-{state}"><stop offset="0" stop-color="#fef08a"/><stop offset="1" stop-color="#f59e0b" stop-opacity="0"/></radialGradient>
  </defs>
  <ellipse class="perry-shadow" cx="100" cy="188" rx="46" ry="7" fill="#000" opacity="0.18"/>
  <g class="perry-float">
    <line x1="100" y1="34" x2="100" y2="16" stroke="#0e7490" stroke-width="4" stroke-linecap="round"/>
    <circle class="perry-glow" cx="100" cy="12" r="13" fill="url(#pglow-{state})"/>
    <g class="perry-tip"><rect x="96.5" y="5" width="7" height="14" rx="2" fill="#fff"/><rect x="93" y="8.5" width="14" height="7" rx="2" fill="#fff"/></g>
    <path d="M100 32 C150 32 168 70 168 112 C168 156 140 180 100 180 C60 180 32 156 32 112 C32 70 50 32 100 32 Z" fill="url(#pbody-{state})"/>
    <ellipse cx="100" cy="146" rx="40" ry="26" fill="#ccfbf1" opacity="0.9"/>
    <path class="perry-ecg" d="M68 146 L84 146 L90 134 L98 158 L105 140 L110 146 L132 146" stroke="#0d9488" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
    <g class="perry-arm-l"><path d="M36 118 Q16 112 14 96" stroke="#14b8a6" stroke-width="11" fill="none" stroke-linecap="round"/></g>
    <g class="perry-arm-r"><path d="M164 118 Q184 112 186 96" stroke="#14b8a6" stroke-width="11" fill="none" stroke-linecap="round"/></g>
    <g class="perry-eyes">
      <ellipse cx="78" cy="90" rx="17" ry="19" fill="#fff"/><ellipse cx="122" cy="90" rx="17" ry="19" fill="#fff"/>
      <g class="perry-pupils"><circle cx="80" cy="93" r="8.5" fill="#0b3b44"/><circle cx="124" cy="93" r="8.5" fill="#0b3b44"/>
      <circle cx="83" cy="89" r="3" fill="#fff"/><circle cx="127" cy="89" r="3" fill="#fff"/></g>
    </g>
    {brows}
    <ellipse cx="62" cy="112" rx="8" ry="5" fill="#f9a8d4" opacity="0.7"/><ellipse cx="138" cy="112" rx="8" ry="5" fill="#f9a8d4" opacity="0.7"/>
    {mouth}
  </g>
</svg>"""
    return " ".join(line.strip() for line in svg.splitlines() if line.strip())


CSS = """
<style>
@keyframes perryFloat {0%,100%{transform:translateY(0)} 50%{transform:translateY(-6px)}}
@keyframes perryBlink {0%,92%,100%{transform:scaleY(1)} 95%{transform:scaleY(0.08)}}
@keyframes perryWave {0%,100%{transform:rotate(0)} 50%{transform:rotate(-16deg)}}
@keyframes perryLook {0%,100%{transform:translateX(-5px)} 50%{transform:translateX(5px)}}
@keyframes perryPulse {0%,100%{opacity:.45; transform:scale(.9)} 50%{opacity:1; transform:scale(1.15)}}
@keyframes perryEcg {0%{stroke-dashoffset:120} 100%{stroke-dashoffset:0}}
@keyframes perryDots {0%,80%,100%{opacity:.25; transform:translateY(0)} 40%{opacity:1; transform:translateY(-4px)}}
@keyframes perryIn {from{opacity:0; transform:translateY(8px)} to{opacity:1; transform:none}}
.perry-svg {overflow:visible; display:block; margin:0 auto;}
.perry-float {animation: perryFloat 3.2s ease-in-out infinite; transform-origin:100px 110px;}
.perry-eyes {animation: perryBlink 5s infinite; transform-origin:100px 90px;}
.perry-arm-r {animation: perryWave 2.6s ease-in-out infinite; transform-origin:164px 118px;}
.perry-glow {animation: perryPulse 2.4s ease-in-out infinite; transform-origin:100px 12px;}
.perry-ecg {stroke-dasharray:120; animation: perryEcg 2.8s linear infinite;}
.perry-thinking .perry-pupils {animation: perryLook 1.1s ease-in-out infinite;}
.perry-thinking .perry-glow {animation-duration: .8s;}
.perry-thinking .perry-arm-r {animation:none;}
.perry-error .perry-float {filter: saturate(.55);}
.perry-error .perry-arm-r, .perry-error .perry-glow {animation:none;}

[data-testid="stMainBlockContainer"] {max-width: 900px; padding-top: 2.6rem !important;}
.perry-hero {text-align:center; padding: 8px 0 4px; animation: perryIn .5s ease-out;}
.perry-name {font-size: 3.1rem; font-weight: 900; letter-spacing: .14em; margin: 4px 0 0;
  background: linear-gradient(90deg,#14b8a6,#0ea5e9,#6366f1); -webkit-background-clip:text; background-clip:text; color: transparent;}
.perry-tag {opacity:.7; font-size:1rem; margin-top:-2px;}
.perry-say {display:inline-block; margin-top:14px; padding:10px 18px; border-radius:18px; font-size:1.08rem;
  background: rgba(20,184,166,.12); border:1px solid rgba(20,184,166,.35);}
.perry-bar {display:flex; align-items:center; gap:12px; padding:6px 4px 12px; border-bottom:1px solid rgba(128,128,128,.18); margin-bottom:10px;}
.perry-bar .perry-mini-name {font-weight:900; letter-spacing:.12em; font-size:1.25rem;
  background: linear-gradient(90deg,#14b8a6,#0ea5e9); -webkit-background-clip:text; background-clip:text; color:transparent;}
.perry-status {font-size:.86rem; opacity:.75;}
.perry-dot {display:inline-block; width:8px; height:8px; border-radius:50%; background:#22c55e; margin-right:6px; box-shadow:0 0 0 3px rgba(34,197,94,.2);}
.perry-scope {display:inline-block; font-size:.8rem; padding:3px 10px; border-radius:999px; background:rgba(99,102,241,.12); border:1px solid rgba(99,102,241,.3); margin-top:10px;}

div[class*="st-key-pmsg-user"] {margin-left:auto; max-width:78%; padding:10px 16px !important; border-radius:18px 18px 4px 18px;
  background: linear-gradient(135deg,#0ea5e9,#6366f1); color:#fff; animation: perryIn .3s ease-out;}
div[class*="st-key-pmsg-user"] p {color:#fff; margin:0; padding:2px 0;}
div[class*="st-key-pmsg"], div[class*="st-key-pmsg"] * {overflow: visible !important;}
div[class*="st-key-pmsg"] p, div[class*="st-key-pmsg"] li {line-height: 1.75;}
div[class*="st-key-pmsg"] [data-testid="stMarkdownContainer"] {margin-bottom: 0 !important;}
div[class*="st-key-pmsg-perry"] {max-width:92%; padding:12px 16px !important; border-radius:18px 18px 18px 4px;
  background: rgba(20,184,166,.08); border:1px solid rgba(20,184,166,.28); animation: perryIn .35s ease-out;}
div[class*="st-key-pmsg-perry-error"] {background: rgba(239,68,68,.07); border-color: rgba(239,68,68,.35);}
.perry-who {display:flex; align-items:center; gap:8px; font-weight:800; font-size:.82rem; letter-spacing:.08em; opacity:.85; margin-bottom:4px;}
.perry-who svg {margin:0;}
.perry-src {display:inline-block; font-size:.76rem; padding:2px 9px; border-radius:999px; margin:6px 6px 0 0;
  background: rgba(128,128,128,.12); border:1px solid rgba(128,128,128,.22);}
.perry-lang {display:inline-block; font-size:.72rem; padding:1px 8px; border-radius:999px; background:rgba(245,158,11,.15); border:1px solid rgba(245,158,11,.35); margin-left:6px;}
.perry-thinking-row {display:flex; align-items:center; gap:10px; font-size:.95rem; opacity:.9;}
.perry-dots span {display:inline-block; width:7px; height:7px; margin:0 2px; border-radius:50%; background:#14b8a6; animation: perryDots 1.2s infinite;}
.perry-dots span:nth-child(2){animation-delay:.15s} .perry-dots span:nth-child(3){animation-delay:.3s}
.perry-qa-label {font-size:.8rem; opacity:.65; margin: 14px 0 4px; letter-spacing:.06em; text-transform:uppercase;}
div[class*="st-key-qa-"] button {border-radius:999px !important; border:1px solid rgba(20,184,166,.45) !important;
  background: rgba(20,184,166,.07) !important; padding: 4px 12px !important; min-height: 0 !important; transition: all .15s ease;}
div[class*="st-key-qa-"] button:hover {background: rgba(20,184,166,.2) !important; transform: translateY(-1px);}
div[class*="st-key-qa-"] button p {font-size:.86rem !important;}
[data-testid="stChatInput"] textarea {height: auto !important; min-height: 1.6rem !important; max-height: 8rem !important; field-sizing: content;}
[data-testid="stChatInput"] {border-radius: 22px !important; border: 1.5px solid rgba(20,184,166,.55) !important;
  box-shadow: 0 6px 24px rgba(14,165,233,.12);}
.perry-foot {text-align:center; font-size:.75rem; opacity:.55; margin-top:6px;}
div[class*="st-key-say-"] button {border-radius:999px !important; padding:0 10px !important; min-height:0 !important; height:28px;
  border:1px solid rgba(20,184,166,.35) !important; background:transparent !important; margin-top:6px;}
div[class*="st-key-say-"] button:hover {background: rgba(20,184,166,.15) !important;}
.perry-langs {text-align:center; font-size:.8rem; opacity:.75; margin-top:12px; line-height:1.7;}
div[class*="st-key-pmsg"] p, div[class*="st-key-pmsg"] li {unicode-bidi: plaintext; text-align: start;}
@media (max-width: 640px) {.perry-name{font-size:2.3rem} div[class*="st-key-pmsg-user"]{max-width:92%}
  [data-testid="stMainBlockContainer"] {padding-top: 4.2rem !important;}}
</style>
"""
