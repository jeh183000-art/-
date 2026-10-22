# /// script
# requires-python = "==3.12.0"
# dependencies = ["numpy==2.2.6", "numba==0.61.2"]
# ///
# Run via bootstrap.py; state is updated only after observed CLOSE.
from __future__ import annotations
import numpy as np
from numba import njit

@njit(cache=True)
def state_exit(ret: float, best: float, stalled: float, options: np.ndarray) -> bool:
    """Net-return trail, or stalled-progress liquidation; no accounting mutation."""
    policy = int(options[6])
    armed = best >= options[7]
    if policy == 1:
        return armed and ret <= best-options[8]
    if policy == 2:
        return armed and stalled >= options[9] and ret <= best-options[8]
    return False
