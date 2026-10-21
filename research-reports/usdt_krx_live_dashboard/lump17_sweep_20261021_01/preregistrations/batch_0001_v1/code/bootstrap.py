# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
import os
import runpy
import site
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
for key in ('TEMP','TMP','TMPDIR','XDG_CACHE_HOME','NUMBA_CACHE_DIR','PIP_CACHE_DIR','UV_CACHE_DIR'):
    directory=root/'runtime'/key.lower();directory.mkdir(parents=True,exist_ok=True);os.environ[key]=str(directory)
os.chdir(root)
site.addsitedir('C:/Users/48733/AppData/Roaming/Python/Python312/site-packages')
sys.dont_write_bytecode=True
sys.path.insert(0,str(root/'code'))
target=root/'code'/sys.argv[1]
sys.argv=sys.argv[1:]
runpy.run_path(str(target),run_name='__main__')
