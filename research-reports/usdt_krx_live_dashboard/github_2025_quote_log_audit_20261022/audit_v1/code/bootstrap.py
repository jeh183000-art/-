import os,runpy,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for key in ('TEMP','TMP','TMPDIR','XDG_CACHE_HOME','NUMBA_CACHE_DIR','PIP_CACHE_DIR','UV_CACHE_DIR'):
    folder=root/'runtime'/key.lower();folder.mkdir(parents=True,exist_ok=True);os.environ[key]=str(folder)
os.chdir(root);sys.dont_write_bytecode=True;sys.path.insert(0,str(root/'code'))
target=root/'code'/sys.argv[1];sys.argv=sys.argv[1:];runpy.run_path(str(target),run_name='__main__')
