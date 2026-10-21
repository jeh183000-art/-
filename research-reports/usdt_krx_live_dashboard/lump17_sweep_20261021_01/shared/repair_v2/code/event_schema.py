from collections import Counter

import numpy as np

EVENT_KINDS = {1: 'ENTRY', 2: 'EXIT', 3: 'ROLL_CLOSE', 4: 'ROLL_OPEN', 5: 'SETTLE'}
ACCOUNT_PHASES = {'OPEN': 0, 'CLOSE': 1, 'SETTLEMENT': 2}


def compare_events(fresh, reference):
    grouped = {}
    for row in reference:
        assert row['kind'] in EVENT_KINDS.values(), row['kind']
        key = (int(row['row']), row['kind'], int(row['cycle_id']))
        bucket = grouped.setdefault(key, np.zeros(6))
        for at, field in enumerate(('spot_gross', 'future_segment', 'spot_fee', 'future_fee', 'spot_slippage', 'future_slippage')):
            bucket[at] += float(row[field])
    assert len(fresh) == len(grouped), 'EVENT_COUNT_MISMATCH'
    counts = Counter()
    maximum_difference = 0.
    for event in fresh:
        assert int(event[0]) in EVENT_KINDS
        kind = EVENT_KINDS[int(event[0])]
        key = (int(event[1]), kind, int(event[2]))
        assert key in grouped, ('MISSING_OR_DUPLICATED_EVENT', key)
        difference = float(np.max(np.abs(event[6:12] - grouped.pop(key))))
        assert difference < .01, ('EVENT_COST_PNL_DIFFERENCE', key, difference)
        maximum_difference = max(maximum_difference, difference)
        counts[kind] += 1
    assert not grouped
    assert all(counts[kind] > 0 for kind in EVENT_KINDS.values())
    assert counts['ROLL_CLOSE'] == counts['ROLL_OPEN']
    return dict(event_counts=dict(counts), max_event_difference_krw=maximum_difference)
