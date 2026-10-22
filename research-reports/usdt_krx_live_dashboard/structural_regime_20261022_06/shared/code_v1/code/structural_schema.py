# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6"]
# ///
# Frozen rules in settings.json are the authoritative parameter boundary.
from typing import Literal
from path_schema import PathRule

class StructuralRule(PathRule, total=False):
    structure: Literal["driver", "residual", "momentum", "trail", "opportunity", "selector"]
    entry_model: Literal["fixed", "residual"]
    lookback: int
    driver: Literal["spot", "future", "balanced"]
    driver_share: float
    impulse_pp: float
    entry_width: float
    inner_width: float
    center_drift_limit: float
    reversal_entry: bool
    trailing_arm_pct: float
    trailing_giveback_pct: float
    stalled_trail_minutes: float
    selector_horizon: int
    selector_memory: int
    selector_min_edge_pp: float
    selector_update_observations: int
    volatility_floor_pp: float
    cooldown_minutes: float
