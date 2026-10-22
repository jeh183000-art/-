# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy==2.2.6"]
# ///
# How to run: python -B code/bootstrap.py test_regressions.py
from verify_quote_book import regressions
from common import OUT,save
proof=regressions();save(OUT/'regression_tests.json',proof);print(proof)
