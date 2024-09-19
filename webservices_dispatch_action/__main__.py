import json
import logging
import os
import pprint
import subprocess
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
    make_lint_comment,
)
from webservices_dispatch_action.rerendering import (
    rerender,
)
from webservices_dispatch_action.utils import comment_and_push_if_changed

LOGGER = logging.getLogger(__name__)


def main():
    logging.basicConfig(level=logging.INFO)

    LOGGER.info("making API clients")

    with webservices_dispatch_action.sensitive_env():
        _, gh = create_api_sessions(os.environ["INPUT_GITHUB_TOKEN"])

    with open(os.environ["GITHUB_EVENT_PATH"], "r") as fp:
        event_data = json.load(fp)
    event_name = os.environ["GITHUB_EVENT_NAME"].lower()

    LOGGER.info("github event: %s", event_name)
    LOGGER.info("github event data:\n%s\n", pprint.pformat(event_data))

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
                    help_message=" or you can try [rerendeing locally](%s)"
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

                # update version
                curr_head = git_repo.active_branch.commit
                cmd = (
                    f"run-webservices-dispatch-action-version-updater "
                    f"--feedstock-dir {feedstock_dir} "
                    f"--repo-name {repo_name}"
                )
                if input_version:
                    cmd += f" --input-version {input_version}"
                LOGGER.info(f"Running command {cmd}")
                ret = subprocess.run(
                    cmd,
                    shell=True,
                    env=os.environ,
                )
                if ret.returncode != 0:
                    version_error = True
                    version_changed = False
                elif git_repo.active_branch.commit == curr_head:
                    version_error = False
                    version_changed = False
                else:
                    version_error = False
                    version_changed = True

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
                        help_message=" or you can try [rerendeing locally](%s)"
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
                    lints, hints = lint_feedstock(feedstock_dir, use_container=True)
                except Exception as err:
                    LOGGER.warning("LINTING ERROR: %s", repr(err))
                    LOGGER.warning(
                        "LINTING ERROR TRACEBACK: %s", traceback.format_exc()
                    )
                    message = textwrap.dedent("""
                        Hi! This is the friendly automated conda-forge-linting service.

                        I Failed to even lint the recipe, probably because of a
                        conda-smithy bug :cry:.
                        This likely indicates a problem in your `meta.yaml`, though.
                        To get a traceback to help figure out what's going on, install
                        conda-smithy
                        and run `conda smithy recipe-lint --conda-forge .` from
                        the recipe directory.
                        """)
                    pr.create_issue_comment(message)
                    status = "bad"
                else:
                    message, status = make_lint_comment(
                        gh, gh_repo, pr_num, lints, hints
                    )

                print(f"Linter status: {status}")
                print(f"Linter message:\n{message}")
        else:
            raise ValueError(
                "Dispatch action %s cannot be processed!" % event_data["action"]
            )
    else:
        raise ValueError("GitHub event %s cannot be processed!" % event_name)
