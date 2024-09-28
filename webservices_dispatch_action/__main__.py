import json
import logging
import os
import pprint
import subprocess
import sys
import tempfile
import textwrap
import traceback

from conda_forge_feedstock_ops.lint import lint as lint_feedstock
from git import Repo

import webservices_dispatch_action
from webservices_dispatch_action.api_sessions import (
    create_api_sessions,
    get_actor_token,
)
from webservices_dispatch_action.linter import (
    build_and_make_lint_comment,
    make_lint_comment,
    set_pr_status,
)
from webservices_dispatch_action.rerendering import (
    rerender,
)
from webservices_dispatch_action.utils import (
    comment_and_push_if_changed,
    get_gha_run_link,
    mark_pr_as_ready_for_review,
)
from webservices_dispatch_action.version_updater import update_pr_title, update_version

LOGGER = logging.getLogger(__name__)


def _pull_docker_image():
    try:
        print("::group::docker image pull", flush=True)
        subprocess.run(
            [
                "docker",
                "pull",
                f"{os.environ['CF_FEEDSTOCK_OPS_CONTAINER_NAME']}:{os.environ['CF_FEEDSTOCK_OPS_CONTAINER_TAG']}",
            ],
        )
        sys.stderr.flush()
        sys.stdout.flush()
    finally:
        print("::endgroup::", flush=True)


