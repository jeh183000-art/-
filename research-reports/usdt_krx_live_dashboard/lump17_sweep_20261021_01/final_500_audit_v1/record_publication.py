import json
import sys

from runner import ROOT, write_json

number=int(sys.argv[1]);stage=sys.argv[2];commit=sys.argv[3];files=int(sys.argv[4])
assert 1<=number<=10 and stage in ('prereg','results') and len(commit)==40
registration=json.loads((ROOT/'preregistration'/f'batch_{number:04d}.json').read_text())
receipt=dict(status='PUBLISHED_VERIFIED',commit=commit,remote_files_verified=files,
             grid_sha256=registration['grid_sha256'],remote_bytes_and_sha256_verified=True,
             batch=f'batch_{number:04d}',stage=stage,new_conditions_total=number*50 if stage=='results' else (number-1)*50)
write_json(ROOT/'publication'/f'batch_{number:04d}_{stage}_verified.json',receipt)
print(json.dumps(receipt),flush=True)
