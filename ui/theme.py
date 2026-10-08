from perry_mascot import avatar_css, head_data_uri

FONT_BASE = "app/static/fonts"

SCENE = """<div class="perry-scene" aria-hidden="true">
<div class="ps-ceiling"><i></i><i></i><i></i></div><div class="ps-glow"></div><div class="ps-glow2"></div>
<div class="ps-shelf ps-shelf-l"></div><div class="ps-shelf ps-shelf-r"></div>
<div class="ps-bokeh"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
<svg class="ps-plants" viewBox="0 0 400 260" preserveAspectRatio="xMaxYMax meet">
<path d="M330 260 C320 200 300 170 280 150 M330 260 C335 190 350 150 372 130 M330 260 C340 210 330 170 318 120" stroke="#1F6B4F" stroke-width="10" fill="none" stroke-linecap="round"/>
<ellipse cx="282" cy="148" rx="26" ry="11" fill="#1F6B4F" transform="rotate(-30 282 148)"/><ellipse cx="370" cy="130" rx="28" ry="11" fill="#22805C" transform="rotate(25 370 130)"/>
<ellipse cx="318" cy="118" rx="12" ry="28" fill="#1A5E45"/><rect x="300" y="226" width="60" height="34" rx="6" fill="#123A3C"/></svg>
<div class="ps-particles"><i></i><i></i><i></i><i></i><i></i><i></i></div>
</div>"""


