import logging
import subprocess

from git import GitCommandError

LOGGER = logging.getLogger(__name__)


def rerender(git_repo):
    LOGGER.info('rerendering')
    curr_head = git_repo.active_branch.commit
    ret = subprocess.call(
        ["conda", "smithy", "rerender", "-c", "auto", "--no-check-uptodate"],
        cwd=git_repo.working_dir,
    )

    if ret:
        changed, rerender_error = False, True
    elif git_repo.active_branch.commit == curr_head:
        changed, rerender_error = False, False
    else:
        subprocess.call(
           ["git", "checkout", "HEAD~1", "--", ".github/workflows/*"],
           cwd=git_repo.working_dir,
        )
        subprocess.call(
           ["git", "commit", "--amend", "--allow-empty", "--no-edit"],
           cwd=git_repo.working_dir,
        )
        changed, rerender_error = True, False


def comment_and_push_per_changed(
    *,
    changed, rerender_error, git_repo, pull, pr_branch, pr_owner, pr_repo
):
    LOGGER.info(
        'pushing and commenting: branch|owner|repo = %s|%s|%s',
        pr_branch,
        pr_owner,
        pr_repo,
    )

    message = None
    if changed:
        try:
            git_repo.remotes.origin.push()
        except GitCommandError as e:
            LOGGER.critical(repr(e))
            message = """\
Hi! This is the friendly automated conda-forge-webservice.
I tried to rerender for you, but it looks like I wasn't able to push to the {}
branch of {}/{}. Did you check the "Allow edits from maintainers" box?

**NOTE**: PRs from organization accounts cannot be rerendered because of GitHub 
permissions.
""".format(pr_branch, pr_owner, pr_repo)
    else:
        if rerender_error:
            doc_url = (
                "https://conda-forge.org/docs/maintainer/updating_pkgs.html"
                "#rerendering-with-conda-smithy-locally"
            )
            message = """\
Hi! This is the friendly automated conda-forge-webservice.
I tried to rerender for you but ran into some issues, please ping conda-forge/core
for further assistance. You can also try [re-rendering locally]({}).
""".format(doc_url)
        else:
            message = """\
Hi! This is the friendly automated conda-forge-webservice.
I tried to rerender for you, but it looks like there was nothing to do.
"""

    if message is not None:
        pull.create_issue_comment(message)
