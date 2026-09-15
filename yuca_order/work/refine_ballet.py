from pathlib import Path
import shutil
root=Path('/Users/erinren/erin_creation/yuca_order')
assets=Path('/Users/erinren/.codex/generated_images/01a08640-3409-7893-a4a7-425c980efb15')
for src,dst in [('exec-287294ca-ddec-48d0-a7f4-4250f8dc7b66.png','ballet-stage-fine.png'),('exec-a53c36f5-b898-4b82-96f2-304cc3ba4ff6.png','ballet-dancer-fine.png')]:
 shutil.copy2(assets/src,root/'static'/dst)
p=root/'templates/_ballet_scene.html';s=p.read_text();s=s[:s.index('  <svg class="theatre-story"')]
s += '''  <svg class="theatre-story" viewBox="0 0 600 470" focusable="false">
    <defs>
      <linearGradient id="snow-gold" x2="1" y2="1"><stop stop-color="#fff1bd"/><stop offset=".4" stop-color="#b7873d"/><stop offset=".7" stop-color="#e8c579"/><stop offset="1" stop-color="#a47532"/></linearGradient>
      <radialGradient id="sweet-pink" cx=".3" cy=".25"><stop stop-color="#fff5e8"/><stop offset=".45" stop-color="#efb6c5"/><stop offset="1" stop-color="#a85475"/></radialGradient>
      <g id="snow-arm"><path d="M0 0V-15M0 -8L-5 -12M0 -8L5 -12M0 -3L-4 -7M0 -3L4 -7"/></g>
      <g id="gold-snowflake" fill="none" stroke="url(#snow-gold)" stroke-width="1.4" stroke-linecap="round"><use href="#snow-arm"/><use href="#snow-arm" transform="rotate(60)"/><use href="#snow-arm" transform="rotate(120)"/><use href="#snow-arm" transform="rotate(180)"/><use href="#snow-arm" transform="rotate(240)"/><use href="#snow-arm" transform="rotate(300)"/><circle r="2" fill="#fff0bc"/></g>
      <g id="wrapped-sweet"><path d="M-10 -4L-23 -10L-21 1L-24 10L-10 5M10 -4L23 -10L21 1L24 10L10 5" fill="#e6b9c4" stroke="#bd8a9c" stroke-width=".8"/><path d="M-20 -6L-12 0L-21 6M20 -6L12 0L21 6" fill="none" stroke="#fff2e2" stroke-width=".8"/><rect x="-13" y="-9" width="26" height="18" rx="8" fill="url(#sweet-pink)" stroke="#c5909e" stroke-width=".8"/><path d="M-5 -8L-9 7M3 -8L-1 8M10 -6L6 8" stroke="#fff0de" stroke-width="2.5" opacity=".8"/><path d="M-8 -4Q0 -8 7 -4" stroke="#fff9f1" fill="none" stroke-width="1.2"/></g>
      <g id="sugar-drop"><path d="M0 8V30" stroke="#d9b989" stroke-width="3"/><circle r="13" fill="#fbe8d8" stroke="#cb9a9d" stroke-width="1"/><path d="M0 0C-8 -4 -4 -13 5 -10C19 -4 10 14 -2 10C-19 5 -10 -17 5 -11M0 0Q5 7 8 0" fill="none" stroke="#c47992" stroke-width="2.5"/><circle cx="-4" cy="-5" r="2" fill="#fff9eb" opacity=".8"/></g>
    </defs>
    <image href="{{ url_for('static', filename='ballet-stage-fine.png') }}" x="0" y="70" width="600" height="400"/>
    <g class="storybook-dancer"><image href="{{ url_for('static', filename='ballet-dancer-fine.png') }}" x="207" y="48" width="214" height="321"/></g>
    <g class="floating-snow snow-one"><use href="#gold-snowflake" x="254" y="119"/></g>
    <g class="floating-snow snow-two"><use href="#gold-snowflake" x="427" y="236"/></g>
    <g class="floating-snow snow-three"><use href="#gold-snowflake" x="367" y="48"/></g>
    <g class="floating-candy candy-one"><use href="#wrapped-sweet" transform="translate(198 213) rotate(-24) scale(.72)"/></g>
    <g class="floating-candy candy-two"><use href="#wrapped-sweet" transform="translate(451 125) rotate(19) scale(.8)"/></g>
    <g class="floating-candy candy-three"><use href="#sugar-drop" transform="translate(374 174) rotate(20) scale(.65)"/></g>
  </svg>
</div>
'''
# Add finer velvet folds, woven texture, and a double gilt edge.
s=s.replace('<linearGradient id="velvet"', '<pattern id="velvet-weave" width="5" height="5" patternUnits="userSpaceOnUse"><path d="M0 1H5M1 0V5" stroke="#fbe4de" opacity=".13" stroke-width=".45"/></pattern><linearGradient id="velvet"')
s=s.replace('  </svg>', '''    <path d="M0 46Q175 128 350 56Q525 118 700 50Q875 118 1050 56Q1225 128 1400 46" fill="none" stroke="#f5dba1" stroke-width="1"/>
  </svg>''',1)
