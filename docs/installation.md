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

# Installation

There are two ways to install XPK:
1.  **Via `pip`** (Recommended for usage)
2.  **From Source** (Recommended for development)

## 1. Prerequisites

Ensure the following tools are installed and configured before proceeding.

### Core Tools
* **Python 3.10+**: Ensure `pip` and `venv` are included.
    * *Check:* `python3 --version`
* **Google Cloud SDK (gcloud)**: [Install from here](https://cloud.google.com/sdk/docs/install).
    * Run `gcloud init`
    * [Authenticate](https://cloud.google.com/sdk/gcloud/reference/auth/application-default/login) to Google Cloud.
    * *Check:* `gcloud auth list`
* **Kubectl**: [Install from here](https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl#install_kubectl).
    * Install the auth plugin: `gke-gcloud-auth-plugin` ([Guide](https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl#install_plugin)).
    * *Check:* `kubectl version --client`
* **Docker**: [Install from here](https://docs.docker.com/engine/install/).
    * *Linux users:* [Configure sudoless docker](https://docs.docker.com/engine/install/linux-postinstall/).
    * Run `gcloud auth configure-docker` to enable image uploads to the registry.

### Method-Specific Requirements
Depending on your chosen installation method, you may need these additional tools:

| Install Method | Tool | Notes |
| :--- | :--- | :--- |
| **Pip** | **kueuectl** | [Installation instructions](https://kueue.sigs.k8s.io/docs/reference/kubectl-kueue/installation/) |
| **Pip** | **kjob** | [Installation instructions](https://github.com/kubernetes-sigs/kjob/blob/main/docs/installation.md) |
| **Source** | **git** | Install via your package manager (e.g., `sudo apt-get install git` on Debian/Ubuntu) |
| **Source** | **make** | Install via your package manager (e.g., `sudo apt-get install make` on Debian/Ubuntu) |

---

## 2. Environment Setup (Virtual Environment)

To avoid conflicts with system packages (and the common "This environment is externally managed" error), **we strongly recommend installing XPK in a virtual environment.**

Run the following to create and activate your environment:

```shell
# 1. Create the virtual environment (one-time setup)
VENV_DIR=~/venvp3
python3 -m venv $VENV_DIR

# 2. Activate the environment
# (You must run this command every time you open a new terminal to use xpk)
source $VENV_DIR/bin/activate
```

---

## 3. Install XPK

Choose **one** of the following methods.

### Option A: Install via pip

Once your prerequisites are met and your virtual environment is active:

```shell
pip install xpk
```

### Option B: Install from Source

If you need to modify the source code or use the latest unreleased features:

```shell
# 1. Clone the XPK repository
git clone https://github.com/AI-Hypercomputer/xpk.git
cd xpk

# 2. Install dependencies and build
make install

# 3. Update your PATH
export PATH=$PATH:$PWD/bin
```

*Note: Installing from source is recommended only for contributors and advanced users. Most users should install via PIP for the best stability.*

**Persisting the PATH configuration:**
To use `xpk` in future terminal sessions without re-running the export command, add the binary path to your shell configuration:

* **For Bash (Linux default):**
    ```shell
    echo "export PATH=\$PATH:$PWD/bin" >> ~/.bashrc
    source ~/.bashrc
    ```

* **For Zsh (macOS default):**
    ```shell
    echo "export PATH=\$PATH:$PWD/bin" >> ~/.zshrc
    source ~/.zshrc
    ```

---

## 4. Verify Installation

Run the following command to ensure XPK is correctly installed and reachable:

```shell
xpk --help
```

If the installation was successful, you will see the help menu listing available commands.

---

## 5. Post-Installation (Optional)

### Enable Bash Completion
To enable tab completion for XPK commands:

1.  **Install argcomplete:**
    ```shell
    pip install argcomplete
    activate-global-python-argcomplete
    ```

2.  **Configure XPK completion:**
    ```shell
    eval "$(register-python-argcomplete xpk)"
    ```

---

## 6. Updating XPK

To get the latest version of XPK:

**Via Pip:**
```shell
pip install --upgrade xpk
```

**From Source:**
Navigate to your cloned directory and run:
```shell
git pull
make install
```

---

## 7. Troubleshooting

**Issue: `command not found: xpk`**
* **Cause:** The installation directory is not in your system `$PATH`.
* **Fix:** Ensure you have activated your virtual environment. If installing from source, ensure you added the `/bin` folder to your PATH as described in Section 3.

**Issue: `permission denied` when running Docker**
* **Cause:** Your user is not added to the `docker` group.
* **Fix:** Follow the [Linux post-installation steps for Docker](https://docs.docker.com/engine/install/linux-postinstall/) to run Docker without sudo.

**Issue: `error: externally-managed-environment`**
* **Cause:** You are trying to install Python packages globally, which is restricted by newer OS versions.
* **Fix:** Ensure you create and activate a Virtual Environment (see **Section 2: Environment Setup**).
