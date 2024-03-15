import os
import logging
import pprint
import subprocess
import click
import sys

from git import Repo
from conda.models.version import VersionOrder

from conda_forge_tick.utils import setup_logging
from conda_forge_tick.feedstock_parser import load_feedstock
from conda_forge_tick.update_upstream_versions import get_latest_version

from conda_forge_tick.update_sources import (
    PyPI,
    CRAN,
    NPM,
    ROSDistro,
    RawURL,
    Github,
    IncrementAlphaRawURL,
    NVIDIA,
)
import conda_forge_tick.update_recipe

setup_logging()

LOGGER = logging.getLogger(__name__)


def update_version(git_repo, repo_name, input_version=None):
    name = os.path.basename(repo_name).rsplit("-", 1)[0]
    LOGGER.info("using feedstock name %s for repo %s", name, repo_name)

    try:
        LOGGER.info("computing feedstock attributes")
        attrs = load_feedstock(name, {})
        LOGGER.info("feedstock attrs:\n%s\n", pprint.pformat(attrs))
    except Exception:
        LOGGER.exception("error while computing feedstock attributes!")
        return False, True

    if input_version is None or input_version == "null":
        try:
            LOGGER.info("getting latest version")
            new_version = get_latest_version(
                name,
                attrs,
                (
                    PyPI(),
                    CRAN(),
                    NPM(),
                    ROSDistro(),
                    RawURL(),
                    Github(),
                    IncrementAlphaRawURL(),
                    NVIDIA(),
                ),
            )
            new_version = new_version["new_version"]
            if new_version:
                LOGGER.info(
                    "curr version|latest version: %s|%s",
                    attrs.get("version", "0.0.0"),
                    new_version,
                )
            else:
                raise RuntimeError("Could not fetch latest version!")
        except Exception:
            LOGGER.exception("error while getting feedstock version!")
            return False, True
    else:
        LOGGER.info("using input version")
        new_version = input_version
        LOGGER.info(
            "curr version|input version: %s|%s",
            attrs.get("version", "0.0.0"),
            new_version,
        )

    # if we are finding the version automatically, check that it is going up
    if (
        (input_version is None or input_version == "null")
        and (
            VersionOrder(str(new_version).replace("-", "."))
            <= VersionOrder(str(attrs.get("version", "0.0.0")).replace("-", "."))
        )
    ):
        LOGGER.info(
            "not updating since new version is less or equal to current version"
        )
        return False, False

    try:
        new_meta_yaml, errors = conda_forge_tick.update_recipe.update_version(
            attrs["raw_meta_yaml"],
            str(new_version),
        )
        if errors or new_meta_yaml is None:
            LOGGER.critical("errors when updating the recipe: %r", errors)
            raise RuntimeError("Error updating the recipe!")
        new_meta_yaml = conda_forge_tick.update_recipe.update_build_number(
            new_meta_yaml,
            0,
        )
    except Exception:
        LOGGER.exception("error while updating the recipe!")
        return False, True

    try:
        with open(os.path.join(git_repo.working_dir, "recipe", "meta.yaml"), "w") as fp:
            fp.write(new_meta_yaml)

        subprocess.run(
            "git add recipe/meta.yaml",
            shell=True,
            cwd=git_repo.working_dir,
            check=True,
            env=os.environ,
        )

        subprocess.run(
            f"git commit -m 'ENH updated version to {new_version}'",
            shell=True,
            cwd=git_repo.working_dir,
            check=True,
            env=os.environ,
        )
    except Exception:
        LOGGER.exception("error while committing new recipe to repo")
        return False, True

    return True, False


@click.command()
@click.option(
    "--feedstock-dir",
    required=True,
    type=str,
    help="The directory of the feedstock",
)
@click.option(
    "--repo-name",
    required=True,
    type=str,
    help="The name of the repository",
)
@click.option(
    "--input-version",
    required=False,
    type=str,
    default=None,
    help="The version to update to",
)
def main(
    feedstock_dir,
    repo_name,
    input_version=None,
):
    git_repo = Repo(feedstock_dir)

    _, version_error = update_version(
        git_repo, repo_name, input_version=input_version,
    )

    if version_error:
        sys.exit(1)
    else:
        sys.exit(0)
