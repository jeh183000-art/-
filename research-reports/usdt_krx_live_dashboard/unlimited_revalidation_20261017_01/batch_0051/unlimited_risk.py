# /// script
# requires-python = ">=3.12"
# dependencies = ["numba", "numpy"]
# ///
from numba import njit


@njit(cache=True)
def update_risk(risk, direction, lots, npos, spot, future, spot_cash, future_cash, initial_rate, maintenance_rate, equity):
    open_net = 0.0
    notional = 0.0
    future_unrealized = 0.0
    observed_gap = (spot / future - 1.0) * 100.0
    for slot in range(npos):
        open_net += direction * (spot - lots[slot, 7]) * 10000.0
        open_net += lots[slot, 10] + direction * (lots[slot, 8] - future) * 10000.0
        open_net -= lots[slot, 11] + lots[slot, 12]
        notional += lots[slot, 7] * 10000.0
        future_unrealized += direction * (lots[slot, 8] - future) * 10000.0
        risk[4] = max(risk[4], direction * (lots[slot, 15] - observed_gap))
    risk[0] = max(risk[0], -open_net)
    risk[1] = max(risk[1], notional)
    risk[2] = max(risk[2], npos * future * 10000.0 * maintenance_rate)
    risk[3] = max(risk[3], npos * future * 10000.0 * initial_rate - future_cash - future_unrealized)
    risk[5] = max(risk[5], -spot_cash)
    risk[6] = min(risk[6], equity)
