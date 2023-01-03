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
import os
import json
import time
import tempfile
import requests
import contextlib
import subprocess
import argparse
import glob


@contextlib.contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(previous_dir)


def _run_test():
    print('sending repo dispatch event to rerender...')
    headers = {
        "authorization": "Bearer %s" % os.environ['GH_TOKEN'],
        'content-type': 'application/json',
    }
    r = requests.post(
        ("https://api.github.com/repos/conda-forge/"
         "cf-autotick-bot-test-package-feedstock/dispatches"),
        data=json.dumps({"event_type": "rerender", "client_payload": {"pr": 445}}),
        headers=headers,
    )
    print('    dispatch event status code:', r.status_code)
    assert r.status_code == 204

    print('sleeping for a few minutes to let the rerender happen...')
    tot = 0
    while tot < 180:
        time.sleep(10)
        tot += 10
        print("    slept %s seconds out of 180" % tot, flush=True)

    print('checking repo for the rerender...')
    with tempfile.TemporaryDirectory() as tmpdir:
        with pushd(tmpdir):
            print("cloning...")
            subprocess.run(
                "git clone "
                "https://github.com/conda-forge/"
                "cf-autotick-bot-test-package-feedstock.git",
                shell=True,
                check=True,
            )

            with pushd("cf-autotick-bot-test-package-feedstock"):
                print("checkout branch...")
                subprocess.run(
                    "git checkout rerender-live-test",
                    shell=True,
                    check=True,
                )

                print("checking the git history")
                c = subprocess.run(
                    ["git", "log", "--pretty=oneline", "-n", "1"],
                    capture_output=True,
                    check=True,
                )
                output = c.stdout.decode('utf-8')
                print("    last commit:", output.strip())
                assert "MNT:" in output

    print('tests passed!')


def _change_action_branch(branch):
    print("moving repo to %s action" % branch, flush=True)
    subprocess.run("git checkout main", shell=True, check=True)

    data = (
        branch,
        "rerendering_github_token: ${{ secrets.RERENDERING_GITHUB_TOKEN }}",
    )

    with open(".github/workflows/webservices.yml", "w") as fp:
        fp.write("""\
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
""" % data)

    print("commiting...", flush=True)
    subprocess.run("git add .github/workflows/webservices.yml", shell=True, check=True)
    subprocess.run(
        "git commit "
        "-m "
        "'[ci skip] move rerender action to branch %s'" % branch,
        shell=True, check=True
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
args = parser.parse_args()

if args.build_and_push:
    subprocess.run(
        "docker build -t condaforge/webservices-dispatch-action:dev .",
        shell=True,
    )
    subprocess.run(
        "docker push condaforge/webservices-dispatch-action:dev",
        shell=True,
    )


print('making an edit to the head ref...')
with tempfile.TemporaryDirectory() as tmpdir:
    with pushd(tmpdir):
        print("cloning...")
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

                print("checkout branch...")
                subprocess.run(
                    "git checkout rerender-live-test",
                    shell=True,
                    check=True,
                )

                if len(glob.glob(".ci_support/*.yaml")) > 0:
                    print("removing files...")
                    subprocess.run("git rm .ci_support/*.yaml", shell=True, check=True)

                    print("making an edit to a workflow...")
                    subprocess.run(
                        "echo ' ' >> .github/workflows/automerge.yml",
                        shell=True,
                        check=True,
                    )
                    subprocess.run(
                        "git add .github/workflows/automerge.yml",
                        check=True,
                        shell=True,
                    )

                    print("git status...")
                    subprocess.run("git status", shell=True, check=True)

                    print("commiting...")
                    subprocess.run(
                        "git commit "
                        "-m "
                        "'[ci skip] remove ci scripts to trigger rerender'",
                        shell=True, check=True
                    )

                    print("push to origin...")
                    subprocess.run("git push", shell=True, check=True)

                _run_test()

            finally:
                _change_action_branch("main")

                print("checkout branch...")
                subprocess.run(
                    "git checkout rerender-live-test",
                    shell=True,
                    check=True,
                )
                subprocess.run(
                    "git pull",
                    shell=True,
                    check=True,
                )

                print("undoing edit to a workflow...")
                with open(".github/workflows/automerge.yml", "r") as fp:
                    lines = fp.readlines()

                for i in range(2):
                    if len(lines[-1].strip()) == 0:
                        lines = lines[:-1]

                with open(".github/workflows/automerge.yml", "w") as fp:
                    fp.write("".join(lines))

                subprocess.run(
                    "git add .github/workflows/automerge.yml",
                    check=True,
                    shell=True,
                )

                print("commiting...")
                subprocess.run(
                    "git commit "
                    "--allow-empty "
                    "-m "
                    "'[ci skip] undo workflow changes'",
                    shell=True, check=True
                )

                print("push to origin...")
                subprocess.run("git push", shell=True, check=True)
