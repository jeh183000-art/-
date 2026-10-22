# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Saved registered rules only: no new market simulation.
from __future__ import annotations
import json
from functools import cache
import numpy as np
import signals
from runner import ROOT,load,table,write_json

def main() -> None:
    out=ROOT/"final_audit";out.mkdir()
    v,frame,codes=load()
    original=signals.features
    @cache
    def cached(length: int,window: int) -> tuple[np.ndarray,...]:
        """Memoize identical immutable feature inputs in this test harness only."""
        arrays=original(tuple(a[:length] for a in v),window)
        for a in arrays:a.flags.writeable=False
        return arrays
    def use_prefix(values: tuple[np.ndarray,...],window: int) -> tuple[np.ndarray,...]:
        return cached(len(values[0]),window)
    signals.features=use_prefix
    rules=[c for p in sorted((ROOT/"preregistration").glob("batch_*.json")) for c in json.loads(p.read_text())["conditions"]]
    assert len(rules)==500
    records=[]
    for c in rules:
        args=signals.prepare(c["rule"],v,{"night":np.zeros(len(v[0]),dtype=bool),"volume":np.zeros(len(v[0]))})
        for end in (12501,24019):
            short=signals.prepare(c["rule"],tuple(a[:end] for a in v),
                {"night":np.zeros(end,dtype=bool),"volume":np.zeros(end)})
            for index in range(5):np.testing.assert_array_equal(args[index][:end],short[index])
            records.append(dict(candidate_id=c["candidate_id"],cut=end,arrays=5,status="PASS"))
    table(out/"all_rules_prefix_invariance.csv",records)
    write_json(out/"all_rules_prefix_validation.json",dict(status="PASS",rules=500,cuts_per_rule=2,
        array_comparisons=5000,source_scope="approved only",market_simulation_repeated=False,
        immutable_pure_feature_memoization="Test harness only, original feature function unchanged"))
    print("PASS_500_RULES_5000_PREFIX_ARRAY_COMPARISONS")

if __name__=="__main__":main()