def theme_css() -> str:
    head = head_data_uri(40)
    return f"""<style>
@font-face {{font-family: PerryHand; src: url("{FONT_BASE}/Kalam-Bold.ttf") format("truetype"); font-display: swap;}}
@font-face {{font-family: PerryLogo; src: url("{FONT_BASE}/Baloo2.ttf") format("truetype"); font-weight: 400 800; font-display: swap;}}
:root {{
  --p-bg: #061B1E; --p-bg2: #0A2A2E; --p-glass: rgba(10, 42, 46, .58); --p-glass2: rgba(14, 54, 58, .55);
  --p-border: rgba(46, 230, 214, .26); --p-cyan: #2EE6D6; --p-cyan2: #7DF9EC; --p-teal: #14B8A6; --p-orange: #F7941D;
  --p-text: #E8FBF8; --p-muted: #9CC9C4; --p-shadow: 0 18px 50px rgba(0, 0, 0, .45);
  --p-mint: #9FF0D9; --p-peach: #FFC2A8; --p-lilac: #D9C2FF; --p-sky: #B9E3FF; --p-sun: #FFE08A; --p-pink: #FFB8D9;
}}
.stApp {{
  background:
    radial-gradient(900px 520px at 96% -6%, rgba(46, 230, 214, .16), transparent 60%),
    radial-gradient(700px 500px at 70% 60%, rgba(46, 230, 214, .08), transparent 70%),
    radial-gradient(1200px 800px at 30% 120%, rgba(4, 12, 14, .9), transparent 60%),
    linear-gradient(160deg, #0B2E2F 0%, #071F22 45%, #04161A 100%) !important;
  color: var(--p-text);
}}
[data-testid="stHeader"] {{background: transparent !important;}}
[data-testid="stMainBlockContainer"] {{max-width: 1500px; padding-top: 1.4rem !important; position: relative; z-index: 2;}}
.perry-scene {{position: fixed; inset: 0; pointer-events: none; z-index: 0; overflow: hidden;}}
.ps-ceiling {{position: absolute; right: 6%; top: -60px; width: 520px; height: 200px;}}
.ps-ceiling i {{position: absolute; left: 50%; top: 50%; border-radius: 50%; border: 3px solid rgba(125, 249, 236, .5);
  box-shadow: 0 0 22px rgba(46, 230, 214, .45), inset 0 0 18px rgba(46, 230, 214, .3); transform: translate(-50%, -50%);}}
.ps-ceiling i:nth-child(1) {{width: 480px; height: 120px;}} .ps-ceiling i:nth-child(2) {{width: 340px; height: 80px; opacity: .7;}}
.ps-ceiling i:nth-child(3) {{width: 200px; height: 46px; opacity: .5;}}
.ps-glow {{position: absolute; right: 0; top: 0; width: 50vw; height: 80vh; background: radial-gradient(closest-side, rgba(46, 230, 214, .10), transparent);}}
.ps-glow2 {{position: absolute; left: 18%; top: 10%; width: 40vw; height: 60vh; background: radial-gradient(closest-side, rgba(255, 190, 110, .06), transparent);}}
.ps-shelf {{position: absolute; top: 18vh; width: 140px; height: 62vh; border-radius: 10px; filter: blur(3px); opacity: .5;
  background: repeating-linear-gradient(180deg, rgba(46, 230, 214, .0) 0 70px, rgba(46, 230, 214, .35) 70px 73px), linear-gradient(180deg, rgba(10, 50, 54, .5), rgba(4, 22, 25, .2));}}
.ps-shelf-l {{left: 262px;}} .ps-shelf-r {{right: -40px;}}
.ps-bokeh i {{position: absolute; border-radius: 50%; background: radial-gradient(circle, rgba(125, 249, 236, .35), transparent 70%); filter: blur(2px);}}
.ps-bokeh i:nth-child(1) {{left: 22%; top: 12%; width: 60px; height: 60px;}} .ps-bokeh i:nth-child(2) {{left: 48%; top: 6%; width: 34px; height: 34px;}}
.ps-bokeh i:nth-child(3) {{left: 70%; top: 18%; width: 80px; height: 80px; opacity: .6;}} .ps-bokeh i:nth-child(4) {{left: 88%; top: 52%; width: 50px; height: 50px;}}
.ps-bokeh i:nth-child(5) {{left: 64%; top: 78%; width: 70px; height: 70px; opacity: .5;}} .ps-bokeh i:nth-child(6) {{left: 30%; top: 86%; width: 40px; height: 40px;}}
.ps-bokeh i:nth-child(7) {{left: 96%; top: 10%; width: 46px; height: 46px; background: radial-gradient(circle, rgba(255, 190, 110, .35), transparent 70%);}}
.ps-bokeh i:nth-child(8) {{left: 18%; top: 60%; width: 30px; height: 30px; background: radial-gradient(circle, rgba(255, 190, 110, .3), transparent 70%);}}
.ps-plants {{position: absolute; right: 0; bottom: 0; width: 34vw; max-width: 520px; opacity: .32; filter: blur(2.5px);}}
.ps-particles i {{position: absolute; width: 4px; height: 4px; border-radius: 50%; background: var(--p-cyan2); opacity: .0;
  animation: psFloat 14s linear infinite;}}
.ps-particles i:nth-child(1) {{left: 58%; top: 80%; animation-delay: 0s;}} .ps-particles i:nth-child(2) {{left: 66%; top: 90%; animation-delay: 3s;}}
.ps-particles i:nth-child(3) {{left: 74%; top: 85%; animation-delay: 6s;}} .ps-particles i:nth-child(4) {{left: 82%; top: 95%; animation-delay: 9s;}}
.ps-particles i:nth-child(5) {{left: 38%; top: 92%; animation-delay: 4s;}} .ps-particles i:nth-child(6) {{left: 90%; top: 70%; animation-delay: 11s;}}
@keyframes psFloat {{0% {{transform: translateY(0); opacity: 0}} 20% {{opacity: .5}} 100% {{transform: translateY(-70vh); opacity: 0}}}}

[data-testid="stSidebar"] {{background: linear-gradient(180deg, rgba(5, 26, 29, .97), rgba(4, 20, 23, .97)) !important;
  border-right: 1px solid rgba(46, 230, 214, .14); min-width: 260px !important; max-width: 260px !important;}}
[data-testid="stSidebarUserContent"] {{padding-top: .6rem;}}
.p-logo {{display: flex; flex-direction: column; align-items: flex-start; padding: 2px 6px 10px; position: relative;}}
.p-logo .w {{font-family: PerryLogo, PerryHand, cursive; font-weight: 800; font-size: 3.1rem; line-height: .95; letter-spacing: .02em;
  background: linear-gradient(180deg, #7DF9EC, #18C2B2 60%, #0E9C92); -webkit-background-clip: text; background-clip: text; color: transparent;
  filter: drop-shadow(0 3px 0 #04363A) drop-shadow(0 0 14px rgba(46, 230, 214, .25)); transform: rotate(-3deg);}}
.p-logo .hat {{position: absolute; left: 0; top: -14px; transform: rotate(-14deg);}}
.p-logo .s {{color: var(--p-text); font-size: 1.02rem; line-height: 1.2; margin: 6px 0 0 36px;}}
[data-testid="stPageLink-NavLink"] {{border-radius: 14px !important; padding: .55rem .8rem !important; margin: 2px 0;
  border: 1px solid transparent; transition: all .18s ease; color: var(--p-text) !important;}}
[data-testid="stPageLink-NavLink"]:hover {{background: rgba(46, 230, 214, .08) !important; border-color: rgba(46, 230, 214, .2);}}
[data-testid="stPageLink-NavLink"][aria-current="page"] {{background: linear-gradient(90deg, rgba(46, 230, 214, .22), rgba(46, 230, 214, .06)) !important;
  border-color: rgba(46, 230, 214, .55); box-shadow: 0 0 18px rgba(46, 230, 214, .22), inset 3px 0 0 var(--p-cyan);}}
[data-testid="stPageLink-NavLink"] p {{font-size: 1.02rem !important;}}
[data-testid="stPageLink-NavLink"] span[data-testid="stIconMaterial"] {{color: var(--p-cyan2);}}
.p-user {{display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 16px; margin-top: 1.4rem;
  background: var(--p-glass2); border: 1px solid var(--p-border);}}
.p-ava {{width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center; font-weight: 800; color: #04363A;
  background: radial-gradient(circle at 35% 30%, #9FFBF1, #19BFB1); box-shadow: 0 0 0 2px rgba(46, 230, 214, .35);}}
.p-user .n {{font-weight: 700;}} .p-user .r {{color: var(--p-muted); font-size: .85rem;}}
div[class*="st-key-p-settings"] button {{border-radius: 16px !important; background: var(--p-glass2) !important; border: 1px solid var(--p-border) !important;
  justify-content: flex-start !important; padding: .6rem 1rem !important;}}

.p-tagline {{font-family: PerryHand, cursive; font-size: clamp(1.6rem, 2.6vw, 2.45rem); line-height: 1.12; transform: rotate(-2deg);
  background: linear-gradient(90deg, #A8FFF5, #2EE6D6); -webkit-background-clip: text; background-clip: text; color: transparent; margin: .2rem 0 0;}}
.p-swoosh {{display: block; margin: -2px 0 0 18%; width: 62%; height: 18px;}}
div[class*="st-key-p-search"] input {{border-radius: 999px !important; background: rgba(4, 26, 29, .7) !important; border: 1.5px solid rgba(46, 230, 214, .4) !important;
  padding-left: 1rem !important;}}
div[class*="st-key-p-bell"] button, .p-head-ava {{border-radius: 50% !important; width: 46px; height: 46px; min-height: 46px;
  background: var(--p-glass2) !important; border: 1px solid var(--p-border) !important;}}
.p-head-ava {{display: grid; place-items: center; font-weight: 800; color: #04363A; background: radial-gradient(circle at 35% 30%, #9FFBF1, #19BFB1) !important;}}
.p-online {{font-size: .72rem; letter-spacing: .12em; color: var(--p-cyan2); text-align: center;}}
.p-online b {{display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #22C55E; margin-right: 6px; box-shadow: 0 0 8px #22C55E;}}

div[class*="st-key-perry-panel"] {{background: var(--p-glass); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  border: 1px solid var(--p-border); border-radius: 28px; padding: 22px 22px 16px !important; box-shadow: var(--p-shadow), inset 0 1px 0 rgba(255, 255, 255, .05);}}
.p-card, div[class*="st-key-p-card"] {{background: var(--p-glass); backdrop-filter: blur(20px); border: 1px solid var(--p-border);
  border-radius: 22px; padding: 16px 18px; box-shadow: var(--p-shadow);}}
.p-welcome {{display: flex; gap: 16px; align-items: flex-start; animation: pIn .5s ease-out;}}
.p-welcome .face {{flex: 0 0 auto; width: 84px; height: 84px; border-radius: 50%; overflow: hidden; display: grid; place-items: center;
  background: radial-gradient(circle at 40% 30%, #1E5F63, #0B2E31); border: 2px solid rgba(46, 230, 214, .45); box-shadow: 0 0 22px rgba(46, 230, 214, .25);}}
.p-welcome .say {{background: var(--p-glass2); border: 1px solid var(--p-border); border-radius: 18px 18px 18px 6px; padding: 12px 18px; line-height: 1.55;}}
@keyframes pIn {{from {{opacity: 0; transform: translateY(8px)}} to {{opacity: 1; transform: none}}}}

div[class*="st-key-qa-row"] {{gap: .55rem !important;}}
div[class*="st-key-qa-"] button {{border-radius: 999px !important; border: none !important; color: #0B2A2E !important; font-weight: 600;
  padding: .35rem 1rem !important; min-height: 2.5rem; transition: transform .15s ease, box-shadow .15s ease;}}
div[class*="st-key-qa-"] button:hover {{transform: translateY(-2px); box-shadow: 0 8px 22px rgba(0, 0, 0, .35);}}
div[class*="st-key-qa-"] button:active {{transform: scale(.97);}}
div[class*="st-key-qa-"] button p, div[class*="st-key-qa-"] button span {{color: #0B2A2E !important;}}
div[class*="st-key-qa-0"] button {{background: var(--p-mint) !important;}} div[class*="st-key-qa-1"] button {{background: var(--p-peach) !important;}}
div[class*="st-key-qa-2"] button {{background: var(--p-lilac) !important;}} div[class*="st-key-qa-3"] button {{background: var(--p-sky) !important;}}
div[class*="st-key-qa-4"] button {{background: var(--p-sun) !important;}} div[class*="st-key-qa-5"] button {{background: var(--p-pink) !important;}}

div[class*="st-key-pmsg-user"] {{margin-left: auto; max-width: 74%; width: fit-content !important; min-width: 180px; padding: 10px 16px 6px !important; border-radius: 20px 20px 6px 20px;
  background: linear-gradient(135deg, rgba(20, 184, 166, .38), rgba(14, 116, 144, .35)); border: 1px solid rgba(46, 230, 214, .35); animation: pIn .3s ease-out;}}
div[class*="st-key-pmsg-perry"] {{position: relative; margin-left: 58px; max-width: 86%; padding: 14px 18px 8px !important;
  border-radius: 20px 20px 20px 6px; background: var(--p-glass2); border: 1px solid var(--p-border); animation: pIn .35s ease-out;}}
div[class*="st-key-pmsg-perry"]::before {{content: ""; position: absolute; left: -58px; top: 0; width: 46px; height: 46px; border-radius: 50%;
  background: url("{head}") center/cover no-repeat, radial-gradient(circle at 40% 30%, #1E5F63, #0B2E31);
  border: 2px solid rgba(46, 230, 214, .45);}}
div[class*="st-key-pmsg-perry-error"] {{border-color: rgba(251, 191, 36, .5); background: rgba(80, 40, 10, .35);}}
div[class*="st-key-pmsg-perry-thinking"]::before {{display: none;}}
div[class*="st-key-pmsg"] p, div[class*="st-key-pmsg"] li {{line-height: 1.7; unicode-bidi: plaintext; text-align: start;}}
div[class*="st-key-pmsg"] [data-testid="stMarkdownContainer"] {{margin-bottom: 0 !important;}}
div[class*="st-key-pmsg"], div[class*="st-key-pmsg"] * {{overflow: visible !important;}}
div[class*="st-key-pmsg-perry-rtl"] [data-testid="stMarkdownContainer"] {{direction: rtl; text-align: right;}}
.p-time {{font-size: .72rem; color: var(--p-muted); text-align: right; margin-top: 2px;}}
.p-lang {{display: inline-block; font-size: .72rem; padding: 1px 9px; border-radius: 999px; background: rgba(247, 148, 29, .16);
  border: 1px solid rgba(247, 148, 29, .4); margin-left: 6px;}}
.vchip {{display: inline-block; padding: 0 8px; border-radius: 999px; font-size: .82em; font-weight: 700; margin: 0 2px;}}
.v-high {{background: rgba(248, 113, 113, .18); color: #FCA5A5; border: 1px solid rgba(248, 113, 113, .45);}}
.v-low {{background: rgba(96, 165, 250, .18); color: #93C5FD; border: 1px solid rgba(96, 165, 250, .45);}}
.v-normal {{background: rgba(74, 222, 128, .15); color: #86EFAC; border: 1px solid rgba(74, 222, 128, .4);}}
.v-far {{background: rgba(251, 191, 36, .2); color: #FCD34D; border: 1px solid rgba(251, 191, 36, .5);}}
.p-checked {{font-size: .74rem; color: var(--p-cyan2); margin: 8px 0 2px 58px; letter-spacing: .03em;}}
div[class*="st-key-src-"] button {{text-align: left !important; justify-content: flex-start !important; border-radius: 16px !important;
  background: rgba(6, 30, 33, .72) !important; border: 1px solid var(--p-border) !important; padding: .55rem .9rem !important; animation: pIn .45s ease-out;}}
div[class*="st-key-src-"] button:hover {{border-color: var(--p-cyan) !important; box-shadow: 0 0 16px rgba(46, 230, 214, .2);}}
div[class*="st-key-src-"] button p {{white-space: pre-line; text-align: left; font-size: .9rem;}}
div[class*="st-key-fb-"] button {{background: transparent !important; border: none !important; padding: .2rem .4rem !important; min-height: 0 !important; opacity: .75;}}
div[class*="st-key-fb-"] button:hover {{opacity: 1;}}
div[class*="st-key-say-"] button {{border-radius: 999px !important; padding: 0 10px !important; min-height: 0 !important; height: 28px;
  border: 1px solid rgba(46, 230, 214, .35) !important; background: transparent !important;}}

[data-testid="stChatInput"] {{border-radius: 999px !important; border: 2px solid rgba(46, 230, 214, .7) !important; background: rgba(4, 22, 25, .85) !important;
  box-shadow: 0 0 0 4px rgba(46, 230, 214, .08), 0 0 26px rgba(46, 230, 214, .25) !important;}}
[data-testid="stChatInput"] textarea {{height: auto !important; min-height: 1.6rem !important; max-height: 8rem !important; field-sizing: content;}}
[data-testid="stChatInputFileUploadButton"] button svg {{display: none;}}
[data-testid="stChatInputFileUploadButton"] button::before {{content: ""; width: 20px; height: 20px; background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%237DF9EC' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48'/></svg>") center/contain no-repeat;}}
[data-testid="stChatInputSubmitButton"] {{background: var(--p-teal) !important; border-radius: 50% !important; color: #02292B !important;}}
[data-testid="stChatInputMicButton"] {{border-radius: 50% !important; border: 1.5px solid rgba(46, 230, 214, .6) !important;}}
[data-testid="stChatInputMicButton"][aria-label="Stop recording"] {{background: rgba(239, 68, 68, .2) !important; border-color: #F87171 !important;
  animation: pMic 1.1s ease-in-out infinite;}}
@keyframes pMic {{0%, 100% {{box-shadow: 0 0 0 0 rgba(248, 113, 113, .5)}} 50% {{box-shadow: 0 0 0 10px rgba(248, 113, 113, 0)}}}}
div[class*="st-key-p-lang"] [data-baseweb="select"] > div {{border-radius: 999px !important; background: rgba(4, 26, 29, .7) !important; border-color: var(--p-border) !important;}}
div[class*="st-key-p-speak"] button {{border-radius: 999px !important; background: rgba(46, 230, 214, .1) !important; border: 1px solid rgba(46, 230, 214, .5) !important;}}
.p-thinking {{display: flex; align-items: center; gap: 10px;}}
.p-dots span {{display: inline-block; width: 7px; height: 7px; margin: 0 2px; border-radius: 50%; background: var(--p-cyan); animation: pDots 1.2s infinite;}}
.p-dots span:nth-child(2) {{animation-delay: .15s}} .p-dots span:nth-child(3) {{animation-delay: .3s}}
@keyframes pDots {{0%, 80%, 100% {{opacity: .25; transform: translateY(0)}} 40% {{opacity: 1; transform: translateY(-4px)}}}}
.p-empty {{text-align: center; padding: 18px; color: var(--p-muted);}}

div[class*="st-key-perry-stage"] {{position: sticky; top: 1rem;}}
.pv-stage {{position: relative; display: flex; flex-direction: column; align-items: center;}}
.pv-bubble {{align-self: flex-end; margin: 0 4px -18px 0; transform: rotate(-4deg); padding: 12px 18px; max-width: 220px; position: relative; z-index: 3;
  font-family: PerryHand, cursive; font-size: 1.35rem; line-height: 1.15; color: var(--p-cyan2);
  background: rgba(10, 46, 50, .7); backdrop-filter: blur(12px); border: 1.5px solid rgba(46, 230, 214, .5); border-radius: 22px;
  box-shadow: 0 0 22px rgba(46, 230, 214, .18); animation: pvFloat 4s ease-in-out infinite;}}
.pv-bubble::after {{content: ""; position: absolute; left: 30px; bottom: -14px; width: 22px; height: 22px; background: inherit;
  border-right: 1.5px solid rgba(46, 230, 214, .5); border-bottom: 1.5px solid rgba(46, 230, 214, .5); transform: rotate(45deg) skew(10deg, 10deg);
  backdrop-filter: none;}}
.p-welcome .face img, .p-thinking img {{width: 100% !important; height: 100% !important;}}
.p-thinking .pv-head {{width: 38px !important; height: 38px !important; border: 1.5px solid rgba(46, 230, 214, .45);}}
.pv-cards {{display: flex; gap: 10px; justify-content: center; margin-top: 6px;}}
.pv-card {{flex: 1 1 0; max-width: 118px; border-radius: 18px; padding: 6px 6px 6px; overflow: hidden; text-align: center;
  background: var(--p-glass); border: 1px solid rgba(46, 230, 214, .16); transition: all .25s ease; opacity: .72;}}
.pv-card.on {{opacity: 1; border-color: var(--p-cyan); box-shadow: 0 0 20px rgba(46, 230, 214, .3); transform: translateY(-3px);}}
.pv-card-label {{font-size: .85rem; font-weight: 600; margin-top: 2px;}}
.pv-card-img {{aspect-ratio: 4 / 5; border-radius: 12px; overflow: hidden;}}
.pv-card-img img {{width: 100%; height: 100%; object-fit: cover;}}
.pv-card.slot0 .v-idle {{object-position: 74% 50%;}}

.p-stat {{background: var(--p-glass); border: 1px solid var(--p-border); border-radius: 18px; padding: 12px 16px;}}
.p-stat .k {{color: var(--p-muted); font-size: .8rem; text-transform: uppercase; letter-spacing: .08em;}}
.p-stat .v {{font-size: 1.7rem; font-weight: 800; color: var(--p-cyan2);}}
.bx-card {{background: var(--p-glass); border: 1px solid var(--p-border) !important; border-radius: 18px !important;}}

*:focus-visible {{outline: 2px solid var(--p-cyan) !important; outline-offset: 2px;}}
@media (max-width: 1100px) {{
  .ps-shelf, .ps-plants, .pv-holo {{display: none;}}
  div[class*="st-key-perry-stage"] .pv-live {{width: 250px !important;}}
}}
@media (max-width: 760px) {{
  [data-testid="stHorizontalBlock"]:has(div[class*="st-key-perry-stage"]) {{flex-direction: column-reverse;}}
  div[class*="st-key-perry-stage"] {{position: static;}}
  div[class*="st-key-perry-stage"] .pv-live {{width: 140px !important;}}
  .pv-cards {{display: none;}}
  .pv-bubble {{font-size: 1.05rem; align-self: center;}}
  div[class*="st-key-pmsg-user"] {{max-width: 92%;}}
  div[class*="st-key-pmsg-perry"] {{margin-left: 0; max-width: 100%;}}
  div[class*="st-key-pmsg-perry"]::before {{display: none;}}
  .p-tagline {{font-size: 1.4rem;}}
}}
@media (prefers-reduced-motion: reduce) {{
  .ps-particles, .pv-bubble {{animation: none !important;}}
  * {{transition: none !important;}}
}}
{avatar_css()}
</style>"""
