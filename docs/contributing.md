# How to Contribute

We would love to accept your patches and contributions to this project.

## Before you begin

### Sign our Contributor License Agreement

Contributions to this project must be accompanied by a
[Contributor License Agreement](https://cla.developers.google.com/about) (CLA).
You (or your employer) retain the copyright to your contribution; this simply
gives us permission to use and redistribute your contributions as part of the
project.

If you or your current employer have already signed the Google CLA (even if it
was for a different project), you probably don't need to do it again.

Visit <https://cla.developers.google.com/> to see your current agreements or to
sign a new one.

### Review our Community Guidelines

This project follows [Google's Open Source Community
Guidelines](https://opensource.google/conduct/).

## Contribution process

1. [Create a virtual environment](#create-a-virtual-environment)
1. [Fork and clone the repository](#fork-and-clone-the-repository)
1. [Install XPK dev dependencies](#install-xpk-dev-dependencies)
1. [Make your change](#make-your-change)
1. [Verify change against checklist](#verify-change-against-checklist)
1. [Open a Pull Request](#open-a-pull-request)

### Create a virtual environment

Use a venv to set up and develop xpk. This is needed for Google
internal xpk development from a cloudtop machine.

```shell
# Create venv if needed.
## One time step of creating the venv
VENV_DIR=~/venvp3
python3 -m venv $VENV_DIR
## enter the venv.
source $VENV_DIR/bin/activate
```

### Fork and clone the repository

All changes should be performed on your XPK fork, then proposed to the mainline repository through pull request process.
More about how to work with forks can be found [here](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo).

### Install XPK dev dependencies

Use the following script to install XPK python dependencies.
```shell
pip install .[dev]
```
Also, follow [Prerequisites](https://github.com/AI-Hypercomputer/xpk?tab=readme-ov-file#prerequisites) section to ensure system dependencies are present on your machine.

### Make your change

Make intended code change, cover it with unit tests and iterate on the code by executing local XPK version via `python3 xpk.py`.

### Verify change against checklist

Before opening a pull request make sure your change passes the following checklist:
* Change is covered with unit tests.
* Goldens are up-to-date - regenerate them using `make goldens` command.
* Change is production ready, if not make sure it is covered with a feature flag. See sample flags [here](https://github.com/AI-Hypercomputer/xpk/blob/main/src/xpk/utils/feature_flags.py).

You can read more about our testing guidance [here](./testing.md).

**Code merged to the main branch is expected to be released at any given point in time, hence it needs to be treated as a production code.**

### Open a Pull Request

All submissions, including submissions by project members, require review. We
use [GitHub pull requests](https://docs.github.com/articles/about-pull-requests)
for this purpose.
