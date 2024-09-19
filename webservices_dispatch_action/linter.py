import textwrap
import time
from pathlib import Path


def _is_mergeable(repo, pr_id):
    mergeable = None
    while mergeable is None:
        time.sleep(1.0)
        pull_request = repo.get_pull(pr_id)
        if pull_request.state != "open":
            return False
        mergeable = pull_request.mergeable
    return mergeable


def _get_comment_state(comment):
    if "and found it was in an excellent condition." in comment:
        has_lints = False
    else:
        has_lints = True

    if "but it appears we have a merge conflict." in comment:
        merge_conflict = True
    else:
        merge_conflict = False

    if "I do have some suggestions for making it better though..." in comment:
        has_hints = True
    else:
        has_hints = False

    if "recipes to lint for you, but couldn't find any." in comment:
        no_recipes = True
    else:
        no_recipes = False

    if merge_conflict:
        return "merge_conflict"

    if no_recipes:
        return "no recipes"

    if has_lints:
        return "bad"

    if not has_lints and has_hints:
        return "mixed"

    if not has_lints and not has_hints:
        return "good"


def make_lint_comment(gh, repo, pr_id, lints, hints):
    mergeable = _is_mergeable(repo, pr_id)
    if not mergeable:
        message = textwrap.dedent("""
            Hi! This is the friendly automated conda-forge-linting service.

            I was trying to look for recipes to lint for you, but it appears we have a merge conflict.
            Please try to merge or rebase with the base branch to resolve this conflict.

            Please ping the 'conda-forge/core' team (using the @ notation in a comment) if you believe this is a bug.
            """)  # noqa
        status = "merge_conflict"
    else:
        fnames = set(hints.keys()) | set(lints.keys())

        all_pass = True
        messages = []
        hints_found = False
        for fname in fnames:
            recipe = Path(fname)

            if recipe.name == "recipe.yaml":
                # this is a v1 recipe and not yet handled
                hint = "\nFor **{}**:\n\n{}".format(
                    fname,
                    "This is a v1 recipe and not yet lintable. We are working on it!",
                )
                messages.append(hint)
                # also add it to hints so that the PR is marked as mixed
                hints_found = True
                continue

            _lints = lints.get(fname, [])
            _hints = hints.get(fname, [])

            if _lints:
                all_pass = False
                messages.append(
                    "\nFor **{}**:\n\n{}".format(
                        fname, "\n".join(f" * {lint}" for lint in _lints)
                    )
                )
            if _hints:
                hints_found = True
                messages.append(
                    "\nFor **{}**:\n\n{}".format(
                        fname, "\n".join(f" * {hint}" for hint in _hints)
                    )
                )

        # Put the recipes in the form "```recipe/a```, ```recipe/b```".
        recipe_code_blocks = ", ".join(f"```{r}```" for r in fnames)

        good = textwrap.dedent(
            f"""
        Hi! This is the friendly automated conda-forge-linting service.

        I just wanted to let you know that I linted all conda-recipes in your PR ({recipe_code_blocks}) and found it was in an excellent condition.

        """  # noqa: E501
        )

        mixed = good + textwrap.dedent("""
        I do have some suggestions for making it better though...

        {}
        """).format("\n".join(messages))

        bad = textwrap.dedent(
            f"""
        Hi! This is the friendly automated conda-forge-linting service.

        I wanted to let you know that I linted all conda-recipes in your PR ({recipe_code_blocks}) and found some lint.

        Here's what I've got...

        {{}}
        """  # noqa: E501
        ).format("\n".join(messages))

        if not fnames:
            message = textwrap.dedent("""
                Hi! This is the friendly automated conda-forge-linting service.

                I was trying to look for recipes to lint for you, but couldn't find any.
                Please ping the 'conda-forge/core' team (using the @ notation in a comment) if you believe this is a bug.
                """)  # noqa
            status = "no recipes"
        elif all_pass and hints_found:
            message = mixed
            status = "mixed"
        elif all_pass:
            message = good
            status = "good"
        else:
            message = bad
            status = "bad"

    message += "\nGHA4lyfe"

    pr = repo.get_pull(pr_id)
    comment = None
    for _comment in pr.get_issue_comments():
        if (
            "Hi! This is the friendly automated conda-forge-linting service."
        ) in _comment.body:
            comment = _comment

    if comment:
        if comment.body != message:
            if _get_comment_state(comment.body) == _get_comment_state(message):
                comment.edit(message)
            else:
                pr.create_issue_comment(message)
    else:
        pr.create_issue_comment(message)

    return message, status


def set_pr_status(repo, sha, status, target_url=None):
    commit = repo.get_commit(sha)

    # get the last github status by the linter, if any
    # API emmits these in reverse time order so first is latest
    statuses = commit.get_statuses()
    last_status = None
    for status in statuses:
        if status.context == "conda-forge-linter":
            last_status = status
            break

    # convert the linter status to a state
    lint_status_to_state = {"good": "success", "mixed": "success", "pending": "pending"}
    lint_new_state = lint_status_to_state.get(status, "failure")

    # make a status only if it is different or we have not ever done it
    # for this commit
    if (
        last_status is None
        or last_status.state != lint_new_state
        or last_status.target_url != target_url
    ):
        if status == "good":
            commit.create_status(
                "success",
                description="All recipes are excellent.",
                context="conda-forge-linter",
                target_url=target_url,
            )
        elif status == "mixed":
            commit.create_status(
                "success",
                description="Some recipes have hints.",
                context="conda-forge-linter",
                target_url=target_url,
            )
        elif status == "pending":
            commit.create_status(
                "pending",
                description="Linting in progress...",
                context="conda-forge-linter",
                target_url=target_url,
            )
        else:
            commit.create_status(
                "failure",
                description="Some recipes need some changes.",
                context="conda-forge-linter",
                target_url=target_url,
            )
