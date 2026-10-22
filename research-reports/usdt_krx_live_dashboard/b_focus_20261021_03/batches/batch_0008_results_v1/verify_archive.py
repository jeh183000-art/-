# /// script
# requires-python = "==3.12.0"
# dependencies = []
# ///
# Run: python -B operations/verify_archive.py PATH_TO_RESULT_PACKET
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import zipfile

root=Path(sys.argv[1])
parts=json.loads((root/'archive_parts.json').read_text())
joined=hashlib.sha256();size=0
for part in parts['parts']:
    raw=(root/part['path']).read_bytes()
    assert len(raw)==part['bytes'] and hashlib.sha256(raw).hexdigest()==part['sha256']
    joined.update(raw);size+=len(raw)
assert size==parts['archive_bytes'] and joined.hexdigest()==parts['archive_sha256']
archive=root.parents[1]/'batches'/root.name.removesuffix('_results_v1')/'full_ledgers.tar'
assert archive.stat().st_size==size and hashlib.sha256(archive.read_bytes()).hexdigest()==joined.hexdigest()
with (root/'archive_inventory.csv').open(encoding='utf8',newline='') as stream:
    inventory={row['path']:row for row in csv.DictReader(stream)}
checked=0;npz=0
with tarfile.open(archive,'r') as stream:
    for member in stream:
        assert member.isfile() and member.name in inventory
        with stream.extractfile(member) as source:raw=source.read()
        row=inventory[member.name]
        assert len(raw)==int(row['bytes']) and hashlib.sha256(raw).hexdigest()==row['sha256']
        if member.name.endswith('.npz'):
            with zipfile.ZipFile(io.BytesIO(raw)) as z:assert z.testzip() is None
            npz+=1
        checked+=1
assert checked==len(inventory) and npz==100
record=dict(status='PASS_LOSSLESS_ALL_MEMBERS_AND_NPZ_CRC',files=checked,npz_archives=npz,
            archive_bytes=size,archive_sha256=joined.hexdigest())
with (root/'archive_validation.json').open('x',encoding='utf8') as out:json.dump(record,out,indent=2)
print(json.dumps(record),flush=True)