for cls,flip in [('curtain-left',''),('curtain-right','translate(1400 0) scale(-1 1)')]:
 start=s.index('<g class="'+cls+'">');end=s.index('</g>',start)
 detail=f'<g transform="{flip}"><path d="M0 0H175Q178 170 119 283Q93 340 47 370Q84 490 110 682L0 714Z" fill="url(#velvet-weave)"/>'
 for x in [18,38,58,78,98,118,138,158]:
  detail+=f'<path d="M{x} 0Q{x+36} 178 {12+x*.3:.1f} 357" fill="none" stroke="#74364f" stroke-width="1" opacity=".18"/>'
 detail+='<path d="M70 449L73 471M75 447L77 473M80 446L81 474M85 448L86 472" stroke="#f9deb0" stroke-width="1"/></g>'
 s=s[:end]+detail+s[end:]
p.write_text(s)
p=root/'static/ballet.css';s=p.read_text();s += '''
/* Detailed painted assets, independently animated over a stationary stage. */
[data-theme="ballet"] .motion-enabled .storybook-dancer{transform-origin:306px 361px;animation-name:dancer-fine}
@keyframes dancer-fine{from{transform:rotate(-1.2deg)}to{transform:rotate(1.2deg)}}
@media(prefers-reduced-motion:no-preference){
 [data-theme="ballet"] .motion-enabled .floating-snow{animation:snow-drift 7s ease-in-out infinite alternate;transform-box:fill-box;transform-origin:center}
 [data-theme="ballet"] .motion-enabled .snow-two{animation-delay:-3s;animation-duration:9s}
 [data-theme="ballet"] .motion-enabled .snow-three{animation-delay:-5s;animation-duration:8s}
 [data-theme="ballet"] .motion-enabled .floating-candy{animation:sweet-drift 6s ease-in-out infinite alternate;transform-box:fill-box;transform-origin:center}
 [data-theme="ballet"] .motion-enabled .candy-two{animation-delay:-2s;animation-duration:8s}
 [data-theme="ballet"] .motion-enabled .candy-three{animation-delay:-4s;animation-duration:7s}
}
@keyframes snow-drift{from{transform:translate(-3px,5px) rotate(-12deg);opacity:.65}to{transform:translate(4px,-9px) rotate(15deg);opacity:1}}
@keyframes sweet-drift{from{transform:translate(-3px,4px) rotate(-7deg)}to{transform:translate(4px,-9px) rotate(8deg)}}
''';p.write_text(s)
p=root/'templates/base.html';p.write_text(p.read_text().replace("filename='ballet.css', v='2'","filename='ballet.css', v='3'"))
