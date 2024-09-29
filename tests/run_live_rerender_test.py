"""
This script will run a live integration test of the rerendering
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
import glob
import json
import os
import subprocess
import tempfile
import time

import requests
from conftest import (
    TEST_DEPLOY_KEY,
    _change_action_branch,
    _merge_main_to_branch,
    pushd,
)


def _run_test():
    print("sending repo dispatch event to rerender...")
    headers = {
        "authorization": "Bearer %s" % os.environ["GH_TOKEN"],
        "content-type": "application/json",
    }
    r = requests.post(
        (
            "https://api.github.com/repos/conda-forge/"
            "cf-autotick-bot-test-package-feedstock/dispatches"
        ),
        data=json.dumps({"event_type": "rerender", "client_payload": {"pr": 445}}),
        headers=headers,
    )
    print("    dispatch event status code:", r.status_code)
    assert r.status_code == 204

    print("sleeping for a few minutes to let the rerender happen...")
    tot = 0
    while tot < 180:
        time.sleep(10)
        tot += 10
        print("    slept %s seconds out of 180" % tot, flush=True)

    print("checking repo for the rerender...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with pushd(tmpdir):
            print("cloning...")
            subprocess.run(
                [
                    "git",
                    "clone",
                    "https://github.com/conda-forge/cf-autotick-bot-test-package-feedstock.git",
                ],
                check=True,
            )

            with pushd("cf-autotick-bot-test-package-feedstock"):
                print("checkout branch...")
                subprocess.run(
                    ["git", "checkout", "rerender-live-test"],
                    check=True,
                )

                print("checking the git history...")
                c = subprocess.run(
                    ["git", "log", "--pretty=oneline", "-n", "1"],
                    capture_output=True,
                    check=True,
                )
                output = c.stdout.decode("utf-8")
                print("    last commit:", output.strip())
                assert "MNT:" in output

                if TEST_DEPLOY_KEY:
                    print("checking rerender undid workflow edits...")
                    with open(".github/workflows/automerge.yml", "r") as fp:
                        lines = fp.readlines()
                    assert not any(
                        line.startswith("# test line for rerender edits")
                        for line in lines
                    )

    print("tests passed!")


parser = argparse.ArgumentParser(
    description="Run a live test of the rerendering code",
)
parser.add_argument(
    "--branch",
    help="the webservices-dispatch-action branch to use for the rerendering test",
    required=True,
)
parser.add_argument(
    "--build-and-push",
    help="build and push the docker image to the dev tag before running the tests",
    action="store_true",
)
args = parser.parse_args()

if args.build_and_push:
    subprocess.run(
        ["docker", "build", "-t", "condaforge/webservices-dispatch-action:dev", "."],
        check=True,
    )
    subprocess.run(
        ["docker", "push", "condaforge/webservices-dispatch-action:dev"],
        check=True,
    )


print("making an edit to the head ref...")
with tempfile.TemporaryDirectory() as tmpdir:
    with pushd(tmpdir):
        print("cloning...")
        subprocess.run(
            [
                "git",
                "clone",
                f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/conda-forge/cf-autotick-bot-test-package-feedstock.git",
            ],
            check=True,
        )

        with pushd("cf-autotick-bot-test-package-feedstock"):
            try:
                _change_action_branch(args.branch, verbose=True)

                print("checkout branch...")
                subprocess.run(
                    ["git", "checkout", "rerender-live-test"],
                    check=True,
                )

                ci_support_files = glob.glob(".ci_support/*.yaml")
                if len(ci_support_files) > 0:
                    print("removing files...")
                    subprocess.run(["git", "rm"] + ci_support_files, check=True)

                    print("making an edit to a workflow...")
                    with open(".github/workflows/automerge.yml", "a") as fp:
                        fp.write("# test line for rerender edits\n")
                    subprocess.run(
                        ["git", "add", "-f", ".github/workflows/automerge.yml"],
                        check=True,
                    )

                    print("git status...")
                    subprocess.run(["git", "status"], check=True)

                    print("committing...")
                    subprocess.run(
                        [
                            "git",
                            "commit",
                            "-m",
                            "[ci skip] remove ci scripts to trigger rerender",
                        ],
                        check=True,
                    )

                    print("push to origin...")
                    subprocess.run(["git", "push"], check=True)

                _run_test()

            finally:
                _change_action_branch("main", verbose=True)

                print("checkout branch...")
                subprocess.run(
                    ["git", "checkout", "rerender-live-test"],
                    check=True,
                )
                subprocess.run(
                    ["git", "pull"],
                    check=True,
                )

                print("undoing edit to a workflow...")
                with open(".github/workflows/automerge.yml", "r") as fp:
                    lines = fp.readlines()

                lines = [
                    line.strip()
                    for line in lines
                    if not line.startswith("# test line for rerender edits")
                ]

                with open(".github/workflows/automerge.yml", "w") as fp:
                    fp.write("\n".join(lines))

                subprocess.run(
                    ["git", "add", "-f", ".github/workflows/automerge.yml"],
                    check=True,
                )

                print("committing...")
                subprocess.run(
                    [
                        "git",
                        "commit",
                        "--allow-empty",
                        "-m",
                        "[ci skip] undo workflow changes if any",
                    ],
                    check=True,
                )

                print("push to origin...")
                subprocess.run(["git", "push"], check=True)

                _merge_main_to_branch("rerender-live-test", verbose=True)
