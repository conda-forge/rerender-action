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


def _merge_main_to_branch(branch, verbose=False):
    if verbose:
        print("merging main into branch...", flush=True)
    subprocess.run(["git", "checkout", "main"], check=True)
    subprocess.run(["git", "pull"], check=True)
    subprocess.run(["git", "checkout", branch], check=True)
    subprocess.run(["git", "pull"], check=True)
    subprocess.run(
        ["git", "merge", "--no-edit", "--strategy-option", "theirs", "main"],
        check=True,
    )
    subprocess.run(["git", "push"], check=True)


def _change_action_branch(branch, verbose=False):
    if verbose:
        print("moving repo to %s action" % branch, flush=True)
    subprocess.run(["git", "checkout", "main"], check=True, capture_output=True)

    data = (
        branch,
        "rerendering_github_token: ${{ secrets.RERENDERING_GITHUB_TOKEN }}",
        "ssh_private_key: ${{ secrets.CONDA_FORGE_WRITE_SSH_DEPLOY_KEY }}"
        if branch != "main"
        else "",
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
          %s
"""
            % data
        )

    if verbose:
        print("committing...", flush=True)
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

    if verbose:
        print("push to origin...", flush=True)
    subprocess.run(["git", "pull"], check=True, capture_output=True)
    subprocess.run(["git", "push"], check=True, capture_output=True)


@pytest.fixture(scope="session")
def setup_test_action(pytestconfig):
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
                try:
                    _change_action_branch(pytestconfig.getoption("branch"))
                    yield
                finally:
                    _change_action_branch("main")


def pytest_addoption(parser):
    parser.addoption("--branch", action="store")
