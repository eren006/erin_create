from pathlib import Path
import shutil
root=Path('/Users/erinren/erin_creation/yuca_order')
shutil.copy2('/Users/erinren/.codex/generated_images/01a08640-3409-7893-a4a7-425c980efb15/exec-edda1676-f89d-42d0-a054-5c3c684ff695.png',root/'static/ballet-stage-romantic.png')
p=root/'templates/_ballet_scene.html';s=p.read_text();story=s[s.index('  <svg class="theatre-story"'):]
curtain='''<path d="M0 -24H170C176 124 139 258 58 343Q49 352 50 367C72 439 78 558 105 690L0 716Z" fill="url(#velvet)"/>
<path d="M25 -10Q91 195 20 345M59 -10Q118 174 31 348M97 -10Q143 154 40 348M138 -10Q159 145 49 343M16 380Q28 514 28 706M34 381Q41 531 61 700M48 388Q56 526 86 693" fill="none" stroke="#f8e0df" stroke-width="2" opacity=".35"/>
<path d="M0 343Q25 356 57 343L58 358Q28 372 0 357Z" fill="url(#tie-gold)"/>
<path d="M0 346Q27 359 56 347M0 353Q26 366 56 353" fill="none" stroke="#f6e1b5" stroke-width="1"/>
<path d="M50 355C75 364 77 390 59 409" fill="none" stroke="#b59a6b" stroke-width="3"/>
<path d="M50 355C74 365 74 390 58 407" fill="none" stroke="#f5dfb4" stroke-width="1"/>
<ellipse cx="58" cy="409" rx="5" ry="6" fill="url(#tie-gold)"/>
<path d="M54 412L48 438Q58 445 68 438L62 412Z" fill="url(#tie-gold)"/>
<path d="M55 414L52 438M58 414V441M61 414L64 438" stroke="#f9e6c8" stroke-width="1"/>'''
head='''{# Each curtain and its tieback are one animated layer; stage art is separate. #}
<div class="ballet-theatre ballet-only" aria-hidden="true">
<svg class="theatre-drapes" viewBox="0 0 1400 800" preserveAspectRatio="none" focusable="false">
<defs>
<linearGradient id="velvet"><stop stop-color="#aa778b"/><stop offset=".16" stop-color="#deb5c1"/><stop offset=".3" stop-color="#b5869a"/><stop offset=".47" stop-color="#e6c2cc"/><stop offset=".61" stop-color="#b38598"/><stop offset=".78" stop-color="#d6abba"/><stop offset="1" stop-color="#a37187"/></linearGradient>
<linearGradient id="valance" x2="0" y2="1"><stop stop-color="#ae7c91"/><stop offset="1" stop-color="#e5c3cc"/></linearGradient>
<linearGradient id="tie-gold" x2="0" y2="1"><stop stop-color="#c7ad7a"/><stop offset=".42" stop-color="#e8d3a5"/><stop offset="1" stop-color="#b19662"/></linearGradient>
</defs>
<path d="M0 -20H1400V38Q1225 110 1050 48Q875 100 700 42Q525 100 350 48Q175 110 0 38Z" fill="url(#valance)"/>
<path d="M0 40Q175 112 350 50Q525 102 700 44Q875 102 1050 50Q1225 112 1400 40" fill="none" stroke="#d9c392" stroke-width="3"/>
<g class="curtain-left">'''+curtain+'''</g>
<g class="curtain-right"><g transform="translate(1400 0) scale(-1 1)">'''+curtain+'''</g></g>
</svg>
'''
story=story.replace("filename='ballet-stage-fine.png'","filename='ballet-stage-romantic.png'").replace('x="207" y="48"','x="207" y="58"')
story=story.replace('<image href="{{ url_for(\'static\', filename=\'ballet-stage-romantic.png\') }}"','<image class="romantic-stage-art" href="{{ url_for(\'static\', filename=\'ballet-stage-romantic.png\') }}"')
story=story.replace('    </defs>','''      <linearGradient id="ribbon-silk"><stop stop-color="#e6b6c5" stop-opacity=".3"/><stop offset=".35" stop-color="#f8dce3" stop-opacity=".8"/><stop offset=".65" stop-color="#d9a1b7" stop-opacity=".45"/><stop offset="1" stop-color="#fbe8eb" stop-opacity=".65"/></linearGradient>
    </defs>''',1)
ribbons='''    <g class="stage-ribbon ribbon-left" style="--ribbon-origin:155px 423px"><path d="M146 420C121 456 174 461 153 493Q143 511 152 532L164 522Q159 504 169 491C194 455 141 453 161 423Z" fill="url(#ribbon-silk)"/><path d="M151 426C131 456 182 461 160 495Q152 509 158 526" fill="none" stroke="#fff0f1" stroke-width="1" opacity=".7"/></g>
    <g class="stage-ribbon ribbon-center" style="--ribbon-origin:300px 433px"><path d="M291 432C283 459 310 472 298 499Q290 520 298 545L310 535Q302 517 312 498C327 470 299 454 308 433Z" fill="url(#ribbon-silk)"/><path d="M298 436C292 462 319 475 305 501Q299 519 304 537" stroke="#fff0f1" fill="none" opacity=".7"/></g>
    <g class="stage-ribbon ribbon-right" style="--ribbon-origin:448px 423px"><path d="M440 422C461 454 420 468 444 495Q457 511 446 532L460 526Q468 508 455 491C435 466 477 454 455 419Z" fill="url(#ribbon-silk)"/><path d="M448 426C466 455 428 469 449 494Q461 511 453 528" stroke="#fff0f1" fill="none" opacity=".7"/></g>
'''
story=story.replace('    <g class="storybook-dancer">',ribbons+'    <g class="storybook-dancer">')
p.write_text(head+story)
p=root/'static/ballet.css';s=p.read_text();s+='''
/* White paper blends into the page; sheer ribbons hang below the platform. */
.theatre-story{mix-blend-mode:multiply;top:32%}
[data-theme="ballet"] .ink-stage{min-height:900px}
.stage-ribbon{transform-origin:var(--ribbon-origin)}
@media(prefers-reduced-motion:no-preference){
 [data-theme="ballet"] .motion-enabled .stage-ribbon{animation:ribbon-whisper 6s ease-in-out infinite alternate}
 [data-theme="ballet"] .motion-enabled .ribbon-center{animation-duration:7.5s;animation-delay:-2s}
 [data-theme="ballet"] .motion-enabled .ribbon-right{animation-duration:6.8s;animation-delay:-4s}
}
@keyframes ribbon-whisper{from{transform:rotate(-3deg) skewX(-1deg)}to{transform:rotate(3deg) skewX(1deg)}}
@media(min-width:601px) and (max-width:1050px){
 [data-theme="ballet"] .ink-stage{min-height:1100px}
 .theatre-story{top:27%;width:430px}
}
@media(max-width:600px){
 .theatre-story{top:245px;width:285px}
 [data-theme="ballet"] .hero-left{top:535px}
 [data-theme="ballet"] .hero-query{top:808px}
 [data-theme="ballet"] .ink-stage{min-height:1150px}
}
''';p.write_text(s)
p=root/'templates/base.html';p.write_text(p.read_text().replace("filename='ballet.css', v='3'","filename='ballet.css', v='4'"))
p=root/'work/deploy_ballet.py';p.write_text(p.read_text().replace("'static/ballet-stage-fine.png'","'static/ballet-stage-romantic.png'"))
