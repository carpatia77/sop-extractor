"""Shared pytest setup for the whole tests/ suite.

Puts scripts/ on sys.path once, here, instead of every test module repeating
`sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))`
individually. conftest.py is imported by pytest before collecting test
modules in this directory, so the path is set up before any test file's own
`from <script_module> import ...` runs.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

# Import sf_embeddings via both paths so we can patch both module objects.
# sf_matcher imports from "scripts.chavruta.sf_embeddings", tests import
# from "chavruta.sf_embeddings" — they are distinct module objects.
import scripts.chavruta.sf_embeddings as _mod_scripts
import chavruta.sf_embeddings as _mod_chavruta

_ALL_SF_EMBEDDINGS_MODULES = [_mod_scripts, _mod_chavruta]


@pytest.fixture(autouse=True)
def _isolate_disk_cache(tmp_path):
    """Redirect ALL sf_embeddings disk writes to tmp_path.

    Patches _disk_put and _DEFAULT_CACHE_DIR on BOTH module objects
    (scripts.chavruta.sf_embeddings and chavruta.sf_embeddings) to
    prevent any test from writing to ~/.cache/sopx/embeddings/.
    """
    originals = []
    for mod in _ALL_SF_EMBEDDINGS_MODULES:
        originals.append((mod, mod._disk_put, mod._DEFAULT_CACHE_DIR))
        mod._DEFAULT_CACHE_DIR = tmp_path
        _orig = mod._disk_put
        mod._disk_put = lambda key, emb, meta, cache_dir=None, _o=_orig, _p=tmp_path: _o(key, emb, meta, _p)
    yield
    for mod, orig_put, orig_default in originals:
        mod._disk_put = orig_put
        mod._DEFAULT_CACHE_DIR = orig_default
