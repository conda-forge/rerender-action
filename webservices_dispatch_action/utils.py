import logging
import os

import requests
from git import GitCommandError

from .api_sessions import get_actor_token

LOGGER = logging.getLogger(__name__)


def get_gha_run_link(repo_name):
    """Get the link to the GHA run given a repo name like conda-forge/blah-feedstock."""
    run_id = os.environ["GITHUB_RUN_ID"]
    return f"https://github.com/{repo_name}/actions/runs/{run_id}"


def comment_and_push_if_changed(
    *,
    action,
    changed,
    error,
    git_repo,
    pull,
    pr_branch,
    pr_owner,
    pr_repo,
    repo_name,
    close_pr_if_no_changes_or_errors,
    help_message,
    info_message,
):
    actor, token, can_change_workflows = get_actor_token()
    LOGGER.info(
        "token can change workflows: %s",
        can_change_workflows,
    )

    LOGGER.info(
        "pushing and commenting: branch|owner|repo = %s|%s|%s",
        pr_branch,
        pr_owner,
        pr_repo,
    )

    run_link = get_gha_run_link(repo_name)

    push_error = False
    message = None
    if changed:
        try:
            git_repo.remotes.origin.set_url(
                "https://%s:%s@github.com/%s/%s.git"
                % (
                    actor,
                    token,
                    pr_owner,
                    pr_repo,
                ),
                push=True,
            )
            git_repo.remotes.origin.push()
        except GitCommandError as e:
            push_error = True
            LOGGER.critical(repr(e))
            message = """\
Hi! This is the friendly automated conda-forge-webservice.

I tried to {} for you, but it looks like I wasn't \
able to push to the {} \
branch of {}/{}. Did you check the "Allow edits from maintainers" box?

**NOTE**: Our webservices cannot push to PRs from organization accounts \
or PRs from forks made from \
organization forks because of GitHub \
permissions. Please fork the feedstock directly from conda-forge \
into your personal GitHub account.
""".format(action, pr_branch, pr_owner, pr_repo)
        finally:
            git_repo.remotes.origin.set_url(
                "https://github.com/%s/%s.git"
                % (
                    pr_owner,
                    pr_repo,
                ),
                push=True,
            )
    else:
        if error:
            message = """\
Hi! This is the friendly automated conda-forge-webservice.

I tried to {} for you but ran into some issues. \
Please check the output \
logs of the latest webservices GitHub actions workflow run for errors. You can \
also ping conda-forge/core for further assistance{}.
""".format(action, help_message)
        else:
            message = """\
Hi! This is the friendly automated conda-forge-webservice.

I tried to {} for you, but it looks like there was nothing to do.
""".format(action)
            if close_pr_if_no_changes_or_errors:
                message += "\nI'm closing this PR!"

    if info_message:
        if message is None:
            message = """\
Hi! This is the friendly automated conda-forge-webservice.

{}
""".format(info_message)
        else:
            message += "\n" + info_message

    if message is not None:
        if run_link is not None:
            message += (
                "\nThis message was generated by "
                f"GitHub actions workflow run [{run_link}]({run_link}).\n"
            )

        pull.create_issue_comment(message)

    if close_pr_if_no_changes_or_errors and not changed and not error:
        pull.edit(state="closed")

    return push_error


def mark_pr_as_ready_for_review(pr):
    # based on this post: https://github.com/orgs/community/discussions/70061
    if not pr.draft:
        return True

    mutation = (
        """
        mutation {
            markPullRequestReadyForReview(input:{pullRequestId: "%s"}) {
                pullRequest{id, isDraft}
            }
        }
    """
        % pr.node_id
    )

    headers = {"Authorization": f"bearer {get_actor_token()[1]}"}
    req = requests.post(
        "https://api.github.com/graphql",
        json={"query": mutation},
        headers=headers,
    )
    if "errors" in req.json():
        LOGGER.error(req.json()["errors"])
        return False
    else:
        return True
