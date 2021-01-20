import os
import logging
import subprocess

import yaml
from git import GitCommandError

LOGGER = logging.getLogger(__name__)


def rerender(git_repo):
    LOGGER.info('rerendering')

    changed = ensure_output_validation_is_on(git_repo)

    curr_head = git_repo.active_branch.commit
    ret = subprocess.call(
        ["conda", "smithy", "rerender", "-c", "auto", "--no-check-uptodate"],
        cwd=git_repo.working_dir,
    )

    if ret:
        return False, True
    else:
        return (git_repo.active_branch.commit != curr_head) or changed, False


def ensure_output_validation_is_on(git_repo):
    pth = os.path.join(git_repo.working_dir, "conda-forge.yml")
    if os.path.exists(pth):
        with open(pth, "r") as fp:
            cfg = yaml.safe_load(fp)
    else:
        cfg = {}

    if not cfg.get("conda_forge_output_validation", False):
        cfg["conda_forge_output_validation"] = True

        with open(pth, "w") as fp:
            fp.write(yaml.dump(cfg, default_flow_style=False))

        subprocess.run(
            "git add conda-forge.yml",
            shell=True,
            cwd=git_repo.working_dir,
        )
        return True
    else:
        return False


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
            global_pinning_url = (
                "https://github.com/conda-forge/conda-forge-pinning-feedstock/"
                "blob/master/recipe/conda_build_config.yaml"
            )
            message = """\
Hi! This is the friendly automated conda-forge-webservice.
I tried to rerender for you but ran into some issues, please ping conda-forge/core
for further assistance. You can also try [re-rendering locally]({}).

More information on the issue may be available in the actions tab of the feedstock
under a "rerender" workflow. The following suggestions might explain the problem:

* Is the `recipe/meta.yaml` file valid?
* If there is a `recipe/conda-build-config.yaml` file in the feedstock make sure
  that it is compatible with the current [global pinnnings]({}).
""".format(doc_url, global_pinning_url)
        else:
            message = """\
Hi! This is the friendly automated conda-forge-webservice.
I tried to rerender for you, but it looks like there was nothing to do.
"""

    if message is not None:
        pull.create_issue_comment(message)
