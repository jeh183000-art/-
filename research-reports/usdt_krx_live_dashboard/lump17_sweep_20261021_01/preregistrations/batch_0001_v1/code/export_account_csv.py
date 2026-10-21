import argparse
import csv
import gzip
from pathlib import Path

import numpy as np

from runner import LEDGER_FIELDS

parser=argparse.ArgumentParser()
parser.add_argument('source',type=Path)
parser.add_argument('destination',type=Path)
args=parser.parse_args()
ledger=np.load(args.source)['ledger']
opener=gzip.open if str(args.destination).endswith('.gz') else open
with opener(args.destination,'xt',encoding='utf8',newline='') as stream:
    writer=csv.writer(stream);writer.writerow(['input_row','phase',*LEDGER_FIELDS])
    for i in range(len(ledger)):
        for phase in range(3):
            if np.isfinite(ledger[i,phase,0]):writer.writerow([i,['OPEN','CLOSE','SETTLEMENT'][phase],*ledger[i,phase]])
