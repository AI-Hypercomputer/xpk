<!--
 Copyright 2025 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 -->
 
# How to Contribute

We would love to accept your patches and contributions to this project.

## Before you begin

### Sign our Contributor License Agreement

Contributions to this project must be accompanied by a [Contributor License Agreement](https://cla.developers.google.com/about) (CLA). You (or your employer) retain the copyright to your contribution; this simply gives us permission to use and redistribute your contributions as part of the project.

If you or your current employer have already signed the Google CLA (even if it was for a different project), you probably don't need to do it again.

Visit <https://cla.developers.google.com/> to see your current agreements or to sign a new one.

### Review our Community Guidelines

This project follows [Google's Open Source Community Guidelines](https://opensource.google/conduct/).

## Contribution process

1. [Fork and clone the repository](#1-fork-and-clone-the-repository)
2. [Set up Development Environment](#2-set-up-development-environment)
3. [Make your change](#3-make-your-change)
4. [Verify change against checklist](#4-verify-change-against-checklist)
5. [Open a Pull Request](#5-open-a-pull-request)

### 1. Fork and clone the repository

All changes should be performed on your XPK fork, then proposed to the mainline repository through the pull request process.
More about how to work with forks can be found [here](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo).

### 2. Set up Development Environment

**Step 1: System and Virtual Environment Setup**

Follow the **[Installation from Source](./installation.md)** instructions in the main guide. This will ensure you have:
* Installed all system prerequisites (Python, gcloud, kubectl, etc.).
* Created and activated your **Virtual Environment** (required to avoid "externally managed environment" errors).

**Step 2: Install XPK dev dependencies**

Once your virtual environment is active, install XPK in editable mode with development dependencies:

```shell
pip install .[dev]
```

### 3. Make your change

Make your intended code change, cover it with unit tests, and iterate on the code.

To execute your local XPK version via the command line, make sure you have added the local bin directory to your path as described in the **[Installation from Source](./installation.md)** guide.

### 4. Verify change against checklist

Before opening a pull request make sure your change passes the following checklist:

* **Tests:** Change is covered with unit tests.
* **Goldens:** Goldens are up-to-date. Regenerate them using the following command:
    ```shell
    make goldens
    ```
* **Feature Flags:** Change is production ready. If not, make sure it is covered with a feature flag. See [sample flags here](https://github.com/AI-Hypercomputer/xpk/blob/main/src/xpk/utils/feature_flags.py).

**Code merged to the main branch is expected to be released at any given point in time, hence it needs to be treated as production code.**

You can read more about our testing guidance [here](./testing.md).

### 5. Open a Pull Request

All submissions, including submissions by project members, require review. We use [GitHub pull requests](https://docs.github.com/articles/about-pull-requests) for this purpose.
