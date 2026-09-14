from pathlib import Path
import re, shutil

root = Path('/Users/erinren/erin_creation/yuca_order')
generated = Path('/Users/erinren/.codex/generated_images/01a08640-3409-7893-a4a7-425c980efb15')
for source, target in [
    ('exec-768a0afc-c513-434b-90a2-62b9e37f4f61.png', 'ballet-island-complete.png'),
    ('exec-2f9bb677-bb3b-4210-ba93-e343918d4985.png', 'ballet-curtain-pastel.png'),
    ('exec-601ca8b9-3b26-4491-973c-965e4d08b139.png', 'ballet-ribbon-silk.png'),
    ('exec-a2cd3536-2f4b-483e-a4aa-4d1a7df3be85.png', 'ballet-masthead-pastel.png'),
]:
    shutil.copy2(generated/source, root/'static'/target)

p = root/'templates/_ballet_scene.html'
s = p.read_text()
s = s[s.index('  <svg class="theatre-story"'):]
s = re.sub(r'    <g class="stage-ribbon[^\n]+\n', '', s)
s = s.replace("filename='ballet-stage-romantic.png'", "filename='ballet-island-complete.png'")
s = s.replace('x="207" y="72"', 'x="207" y="43"')
s = s.replace('x="378" y="304"', 'x="378" y="275"')
s = s.replace('    </defs>', '''      <filter id="silk-breeze" x="-25%" y="-15%" width="150%" height="135%" color-interpolation-filters="sRGB">
        <feTurbulence type="fractalNoise" baseFrequency=".012 .025" numOctaves="1" seed="7" result="silk-noise"/>
        <feOffset in="silk-noise" dx="0" dy="0" result="silk-wave" data-silk-offset=""/>
        <feDisplacementMap in="SourceGraphic" in2="silk-wave" scale="4" xChannelSelector="R" yChannelSelector="G" data-silk-displace=""/>
      </filter>
    </defs>''', 1)
marker = '    <g class="storybook-dancer">'
ribbons = '''    <g class="painted-ribbon silk-left"><image href="{{ url_for('static', filename='ballet-ribbon-silk.png') }}" x="156" y="393" width="55" height="165" filter="url(#silk-breeze)"/></g>
    <g class="painted-ribbon silk-right"><image href="{{ url_for('static', filename='ballet-ribbon-silk.png') }}" x="393" y="392" width="45" height="135" filter="url(#silk-breeze)"/></g>
'''
s = s.replace(marker, ribbons + marker)
head = '''{# Painted curtain and pearls share an undistorted image; island is contained. #}
<div class="ballet-theatre ballet-only" aria-hidden="true">
  <div class="pastel-curtain pastel-curtain-left"><img src="{{ url_for('static', filename='ballet-curtain-pastel.png') }}" alt="" width="736" height="2135"></div>
  <div class="pastel-curtain pastel-curtain-right"><img src="{{ url_for('static', filename='ballet-curtain-pastel.png') }}" alt="" width="736" height="2135"></div>
'''
p.write_text(head + s)
p = root/'templates/base.html'
s = p.read_text()
anchor = '<script defer src="{{ url_for(\'static\', filename=\'themes.js\', v=\'1\') }}"></script>'
s = s.replace(anchor, '<link rel="stylesheet" href="{{ url_for(\'static\', filename=\'ballet-refined.css\', v=\'1\') }}">\n<script defer src="{{ url_for(\'static\', filename=\'ballet-motion.js\', v=\'1\') }}"></script>\n' + anchor)
p.write_text(s)
