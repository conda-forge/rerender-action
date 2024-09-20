import json
import os
import time

import github
import pytest
import requests


@pytest.mark.parametrize(
    "pr_number,expected_status,expected_msgs",
    [
        (
            632,
            "success",
            [
                "and found it was in an excellent condition.",
                "This is a v1 recipe and not yet lintable. We are working on it!",
            ],
        ),
        (
            523,
            "failure",
            [
                "I was trying to look for recipes to lint for "
                "you, but couldn't find any.",
            ],
        ),
        (
            217,
            "success",
            [
                "I do have some suggestions for making it better though...",
            ],
        ),
        (
            62,
            "success",
            [
                "I do have some suggestions for making it better though...",
            ],
        ),
        (
            57,
            "failure",
            [
                "I was trying to look for recipes to lint for you, but it "
                "appears we have a merge conflict.",
            ],
        ),
        (
            56,
            "failure",
            [
                "I was trying to look for recipes to lint for you, but it appears "
                "we have a merge conflict.",
            ],
        ),
        (
            54,
            "success",
            [
                "I do have some suggestions for making it better though...",
            ],
        ),
        (
            17,
            "failure",
            [
                "and found some lint.",
            ],
        ),
        (
            16,
            "success",
            [
                "and found it was in an excellent condition.",
            ],
        ),
    ],
)
def test_linter_pr(
    pr_number, expected_status, expected_msgs, setup_test_action, pytestconfig
):
    gh = github.Github(auth=github.Auth.Token(os.environ["GH_TOKEN"]))
    repo = gh.get_repo("conda-forge/conda-forge-webservices")
    pr = repo.get_pull(pr_number)
    commit = repo.get_commit(pr.head.sha)

    setup_test_action(pytestconfig.getoption("branch"))

    headers = {
        "authorization": "Bearer %s" % os.environ["GH_TOKEN"],
        "content-type": "application/json",
    }
    r = requests.post(
        (
            "https://api.github.com/repos/conda-forge/"
            "conda-forge-webservices/dispatches"
        ),
        data=json.dumps({"event_type": "lint", "client_payload": {"pr": pr_number}}),
        headers=headers,
    )
    assert r.status_code == 204

    print("\nsleeping for two minutes to let the linter work...", flush=True)
    tot = 0
    while tot < 120:
        time.sleep(10)
        tot += 10
        print("    slept %s seconds out of 120" % tot, flush=True)

    for status in commit.get_statuses():
        if status.context == "conda-forge-linter":
            break

    assert status.state == expected_status

    comment = None
    for _comment in pr.get_issue_comments():
        if (
            "Hi! This is the friendly automated conda-forge-linting service."
            in _comment.body
        ):
            comment = _comment

    assert comment is not None
    for expected_msg in expected_msgs:
        assert expected_msg in comment.body
