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

## Steps

0. <Optionally needed> Create a virtual environment:

Optionally use a venv to set up and develop xpk. This is needed for Google
internal xpk development from a cloudtop machine.

```shell
  # Create venv if needed.
  ## One time step of creating the venv
  VENV_DIR=~/venvp3
  python3 -m venv $VENV_DIR
  ## enter the venv.
  source $VENV_DIR/bin/activate
  ## Same steps as above.
  git clone https://github.com/google/xpk.git
  pip install .[dev]
```

1. Install developer tools including `pyink`, `pylint`, and `precommit` using

```shell
  git clone https://github.com/google/xpk.git
  pip install .[dev]
```

2. Install git hook scripts.
```shell
cd $XPK_REPO_DIR
pre-commit install
# Optionally run against files
pre-commit run --all-files
```

3. Write code and commit changes!
```shell
# 1. Code will be autoformatted on:
git commit -m "My cool new feature"
# 2. If code needs to be reformatted, check what changes were made, and add them to the commit.
git add -p
# 3. Run git commit again, which should successfully pass pre-commit checks.
git commit -m "My cool new feature"


# Manually format code by running:
plink .
```

### Code Reviews

All submissions, including submissions by project members, require review. We
use [GitHub pull requests](https://docs.github.com/articles/about-pull-requests)
for this purpose.

### Testing
Unit Tests for XPK coming soon.

### Code style
Before pushing your changes, you need to lint the code style via `pyink`. This
is handled through `pre-commit` if you have that installed.

To install `pyink`:

```sh
pip3 install pyink==24.3.0
```

To lint the code:

```sh
# Format files in the local directory.
pyink .
# Check if files need to be formatted.
pylink --check .
```
