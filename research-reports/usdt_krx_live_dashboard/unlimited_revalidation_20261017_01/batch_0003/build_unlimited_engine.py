# /// script
# requires-python = ">=3.12"
# dependencies = ["numba", "numpy", "pandas"]
# ///
"""Generate a versioned research engine by explicit audited changes to the original AST."""
from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path


class ResearchKernel(ast.NodeTransformer):
    def __init__(self) -> None:
        self.guards = 0
        self.spacings = 0
        self.marks = 0

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if node.value == 0.2:
            self.spacings += 1
            return ast.copy_location(ast.Name(id="stage_spacing", ctx=ast.Load()), node)
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        names = {"MAX_POSITIONS": "stage_capacity", "MAX_STAGES": "stage_capacity", "EVENT_CAPACITY": "event_capacity", "TRADE_CAPACITY": "trade_capacity"}
        if node.id in names:
            return ast.copy_location(ast.Name(id=names[node.id], ctx=node.ctx), node)
        return node

    def visit_If(self, node: ast.If) -> ast.AST:
        text = ast.unparse(node.test)
        if text == "npos >= MAX_POSITIONS":
            node.test = ast.parse("capital_limited and npos >= 5", mode="eval").body
            self.guards += 1
        if "spot_cash < spot_notional" in text or "future_equity - future_fee - future_slip < required_initial" in text:
            node.test = ast.BoolOp(op=ast.And(), values=[ast.Name(id="capital_limited", ctx=ast.Load()), node.test])
            self.guards += 1
        if text == "k_max >= MAX_STAGES":
            return ast.copy_location(ast.parse("if k_max >= stage_capacity:\n    raise RuntimeError('STAGE_STORAGE_OVERFLOW')").body[0], node)
        return self.generic_visit(node)

    def visit_For(self, node: ast.For) -> ast.AST:
        original = ast.unparse(node.iter)
        node = self.generic_visit(node)
        if original == "range(pending_entry_count)":
            node.body.extend(ast.parse("if one_fill_per_bar:\n    break").body)
        return node

    def visit_Assign(self, node: ast.Assign) -> ast.AST | list[ast.AST]:
        original = ast.unparse(node)
        node = self.generic_visit(node)
        if original == "summary = np.zeros(45, dtype=np.float64)":
            return ast.copy_location(ast.parse("summary = np.zeros(52, dtype=np.float64)").body[0], node)
        if original.startswith("summary[14] ="):
            return ast.copy_location(ast.parse("summary[14] = net_liq / INITIAL_CAPITAL * 100.0 if INITIAL_CAPITAL > 0 else np.nan").body[0], node)
        if original.startswith("equity, future_unreal = _equity("):
            call = node.value
            spot, future = ast.unparse(call.args[-2]), ast.unparse(call.args[-1])
            self.marks += 1
            extra = ast.parse(f"update_risk(risk, direction, lots, npos, {spot}, {future}, spot_cash, futures_cash, initial_rate[i], maintenance_rate[i], equity - INITIAL_CAPITAL)").body[0]
            return [node, extra]
        return node


def build(source: Path, destination: Path):
    tree = ast.parse(source.read_text(encoding="utf-8"))
    transforms = ResearchKernel()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {"INITIAL_SPOT", "INITIAL_FUTURES", "INITIAL_CAPITAL"}:
                    node.value = ast.Constant(value=0.0)
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    for kw in decorator.keywords:
                        if kw.arg == "cache":
                            kw.value = ast.Constant(value=True)
        if isinstance(node, ast.FunctionDef) and node.name == "simulate_one":
            node.args.args.extend(ast.arg(arg=name) for name in ("capital_limited", "stage_spacing", "one_fill_per_bar", "stage_capacity", "event_capacity", "trade_capacity"))
            transforms.visit(node)
            node.body.insert(0, ast.parse("risk = np.zeros(7, dtype=np.float64)").body[0])
            node.body.insert(-1, ast.parse("summary[45:52] = risk").body[0])
    tree.body.insert(0, ast.ImportFrom(module="unlimited_risk", names=[ast.alias(name="update_risk")], level=0))
    future = next(node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module == "__future__")
    tree.body.remove(future)
    tree.body.insert(0, future)
    ast.fix_missing_locations(tree)
    assert transforms.guards == 3, transforms.guards
    assert transforms.spacings == 6, transforms.spacings
    assert transforms.marks == 3, transforms.marks
    generated = ast.unparse(tree) + "\n"
    if destination.exists():
        assert destination.read_text(encoding="utf-8") == generated, "Use a new study ID for changed generated code"
    else:
        destination.write_text(generated, encoding="utf-8")
    audit = {"original_cash_margin_cap_guards_gated": transforms.guards, "spacing_literals_parameterized": transforms.spacings, "open_close_settlement_risk_marks": transforms.marks, "research_initial_cash": 0, "funding_behavior": "capital_limited=False bypasses spot cash, initial margin, and 5-contract admission branches; negative bookkeeping cash is permitted", "stage_behavior": "capacity is storage only; overflow raises instead of truncating stages", "event_trade_buffers": "retry from scratch with larger buffers when overflow is reported; never accept truncated ledgers"}
    destination.with_suffix(".audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    spec = importlib.util.spec_from_file_location(destination.stem, destination)
    if spec is None or spec.loader is None:
        raise RuntimeError("Generated engine cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
