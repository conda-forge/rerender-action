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
import json
import os
import subprocess
import tempfile
import time

import requests
from conftest import _change_action_branch, _merge_main_to_branch, pushd
from github import Github

REPO_OWNER = "conda-forge"
REPO_NAME = "cf-autotick-bot-test-package-feedstock"
REPO = f"{REPO_OWNER}/{REPO_NAME}"
BRANCH = "version-update-live-test"
PR_NUM = 483


def _set_pr_draft():
    gh = Github(os.environ["GH_TOKEN"])
    repo = gh.get_repo(REPO)
    pr = repo.get_pull(PR_NUM)

    if pr.draft:
        return

    # based on this post: https://github.com/orgs/community/discussions/70061
    mutation = (
        """
        mutation {
            convertPullRequestToDraft(input:{pullRequestId: %s}) {
                pullRequest{id, isDraft}
            }
        }
    """
        % pr.node_id
    )

    headers = {"Authorization": f"bearer {os.environ['GH_TOKEN']}"}
    req = requests.post(
        "https://api.github.com/graphql",
        json={"query": mutation},
        headers=headers,
    )
    req.raise_for_status()


def _set_pr_not_draft():
    # based on this post: https://github.com/orgs/community/discussions/70061
    gh = Github(os.environ["GH_TOKEN"])
    repo = gh.get_repo(REPO)
    pr = repo.get_pull(PR_NUM)

    if not pr.draft:
        return

    mutation = (
        """
        mutation {
            markPullRequestReadyForReview(input:{pullRequestId: %s}) {
                pullRequest{id, isDraft}
            }
        }
    """
        % pr.node_id
    )

    headers = {"Authorization": f"bearer {os.environ['GH_TOKEN']}"}
    req = requests.post(
        "https://api.github.com/graphql",
        json={"query": mutation},
        headers=headers,
    )
    req.raise_for_status()


def _change_version(new_version="0.13", branch="main"):
    import random

    new_sha = "".join(random.choices("0123456789abcdef", k=64))

    print("changing the version to an old one...", flush=True)
    subprocess.run(["git", "checkout", branch], check=True)

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
    subprocess.run(["git", "add", "recipe/meta.yaml"], check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "--allow-empty",
            "-m",
            "[ci skip] moved version to older 0.13",
        ],
        check=True,
    )

    print("push to origin...", flush=True)
    subprocess.run(["git", "push"], check=True)


def _pr_title(new=None):
    gh = Github(os.environ["GH_TOKEN"])
    repo = gh.get_repo(REPO)
    pr = repo.get_pull(PR_NUM)
    old = pr.title
    if new:
        pr.edit(title=new)
    return old


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
        (f"https://api.github.com/repos/{REPO}/dispatches"),
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
                [
                    "git",
                    "clone",
                    f"https://github.com/{REPO}.git",
                ],
                check=True,
            )

            with pushd(REPO_NAME):
                print("checkout branch...", flush=True)
                subprocess.run(
                    ["git", "checkout", BRANCH],
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

    if version:
        assert _pr_title() == f"ENH: update package version to {version}"
    else:
        assert "ENH: update package version to " in _pr_title()

    gh = Github(os.environ["GH_TOKEN"])
    repo = gh.get_repo(REPO)
    pr = repo.get_pull(PR_NUM)

    assert not pr.draft

    print("tests passed!", flush=True)


parser = argparse.ArgumentParser(
    description="Run a live test of the rerendering code",
)
parser.add_argument(
    "--branch",
    help="the webservices-dispatch-action branch to use for the test",
    required=True,
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
        ["docker", "build", "-t", "condaforge/webservices-dispatch-action:dev", "."],
        check=True,
    )
    subprocess.run(
        ["docker", "push", "condaforge/webservices-dispatch-action:dev"],
        check=True,
    )


print("making an edit to the head ref...", flush=True)
with tempfile.TemporaryDirectory() as tmpdir:
    with pushd(tmpdir):
        print("cloning...", flush=True)
        subprocess.run(
            [
                "git",
                "clone",
                f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/{REPO}.git",
            ],
            check=True,
        )

        with pushd(REPO_NAME):
            try:
                _change_action_branch(args.branch, verbose=True)
                _change_version(new_version="0.13", branch="main")
                _merge_main_to_branch(BRANCH, verbose=True)
                _change_version(new_version="0.13", branch=BRANCH)
                original_title = _pr_title(new="ENH: update package version")
                _set_pr_draft()
                _run_test(args.version)
            finally:
                _change_action_branch("main", verbose=True)
                _change_version(new_version="0.14", branch="main")
                _merge_main_to_branch(BRANCH, verbose=True)
                _change_version(new_version="0.13", branch=BRANCH)
                _pr_title(new=original_title)
                _set_pr_not_draft()
