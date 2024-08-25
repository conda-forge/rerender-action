"""
This script will run a live integration test of the version update
action. To use it do the following

1. Make sure you have a valid github token in your environment called
   "GH_TOKEN".
2. Make surre you have pushed the new version of the action to the `dev`
   docker image tag.

   You can run

      docker build -t condaforge/webservices-dispatch-action:dev .
      docker push condaforge/webservices-dispatch-action:dev

   or pass `--build-and-push` when running the test script.

Then you can execute this script and it will report the results.

## setup

 - The script uses a PR on the `conda-forge/cf-autotick-bot-test-package-feedstock`.
 - The head ref for this PR is on a fork of that feedstock in the regro
   organization.
 - It works by pushing a change to the PR branch that would cause a rerender
   to happen.
 - Then we trigger the rerender and check that it happened.

"""

import argparse
import contextlib
import json
import os
import subprocess
import tempfile
import time

import requests

BRANCH = "version-update-live-test"
PR_NUM = 483


@contextlib.contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(previous_dir)


def _change_version(new_version="0.13", branch="main"):
    import random

    new_sha = "".join(random.choices("0123456789abcdef", k=64))

    print("changing the version to an old one...", flush=True)
    subprocess.run(f"git checkout {branch}", shell=True, check=True)

    new_lines = []
    with open("recipe/meta.yaml", "r") as fp:
        for line in fp.readlines():
            if line.startswith("{% set version ="):
                new_lines.append('{%% set version = "%s" %%}\n' % new_version)
            elif line.startswith("  sha256: "):
                new_lines.append("  sha256: %s\n" % new_sha)
            else:
                new_lines.append(line)
    with open("recipe/meta.yaml", "w") as fp:
        fp.write("".join(new_lines))

    print("staging file..", flush=True)
    subprocess.run("git add recipe/meta.yaml", shell=True, check=True)
    subprocess.run(
        "git commit " "--allow-empty " "-m " "'[ci skip] moved version to older 0.13'",
        shell=True,
        check=True,
    )

    print("push to origin...", flush=True)
    subprocess.run("git push", shell=True, check=True)


def _merge_main_to_branch():
    print("merging main into branch...", flush=True)
    subprocess.run("git checkout main", shell=True, check=True)
    subprocess.run("git pull", shell=True, check=True)
    subprocess.run(f"git checkout {BRANCH}", shell=True, check=True)
    subprocess.run("git pull", shell=True, check=True)
    subprocess.run(
        "git merge --no-edit --strategy-option theirs main",
        shell=True,
        check=True,
    )
    subprocess.run("git push", shell=True, check=True)


def _run_test(version):
    print(
        "sending repo dispatch event to update "
        "the version w/ version=%r..." % version,
        flush=True,
    )
    headers = {
        "authorization": "Bearer %s" % os.environ["GH_TOKEN"],
        "content-type": "application/json",
    }
    r = requests.post(
        (
            "https://api.github.com/repos/conda-forge/"
            "cf-autotick-bot-test-package-feedstock/dispatches"
        ),
        data=json.dumps(
            {
                "event_type": "version_update",
                "client_payload": {"pr": PR_NUM, "input_version": version},
            }
        ),
        headers=headers,
    )
    print("    dispatch event status code:", r.status_code, flush=True)
    assert r.status_code == 204

    print("sleeping for a few minutes to let the version update happen...", flush=True)
    tot = 0
    while tot < 180:
        time.sleep(10)
        tot += 10
        print("    slept %s seconds out of 180" % tot, flush=True)

    print("checking repo for the version update...", flush=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        with pushd(tmpdir):
            print("cloning...", flush=True)
            subprocess.run(
                "git clone "
                "https://github.com/conda-forge/"
                "cf-autotick-bot-test-package-feedstock.git",
                shell=True,
                check=True,
            )

            with pushd("cf-autotick-bot-test-package-feedstock"):
                print("checkout branch...", flush=True)
                subprocess.run(
                    f"git checkout {BRANCH}",
                    shell=True,
                    check=True,
                )

                print("checking the git history", flush=True)
                c = subprocess.run(
                    ["git", "log", "--pretty=oneline", "-n", "1"],
                    capture_output=True,
                    check=True,
                )
                output = c.stdout.decode("utf-8")
                print("    last commit:", output.strip(), flush=True)
                assert "MNT:" in output or "ENH " in output

    print("tests passed!", flush=True)


def _change_action_branch(branch):
    print("moving repo to %s action" % branch, flush=True)
    subprocess.run("git checkout main", shell=True, check=True)
    subprocess.run("git pull", shell=True, check=True)

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

    print("committing...", flush=True)
    subprocess.run("git add .github/workflows/webservices.yml", shell=True, check=True)
    subprocess.run(
        "git commit "
        "--allow-empty "
        "-m "
        "'[ci skip] move rerender action to branch %s'" % branch,
        shell=True,
        check=True,
    )

    print("push to origin...", flush=True)
    subprocess.run("git push", shell=True, check=True)


parser = argparse.ArgumentParser(
    description="Run a live test of the rerendering code",
)
parser.add_argument(
    "--build-and-push",
    help="build and push the docker image to the dev tag before running the tests",
    action="store_true",
)
parser.add_argument("--version", type=str, help="if given, update to this version")
args = parser.parse_args()

if args.build_and_push:
    subprocess.run(
        "docker build -t condaforge/webservices-dispatch-action:dev .",
        shell=True,
        check=True,
    )
    subprocess.run(
        "docker push condaforge/webservices-dispatch-action:dev",
        shell=True,
        check=True,
    )


print("making an edit to the head ref...", flush=True)
with tempfile.TemporaryDirectory() as tmpdir:
    with pushd(tmpdir):
        print("cloning...", flush=True)
        subprocess.run(
            "git clone "
            "https://x-access-token:${GH_TOKEN}@github.com/conda-forge/"
            "cf-autotick-bot-test-package-feedstock.git",
            shell=True,
            check=True,
        )

        with pushd("cf-autotick-bot-test-package-feedstock"):
            try:
                _change_action_branch("dev")
                _change_version(new_version="0.13", branch="main")
                _merge_main_to_branch()
                _change_version(new_version="0.13", branch=BRANCH)
                _run_test(args.version)
            finally:
                _change_action_branch("main")
                _change_version(new_version="0.14", branch="main")
                _merge_main_to_branch()
                _change_version(new_version="0.13", branch=BRANCH)