def main():
    logging.basicConfig(level=logging.INFO)

    LOGGER.info("making API clients")

    with webservices_dispatch_action.sensitive_env():
        _, gh = create_api_sessions(os.environ["INPUT_GITHUB_TOKEN"])

    with open(os.environ["GITHUB_EVENT_PATH"], "r") as fp:
        event_data = json.load(fp)
    event_name = os.environ["GITHUB_EVENT_NAME"].lower()

    print("::group::github event", flush=True)
    LOGGER.info("github event: %s", event_name)
    LOGGER.info("github event data:\n%s\n", pprint.pformat(event_data))
    sys.stderr.flush()
    sys.stdout.flush()
    print("::endgroup::", flush=True)

    if event_name in ["repository_dispatch"]:
        if event_data["action"] == "rerender":
            pr_num = int(event_data["client_payload"]["pr"])
            repo_name = event_data["repository"]["full_name"]

            gh_repo = gh.get_repo(repo_name)
            pr = gh_repo.get_pull(pr_num)

            if pr.state == "closed":
                raise ValueError("Closed PRs cannot be rerendered!")

            with tempfile.TemporaryDirectory() as tmpdir:
                # clone the head repo
                pr_branch = pr.head.ref
                pr_owner = pr.head.repo.owner.login
                pr_repo = pr.head.repo.name
                repo_url = "https://github.com/%s/%s.git" % (
                    pr_owner,
                    pr_repo,
                )
                feedstock_dir = os.path.join(
                    tmpdir,
                    pr_repo,
                )
                git_repo = Repo.clone_from(
                    repo_url,
                    feedstock_dir,
                    branch=pr_branch,
                )

                # rerender
                _, _, can_change_workflows = get_actor_token()
                can_change_workflows = (
                    can_change_workflows or os.environ["HAS_SSH_PRIVATE_KEY"] == "true"
                )
                _pull_docker_image()
                changed, rerender_error, info_message = rerender(
                    git_repo, can_change_workflows
                )

                # comment
                push_error = comment_and_push_if_changed(
                    action="rerender",
                    changed=changed,
                    error=rerender_error,
                    git_repo=git_repo,
                    pull=pr,
                    pr_branch=pr_branch,
                    pr_owner=pr_owner,
                    pr_repo=pr_repo,
                    repo_name=repo_name,
                    close_pr_if_no_changes_or_errors=False,
                    help_message=" or you can try [rerendering locally](%s)"
                    % (
                        "https://conda-forge.org/docs/maintainer/updating_pkgs.html"
                        "#rerendering-with-conda-smithy-locally"
                    ),
                    info_message=info_message,
                )

                if rerender_error or push_error:
                    raise RuntimeError(
                        "Rerendering failed! error in push|rerender: %s|%s"
                        % (
                            push_error,
                            rerender_error,
                        ),
                    )
                # if the pr was made by the bot, mark it as ready for review
                if pr.title == "MNT: rerender" and pr.user.login == "conda-forge-admin":
                    mark_pr_as_ready_for_review(pr)

        elif event_data["action"] == "version_update":
            pr_num = int(event_data["client_payload"]["pr"])
            repo_name = event_data["repository"]["full_name"]
            input_version = event_data["client_payload"].get("input_version", None)

            gh_repo = gh.get_repo(repo_name)
            pr = gh_repo.get_pull(pr_num)

            if pr.state == "closed":
                raise ValueError("Closed PRs cannot have their version updated!")

            with tempfile.TemporaryDirectory() as tmpdir:
                # clone the head repo
                pr_branch = pr.head.ref
                pr_owner = pr.head.repo.owner.login
                pr_repo = pr.head.repo.name
                repo_url = "https://github.com/%s/%s.git" % (
                    pr_owner,
                    pr_repo,
                )
                feedstock_dir = os.path.join(
                    tmpdir,
                    pr_repo,
                )
                git_repo = Repo.clone_from(
                    repo_url,
                    feedstock_dir,
                    branch=pr_branch,
                )

                _, _, can_change_workflows = get_actor_token()
                can_change_workflows = (
                    can_change_workflows or os.environ["HAS_SSH_PRIVATE_KEY"] == "true"
                )

                # update version
                _pull_docker_image()
                LOGGER.info(
                    "Running version update for %s with input_version %s",
                    repo_name,
                    input_version,
                )
                version_changed, version_error, found_version = update_version(
                    git_repo, repo_name, input_version=input_version
                )

                version_push_error = comment_and_push_if_changed(
                    action="update the version",
                    changed=version_changed,
                    error=version_error,
                    git_repo=git_repo,
                    pull=pr,
                    pr_branch=pr_branch,
                    pr_owner=pr_owner,
                    pr_repo=pr_repo,
                    repo_name=repo_name,
                    close_pr_if_no_changes_or_errors=True,
                    help_message="",
                    info_message="",
                )

                if version_error or version_push_error:
                    raise RuntimeError(
                        "Updating version failed! error in "
                        "push|version update: %s|%s"
                        % (
                            version_push_error,
                            version_error,
                        ),
                    )

                if version_changed:
                    # rerender
                    rerender_changed, rerender_error, info_message = rerender(
                        git_repo, can_change_workflows
                    )
                    rerender_push_error = comment_and_push_if_changed(
                        action="rerender",
                        changed=rerender_changed,
                        error=rerender_error,
                        git_repo=git_repo,
                        pull=pr,
                        pr_branch=pr_branch,
                        pr_owner=pr_owner,
                        pr_repo=pr_repo,
                        repo_name=repo_name,
                        close_pr_if_no_changes_or_errors=False,
                        help_message=" or you can try [rerendering locally](%s)"
                        % (
                            "https://conda-forge.org/docs/maintainer/updating_pkgs.html"
                            "#rerendering-with-conda-smithy-locally"
                        ),
                        info_message=info_message,
                    )

                    if rerender_error or rerender_push_error:
                        raise RuntimeError(
                            "Rerendering failed! error in push|rerender: %s|%s"
                            % (
                                push_error,
                                rerender_error,
                            ),
                        )
                    if found_version:
                        LOGGER.info(
                            "Updating PR title for %s#%s with version=%s",
                            repo_name,
                            pr_num,
                            found_version,
                        )
                        update_pr_title(repo_name, pr_num, found_version)

                    # these PRs always get marked as ready for review
                    mark_pr_as_ready_for_review(pr)

        elif event_data["action"] == "lint":
            pr_num = int(event_data["client_payload"]["pr"])
            repo_name = event_data["repository"]["full_name"]

            gh_repo = gh.get_repo(repo_name)
            pr = gh_repo.get_pull(pr_num)

            if pr.state == "closed":
                raise ValueError("Closed PRs are not linted!")

            with tempfile.TemporaryDirectory() as tmpdir:
                # clone the head repo
                pr_branch = pr.head.ref
                pr_owner = pr.head.repo.owner.login
                pr_repo = pr.head.repo.name
                repo_url = "https://github.com/%s/%s.git" % (
                    pr_owner,
                    pr_repo,
                )
                feedstock_dir = os.path.join(
                    tmpdir,
                    pr_repo,
                )
                git_repo = Repo.clone_from(
                    repo_url,
                    feedstock_dir,
                    branch=pr_branch,
                )

                # run the linter
                try:
                    set_pr_status(pr.base.repo, pr.head.sha, "pending", target_url=None)
                    _pull_docker_image()
                    lints, hints = lint_feedstock(feedstock_dir, use_container=True)
                except Exception as err:
                    LOGGER.warning("LINTING ERROR: %s", repr(err))
                    LOGGER.warning(
                        "LINTING ERROR TRACEBACK: %s", traceback.format_exc()
                    )
                    _message = textwrap.dedent("""\
Hi! This is the friendly automated conda-forge-linting service.

I Failed to even lint the recipe, probably because of a conda-smithy bug :cry:. \
This likely indicates a problem in your `meta.yaml`, though. To get a traceback \
to help figure out what's going on, install conda-smithy and run \
`conda smithy recipe-lint --conda-forge .` from the recipe directory.
""")
                    run_link = get_gha_run_link(repo_name)
                    _message += (
                        "\n\n<sub>This message was generated by "
                        f"GitHub actions workflow run [{run_link}]({run_link}).</sub>\n"
                    )
                    msg = make_lint_comment(gh_repo, pr_num, _message)
                    status = "bad"
                else:
                    msg, status = build_and_make_lint_comment(
                        gh, gh_repo, pr_num, lints, hints
                    )

                set_pr_status(
                    pr.base.repo, pr.head.sha, status, target_url=msg.html_url
                )
                print(f"Linter status: {status}")
                print(f"Linter message:\n{msg.body}")
        else:
            raise ValueError(
                "Dispatch action %s cannot be processed!" % event_data["action"]
            )
    else:
        raise ValueError("GitHub event %s cannot be processed!" % event_name)
