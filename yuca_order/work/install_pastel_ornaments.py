from pathlib import Path
from PIL import Image
import re

root = Path('/Users/erinren/erin_creation/yuca_order')
source = Path('/Users/erinren/.codex/generated_images/01a08640-3409-7893-a4a7-425c980efb15/exec-be14df03-f2df-4b41-91d6-ec8f013f926b.png')
target = root/'static/ballet-ornaments-pastel.webp'
with Image.open(source) as image:
    image.thumbnail((512, 214), Image.Resampling.LANCZOS)
    image.save(target, 'WEBP', quality=84, method=6, alpha_quality=90, exact=True)
print(f'Ornaments: {source.stat().st_size} -> {target.stat().st_size} bytes')
p = root/'templates/_ballet_scene.html'
s = p.read_text()
# Each half of the atlas is displayed in its own bounded SVG viewport.
def ornament(kind, variant, x, y, size):
    left = 0 if kind == 'snow' else 971
    return f'''    <g class="floating-{kind} {kind}-{variant}"><svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="{left} 0 971 809" overflow="hidden"><image href="{{{{ url_for('static', filename='ballet-ornaments-pastel.webp') }}}}" width="1942" height="809"/></svg></g>'''
items = [ornament('snow','one',154,81,39), ornament('snow','two',426,191,34), ornament('snow','three',372,28,33), ornament('candy','one',161,211,45), ornament('candy','two',421,96,44), ornament('candy','three',387,260,35)]
s = re.sub(r'    <g class="floating-(?:snow|candy)[^\n]+\n', '', s)
s = s.replace('  </svg>\n</div>', '\n'.join(items)+'\n  </svg>\n</div>')
p.write_text(s)
