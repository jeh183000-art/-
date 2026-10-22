# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Run: python -B code/bootstrap.py metric_tests.py
from __future__ import annotations
import csv
from pathlib import Path
from typing import Literal, TypedDict
import numpy as np
from numpy.typing import NDArray

class ProfitSummary(TypedDict):
    profit_factor_krw: float | None
    profit_factor_status: Literal['FINITE','INFINITE_NO_LOSSES','UNDEFINED_NO_COMPLETED_PNL']
    completed_gross_profit_krw: float
    completed_gross_loss_krw: float

def profit_summary(nets: NDArray[np.float64]) -> ProfitSummary:
    """PF uses completed-cycle net KRW after all modeled costs; infinity is explicit."""
    gains=float(np.sum(nets[nets>0]));losses=float(-np.sum(nets[nets<0]))
    if losses>0:
        return ProfitSummary(profit_factor_krw=gains/losses,profit_factor_status='FINITE',completed_gross_profit_krw=gains,completed_gross_loss_krw=losses)
    if gains>0:
        return ProfitSummary(profit_factor_krw=None,profit_factor_status='INFINITE_NO_LOSSES',completed_gross_profit_krw=gains,completed_gross_loss_krw=0.)
    return ProfitSummary(profit_factor_krw=None,profit_factor_status='UNDEFINED_NO_COMPLETED_PNL',completed_gross_profit_krw=0.,completed_gross_loss_krw=0.)

def verify_cycle_pf(path: Path, expected: ProfitSummary) -> ProfitSummary:
    """Replay PF independently from saved cycle CSV, using Python sums instead of numpy."""
    import gzip
    with gzip.open(path,'rt',encoding='utf8',newline='') as stream:
        nets=[float(row['net']) for row in csv.DictReader(stream)]
    gains=sum(x for x in nets if x>0);losses=-sum(x for x in nets if x<0)
    assert abs(gains-expected['completed_gross_profit_krw'])<.01
    assert abs(losses-expected['completed_gross_loss_krw'])<.01
    if losses>0:
        assert expected['profit_factor_status']=='FINITE'
        pf=expected['profit_factor_krw'];assert pf is not None and abs(gains/losses-pf)<1e-10
    else:
        assert expected['profit_factor_krw'] is None
        assert expected['profit_factor_status']==('INFINITE_NO_LOSSES' if gains>0 else 'UNDEFINED_NO_COMPLETED_PNL')
    return expected
