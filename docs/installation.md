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

There are 2 ways to install XPK:

- via Python package installer (`pip`),
- clone from git and build from source.

## Prerequisites

The following tools must be installed:

- python >= 3.10: download from [here](https://www.python.org/downloads/)
- pip: [installation instructions](https://pip.pypa.io/en/stable/installation/)
- python venv: [installation instructions](https://virtualenv.pypa.io/en/latest/installation.html)
(all three of above can be installed at once from [here](https://packaging.python.org/en/latest/guides/installing-using-linux-tools/#installing-pip-setuptools-wheel-with-linux-package-managers))
- gcloud: install from [here](https://cloud.google.com/sdk/gcloud#download_and_install_the) and then:
  - Run `gcloud init` 
  - [Authenticate](https://cloud.google.com/sdk/gcloud/reference/auth/application-default/login) to Google Cloud
- kubectl: install from [here](https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl#install_kubectl) and then:
  - Install `gke-gcloud-auth-plugin` from [here](https://cloud.google.com/kubernetes-engine/docs/how-to/cluster-access-for-kubectl#install_plugin)
- docker: [installation instructions](https://docs.docker.com/engine/install/) and then:
  - Configure sudoless docker: [guide](https://docs.docker.com/engine/install/linux-postinstall/)
  - Run `gcloud auth configure-docker` to ensure images can be uploaded to registry 

### Additional prerequisites when installing from pip

- kueuectl: install from [here](https://kueue.sigs.k8s.io/docs/reference/kubectl-kueue/installation/)
- kjob: installation instructions [here](https://github.com/kubernetes-sigs/kjob/blob/main/docs/installation.md)

### Additional prerequisites when installing from source

- git: [installation instructions](https://git-scm.com/downloads/linux)
- make: install by running `apt-get -y install make` (`sudo` might be required)

### Additional prerequisites to enable bash completion

- Install [argcomplete](https://pypi.org/project/argcomplete/) globally on your machine.
  ```shell
  pip install argcomplete
  activate-global-python-argcomplete
  ```
- Configure `argcomplete` for XPK.
  ```shell
  eval "$(register-python-argcomplete xpk)"
  ```

## Installation via pip

To install XPK using pip, first install required tools mentioned in [prerequisites](#prerequisites) and [additional prerequisites](#additional-prerequisites-when-installing-from-pip). Then you can install XPK simply by running:

```shell
pip install xpk
```

If you see an error saying: `This environment is externally managed`, please use a virtual environment. For example:

```shell
# One time step of creating the virtual environment
VENV_DIR=~/venvp3
python3 -m venv $VENV_DIR

# Activate your virtual environment
source $VENV_DIR/bin/activate

# Install XPK in virtual environment using pip
pip install xpk
```

## Installation from source

To install XPK from source, first install required tools mentioned in [prerequisites](#prerequisites) and [additional prerequisites](#additional-prerequisites-when-installing-from-source). Afterwards you can install XPK from source using `make`

```shell
# Clone the XPK repository
git clone https://github.com/google/xpk.git
cd xpk

# Install required dependencies and build XPK with make
make install && export PATH=$PATH:$PWD/bin
```

If you want the dependecies to be available in your PATH please run: `echo $PWD/bin` and add its value to `PATH` in .bashrc or .zshrc file.

If you see an error saying: `This environment is externally managed`, please use a virtual environment. For example:

```shell
# One time step of creating the virtual environment
VENV_DIR=~/venvp3
python3 -m venv $VENV_DIR

# Activate your virtual environment
source $VENV_DIR/bin/activate

# Clone the XPK repository
git clone https://github.com/google/xpk.git
cd xpk

# Install required dependencies and build XPK with make
make install && export PATH=$PATH:$PWD/bin
```
