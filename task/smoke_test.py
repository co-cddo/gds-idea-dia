"""Smoke test for the pipeline task image: can what a task runs even be imported?

Run it inside the built image, with the image's own Python:

    docker run --rm -i --entrypoint python <image> - < task/smoke_test.py

It exists because the image holds only the base and `pipeline` dependencies, with
no Node, no CDK and no dev tools. A module that needs anything else works on a
laptop and fails only once a task starts. `--help` is not enough, because the CLI
imports its commands lazily.

Add a module to `TASK_MODULES` when a task command starts to use it.
"""

import importlib
import sys
import traceback

# Modules that `dia pipeline preflight` and the task commands run through.
TASK_MODULES = [
    "dia.cli",
    "dia.cli_helpers",
    "dia.naming",
    "dia.preflight",
    "dia.runtime_config",
]


def main() -> int:
    failed = []
    for module in TASK_MODULES:
        try:
            importlib.import_module(module)
        except Exception:
            failed.append(module)
            print(f"FAIL {module}", file=sys.stderr)
            traceback.print_exc()
        else:
            print(f"ok   {module}")

    if failed:
        print(f"\n{len(failed)} of {len(TASK_MODULES)} modules cannot be imported in this image.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
