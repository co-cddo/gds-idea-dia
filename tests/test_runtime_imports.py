"""What a pipeline task imports must not need the CDK.

Importing `aws_cdk` starts a Node process (through jsii), and the task image has no
Node. Each module is imported in a fresh interpreter in which the CDK cannot be
imported, which is what the image looks like.
"""

import runpy
import subprocess
import sys
from pathlib import Path

import pytest

# The same list the image smoke test checks (task/smoke_test.py), so the two cannot drift.
TASK_MODULES = runpy.run_path(str(Path(__file__).parent.parent / "task" / "smoke_test.py"))["TASK_MODULES"]

_SCRIPT = """
import importlib
import sys

# Make any import of the CDK fail, as it would where Node is missing.
sys.modules["aws_cdk"] = None
sys.modules["constructs"] = None

importlib.import_module({module!r})
"""


@pytest.mark.parametrize("module", TASK_MODULES)
def test_task_module_imports_without_the_cdk(module):
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT.format(module=module)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
