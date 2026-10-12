"""Run offline tests with disposable files confined to the project workspace."""
import pathlib
import sys
import tempfile
import unittest

root=pathlib.Path(__file__).resolve().parents[1]
scratch=root/'tests'/'.agv_test_tmp'
scratch.mkdir(exist_ok=True)
assert scratch.resolve().is_relative_to(root)
prior=tempfile.tempdir
with tempfile.TemporaryDirectory(dir=scratch,prefix='run_') as folder:
    assert pathlib.Path(folder).resolve().is_relative_to(root)
    tempfile.tempdir=folder
    try:
        suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_agv*.py')
        result=unittest.TextTestRunner(verbosity=1).run(suite)
    finally:
        tempfile.tempdir=prior
sys.exit(0 if result.wasSuccessful() else 1)
