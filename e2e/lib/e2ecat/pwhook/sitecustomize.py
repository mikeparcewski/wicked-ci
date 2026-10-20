"""Loaded by Python at startup when this directory is on PYTHONPATH (the e2e runner puts it there for a
studio journey). It does nothing unless E2E_PW_DIR is set; see e2e_pw.py."""
import os

if os.environ.get("E2E_PW_DIR"):
    try:
        import e2e_pw

        e2e_pw.install()
    except Exception as _e:  # never break the process the hook rides in
        import sys

        sys.stderr.write("e2e playwright hook disabled: %s\n" % _e)
