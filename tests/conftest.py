import contextlib
import os
import subprocess
import tempfile

import pytest


@contextlib.contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(previous_dir)


def _change_action_branch(branch):
    subprocess.run(["git", "checkout", "main"], check=True, capture_output=True)

    data = (
        branch,
        "rerendering_github_token: ${{ secrets.RERENDERING_GITHUB_TOKEN }}",
    )

    with open(".github/workflows/webservices.yml", "w") as fp:
        fp.write(
            """\
on: repository_dispatch

jobs:
  webservices:
    runs-on: ubuntu-latest
    name: webservices
    steps:
      - name: webservices
        id: webservices
        uses: conda-forge/webservices-dispatch-action@%s
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          %s
"""
            % data
        )

    subprocess.run(
        ["git", "add", "-f", ".github/workflows/webservices.yml"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "commit",
            "--allow-empty",
            "-m",
            "[ci skip] move rerender action to branch %s" % branch,
        ],
        check=True,
        capture_output=True,
    )

    subprocess.run(["git", "pull"], check=True, capture_output=True)
    subprocess.run(["git", "push"], check=True, capture_output=True)


@pytest.fixture(scope="session")
def setup_test_action():
    with tempfile.TemporaryDirectory() as tmpdir:
        with pushd(tmpdir):
            subprocess.run(
                [
                    "git",
                    "clone",
                    f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/conda-forge/conda-forge-webservices.git",
                ],
                check=True,
                capture_output=True,
            )

            with pushd("conda-forge-webservices"):
                yield _change_action_branch
                _change_action_branch("main")


def pytest_addoption(parser):
    parser.addoption("--branch", action="store")
