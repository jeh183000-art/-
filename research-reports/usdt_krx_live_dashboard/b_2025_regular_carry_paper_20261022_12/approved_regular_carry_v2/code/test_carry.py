# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: python -B code/bootstrap.py test_carry.py
from carry_audit import tests
from common import OUT,save
proof=tests();save(OUT/'tests.json',proof);print(proof)
