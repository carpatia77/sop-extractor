"""Shared pytest setup for the whole tests/ suite.

Puts scripts/ on sys.path once, here, instead of every test module repeating
`sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))`
individually. conftest.py is imported by pytest before collecting test
modules in this directory, so the path is set up before any test file's own
`from <script_module> import ...` runs.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
