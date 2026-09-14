from pathlib import Path
import shutil, math
root=Path('/Users/erinren/erin_creation/yuca_order');gen=Path('/Users/erinren/.codex/generated_images/01a08640-3409-7893-a4a7-425c980efb15')
for a,b in [('exec-049780ca-91e7-4ff3-a914-e9ca8eda09b2.png','ballet-dancer-pastel.png'),('exec-358747e1-87c2-4392-be53-dcddf1ad1d17.png','ballet-swan.png')]:shutil.copy2(gen/a,root/'static'/b)
p=root/'templates/_ballet_scene.html';s=p.read_text().replace("filename='ballet-dancer-fine.png'","filename='ballet-dancer-pastel.png'")
s=s.replace('    <g class="floating-snow snow-one">','    <image class="ballet-swan" href="{{ url_for(\'static\', filename=\'ballet-swan.png\') }}" x="378" y="304" width="116" height="77"/>\n    <g class="floating-snow snow-one">')
s=s.replace('<linearGradient id="velvet">','<radialGradient id="pearl" cx=".32" cy=".27"><stop stop-color="#fffef6"/><stop offset=".45" stop-color="#f6eee6"/><stop offset=".8" stop-color="#d5c6be"/><stop offset="1" stop-color="#bbaa9e"/></radialGradient><linearGradient id="velvet">',1)
pearls='<g class="pearl-necklace" opacity=".88"><path d="M125 75C245 178 242 279 95 230" stroke="#c8b899" stroke-width="1" fill="none"/>'
for i in range(43):
 t=i/42;u=1-t;x=u*u*u*125+3*u*u*t*245+3*u*t*t*242+t*t*t*95;y=u*u*u*75+3*u*u*t*178+3*u*t*t*279+t*t*t*230
 pearls+=f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.1" fill="url(#pearl)" stroke="#eee0d2" stroke-width=".4"/>'
pearls+='</g>'
pos=s.index('</svg>');s=s[:pos]+pearls+'<g transform="translate(1400 20) scale(-1 1)">'+pearls+'</g>'+s[pos:]
p.write_text(s)
p=root/'templates/base.html';p.write_text(p.read_text().replace("filename='ballet.css', v='4'","filename='ballet.css', v='5'"))
p=root/'work/deploy_ballet.py';s=p.read_text().replace("'static/ballet-dancer-fine.png'","'static/ballet-dancer-pastel.png','static/ballet-swan.png'");p.write_text(s)
