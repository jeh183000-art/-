# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2", "pandas==3.0.1"]
# ///
# How to run: existing Python312/python.exe -B run_one_batch.py run_unlimited_sweep.py
"""Bound the existing runner to batch 143 without altering strategy modules."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import site
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

PROJECT: Final = Path("D:/Codex_Research/usdt_krx_live_dashboard")
STUDY: Final = PROJECT / "studies/unlimited_revalidation_20261017_01"
ENGINE: Final = PROJECT / "engine"
site.addsitedir("C:/Users/48733/AppData/Roaming/Python/Python312/site-packages")
sys.path.insert(0, str(ENGINE))
sys.dont_write_bytecode = True

import research_storage as storage

storage.STORAGE = storage.resolve_research_paths()
storage.prepare_research_runtime(storage.STORAGE)

receipt = json.loads((STUDY / "batch_0142/publication_receipt.json").read_text())
assert receipt["status"] == "PUBLISHED_VERIFIED"
assert not (STUDY / "batch_0143").exists(), "Refuse to repeat an existing attempt"
assert not (STUDY / "batch_0144").exists(), "Unexpected study progress"

runner_path = ENGINE / "run_unlimited_sweep.py"
tree = ast.parse(runner_path.read_text(encoding="utf-8"), filename=str(runner_path))
main_function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
batch_loops = [node for node in main_function.body if isinstance(node, ast.For) and ast.unparse(node.target) == "start"]
assert len(batch_loops) == 1
batch_loop = batch_loops[0]
assert ast.unparse(batch_loop.iter) == "range(0, len(grid), 50)"
batch_loop.iter = ast.parse("range(7100, 7150, 50)", mode="eval").body
wait_loops = [node for node in batch_loop.body if isinstance(node, ast.While)]
assert len(wait_loops) == 1 and ast.unparse(wait_loops[0].test) == "not receipt.exists()"
batch_loop.body[batch_loop.body.index(wait_loops[0])] = ast.Return(value=None)
registry_comparisons = [node for node in ast.walk(main_function) if isinstance(node, ast.Compare) and ast.unparse(node) == "json.loads(registry.read_text()) == settings"]
assert len(registry_comparisons) == 1
registry_comparisons[0].comparators[0] = ast.parse("json.loads(json.dumps(settings))", mode="eval").body
ast.fix_missing_locations(tree)

namespace = {"__name__": "bounded_existing_runner", "__file__": str(runner_path)}
exec(compile(tree, str(runner_path), "exec"), namespace)
generated_path = STUDY / "engine_unlimited_generated.py"
generated_before = hashlib.sha256(generated_path.read_bytes()).hexdigest()
preregistration_before = hashlib.sha256((STUDY / "preregistration.json").read_bytes()).hexdigest()

def load_frozen_engine(source: Path, output: Path) -> ModuleType:
    """Load the already audited kernel; never regenerate or overwrite it."""
    assert source == storage.STORAGE.source / "paper_engine.py"
    assert output == generated_path
    spec = importlib.util.spec_from_file_location("frozen_unlimited_batch142", generated_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

namespace["build"] = load_frozen_engine
sys.argv[0] = str(runner_path)
with namespace["claim_study"]():
    namespace["main"]()

assert hashlib.sha256(generated_path.read_bytes()).hexdigest() == generated_before
assert hashlib.sha256((STUDY / "preregistration.json").read_bytes()).hexdigest() == preregistration_before
assert not (STUDY / "batch_0144").exists()
ready = json.loads((STUDY / "batch_0143/READY.json").read_text())
assert ready["batch"] == 143 and ready["completed_conditions"] == 7150
print("BOUNDED_BATCH_0143_FINISHED_NO_0144", flush=True)

