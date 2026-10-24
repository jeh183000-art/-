#!/usr/bin/env python3
"""Reproduce public inputs without requiring an existing sibling V1 project.

Download only public official Binance monthly archives and verify their hashes.
This script does not fit models, inspect direction accuracy, or place orders.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

import data_loader_v2 as loader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', choices=['development', 'holdout', 'both'],
                        default='development')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    if args.scope in ('development', 'both'):
        for interval in ('4h', '15m'):
            original = loader.EXISTING[interval]
            valid_original = (original.is_file() and
                              hashlib.sha256(original.read_bytes()).hexdigest() ==
                              loader.EXISTING_SHA[interval])
            if valid_original:
                continue
            directory = root / 'data' / 'reused_v1' / interval
            target = directory / f'BTCUSDT_{interval}_2022-01_2025-12.csv.gz'
            if not target.exists():
                subprocess.run([
                    sys.executable, str(root / 'reference' / f'v1_data_loader_{interval}.py'),
                    '--start', '2022-01', '--end', '2025-12', '--out', str(directory),
                    '--workers', '4',
                ], check=True)
            if hashlib.sha256(target.read_bytes()).hexdigest() != loader.EXISTING_SHA[interval]:
                raise SystemExit(f'Frozen V1 input hash mismatch: {interval}; stop without repair')
            loader.EXISTING[interval] = target
    sys.argv = [str(root / 'data_loader_v2.py'), '--scope', args.scope]
    loader.main()


if __name__ == '__main__':
    main()
