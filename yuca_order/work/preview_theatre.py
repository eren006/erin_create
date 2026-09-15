from pathlib import Path
import sqlite3
root=Path('/Users/erinren/erin_creation/yuca_order')
source=(root/'app.py').read_text().replace('threading.Thread(target=_expiry_sweep_loop, daemon=True).start()','# preview')
db=root/'work/theatre-preview.db'
src=sqlite3.connect(f'file:{root}/order_data.db?mode=ro',uri=True);dst=sqlite3.connect(db);src.backup(dst);src.close();dst.close()
source=source.replace('os.path.join(os.path.dirname(__file__), "order_data.db")',repr(str(db)))
ns={'__name__':'theatre_preview','__file__':str(root/'app.py')};exec(compile(source,str(root/'app.py'),'exec'),ns)
app=ns['app'];app.template_folder=str(root/'templates');app.static_folder=str(root/'static');app.config['TEMPLATES_AUTO_RELOAD']=True;app.jinja_env.auto_reload=True;app.run(port=5238,debug=False)
