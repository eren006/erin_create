from pathlib import Path
from PIL import Image
import json

root = Path('/Users/erinren/erin_creation/yuca_order')
specs = {
    'ballet-island-complete': (1280, 854),
    'ballet-curtain-pastel': (600, 1740),
    'ballet-dancer-pastel': (512, 768),
    'ballet-ribbon-silk': (200, 600),
    'ballet-swan': (360, 240),
    'ballet-masthead-pastel': (1280, 854),
}
report = []
for stem, box in specs.items():
    source = root/'static'/f'{stem}.png'
    target = source.with_suffix('.webp')
    with Image.open(source) as image:
        image.thumbnail(box, Image.Resampling.LANCZOS)
        image.save(target, 'WEBP', quality=84, method=6, alpha_quality=90, exact=True)
        report.append(dict(asset=stem, before=source.stat().st_size, after=target.stat().st_size, size=image.size))
for rel in ['templates/_ballet_scene.html', 'static/ballet-refined.css']:
    path = root/rel
    text = path.read_text()
    for stem in specs:
        text = text.replace(f'{stem}.png', f'{stem}.webp')
    path.write_text(text)
(root/'work/ballet-compression.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
before = sum(item['before'] for item in report)
after = sum(item['after'] for item in report)
print(f'Total: {before} -> {after} bytes, reduction {100*(1-after/before):.1f}%')
