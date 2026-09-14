from pathlib import Path
import subprocess, base64, datetime, tarfile, tempfile
root=Path('/Users/erinren/erin_creation/yuca_order')
files=['templates/index.html','templates/base.html','templates/_ballet_scene.html','static/ballet.css','static/ballet-refined.css','static/ballet-motion.js','static/ballet-island-complete.webp','static/ballet-curtain-pastel.webp','static/ballet-dancer-pastel.webp','static/ballet-ribbon-silk.webp','static/ballet-swan.webp','static/ballet-masthead-pastel.webp','static/ballet-ornaments-pastel.webp']
tag='ballet-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
remote='C:/Users/Administrator/yuca_order'
staging=remote+'/deploy-backups/'+tag

def ps(script):
 encoded=base64.b64encode(("$ErrorActionPreference='Stop'; "+script).encode('utf-16le')).decode()
 subprocess.run(['ssh','-o','BatchMode=yes','yulequan-server','powershell -NoProfile -NonInteractive -EncodedCommand '+encoded],check=True)
ps(f"New-Item -ItemType Directory -Force -Path '{staging}/incoming','{staging}/previous' | Out-Null")
with tempfile.TemporaryDirectory(prefix='ballet-release-') as temporary:
 archive=Path(temporary)/'release.tar.gz'
 with tarfile.open(archive,'w:gz') as bundle:
  for f in files:
   bundle.add(root/f,arcname=Path(f).name)
 subprocess.run(['scp',str(archive),'yulequan-server:'+staging+'/release.tar.gz'],check=True)
ps(f"tar -xzf '{staging}/release.tar.gz' -C '{staging}/incoming'; if ($LASTEXITCODE -ne 0) {{ throw 'Unable to extract release' }}")
file_list=','.join("'"+f+"'" for f in files)
context=f"$root='{remote}'; $release='{staging}'; $files=@({file_list}); "
ps(context+"foreach ($f in $files) { $src=Join-Path $root $f; $name=Split-Path $f -Leaf; if (Test-Path $src) { Copy-Item $src ($release+'/previous/'+$name) } }")
ps(context+"foreach ($f in $files) { $name=Split-Path $f -Leaf; Copy-Item ($release+'/incoming/'+$name) (Join-Path $root $f) -Force }")
print('Published refined theme and illustration assets. Backup:',staging,flush=True)
subprocess.run(['ssh','yulequan-server','nssm restart yucaorder'],check=True)
