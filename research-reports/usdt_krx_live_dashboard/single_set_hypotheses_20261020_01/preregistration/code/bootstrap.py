# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2", "pandas==3.0.1"]
# ///
# Run with the existing Python 3.12.0 installation; no package installation needed.
from pathlib import Path
import os
import runpy
import site
import sys
import inspect

root = Path(__file__).resolve().parents[1]
for name in ("TEMP", "TMP", "TMPDIR", "XDG_CACHE_HOME", "NUMBA_CACHE_DIR", "PIP_CACHE_DIR", "UV_CACHE_DIR"):
    path = root / "runtime" / name.lower()
    path.mkdir(parents=True, exist_ok=True)
    os.environ[name] = str(path)
os.chdir(root)
sys.dont_write_bytecode = True
site.addsitedir("C:/Users/48733/AppData/Roaming/Python/Python312/site-packages")
sys.path.insert(0, str(root / "code"))
if "test" in sys.argv[1:]:
    import test_single
    count = 0
    for name, test in inspect.getmembers(test_single, inspect.isfunction):
        if name.startswith("test_"):
            test()
            count += 1
            print("PASS", name, flush=True)
    print("ALL_TESTS_PASS", count, flush=True)
else:
    runpy.run_path(str(root / "code/study.py"), run_name="__main__")
