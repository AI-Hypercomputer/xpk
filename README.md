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

[![Build Tests](https://github.com/google/xpk/actions/workflows/build_tests.yaml/badge.svg?query=branch%3Amain)](https://github.com/google/xpk/actions/workflows/build_tests.yaml?query=branch%3Amain)
[![Nightly Tests](https://github.com/google/xpk/actions/workflows/nightly_tests.yaml/badge.svg?query=branch%3Amain)](https://github.com/google/xpk/actions/workflows/nightly_tests.yaml?query=branch%3Amain)
[![Develop Tests](https://github.com/AI-Hypercomputer/xpk/actions/workflows/build_tests.yaml/badge.svg?query=branch%3Adevelop)](https://github.com/AI-Hypercomputer/xpk/actions/workflows/build_tests.yaml?query=branch%3Adevelop)
[![Develop Nightly Tests](https://github.com/AI-Hypercomputer/xpk/actions/workflows/nightly_tests.yaml/badge.svg?query=branch%3Adevelop)](https://github.com/AI-Hypercomputer/xpk/actions/workflows/nightly_tests.yaml?query=branch%3Adevelop)

# Overview

XPK (Accelerated Processing Kit, pronounced x-p-k) is a command line interface that simplifies cluster creation and workload execution on Google Kubernetes Engine (GKE). XPK generates preconfigured, training-optimized clusters and allows easy workload scheduling without any Kubernetes expertise.

XPK is recommended for quick creation of GKE clusters for proofs of concepts and testing.

XPK decouples provisioning capacity from running jobs. There are two structures: clusters (provisioned VMs) and workloads (training jobs). Clusters represent the physical resources you have available. Workloads represent training jobs -- at any time some of these will be completed, others will be running and some will be queued, waiting for cluster resources to become available.

The ideal workflow starts by provisioning the clusters for all of the ML
hardware you have reserved. Then, without re-provisioning, submit jobs as
needed. By eliminating the need for re-provisioning between jobs, using Docker
containers with pre-installed dependencies and cross-ahead of time compilation,
these queued jobs run with minimal start times. Further, because workloads
return the hardware back to the shared pool when they complete, developers can
achieve better use of finite hardware resources. And automated tests can run
overnight while resources tend to be underutilized.

XPK supports the following TPU types:
* v4
* v5e
* v5p
* Trillium (v6e)
* Ironwood (tpu7x)
XPK supports a variety of hardware accelerators.
| Accelerator | Type               | Create Cluster                                                                                                | Create Workload                                                                                                 |
|-------------|--------------------|---------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| TPU         | v4                 | [docs](./docs/usage/clusters.md)                                                                              | [docs](./docs/usage/workloads.md)                                                                               |
| TPU         | v5e                | [docs](./docs/usage/clusters.md)                                                                              | [docs](./docs/usage/workloads.md)                                                                               |
| TPU         | v5p                | [docs](./docs/usage/clusters.md)                                                                              | [docs](./docs/usage/workloads.md)                                                                               |
| TPU         | Trillium (v6e)     | [docs](./docs/usage/clusters.md)                                                                              | [docs](./docs/usage/workloads.md)                                                                               |
| TPU         | Ironwood (tpu7x)   | [docs](./docs/usage/clusters.md)                                                                              | [docs](./docs/usage/workloads.md)                                                                               |
| GPU         | A100               | [docs](./docs/usage/gpu.md)                                                                                   | [docs](./docs/usage/workloads.md)                                                                               |
| GPU         | A3-Highgpu (h100)  | [docs](./docs/usage/gpu.md)                                                                                   | [docs](./docs/usage/workloads.md)                                                                               |
| GPU         | A3-Mega (h100-mega)| [docs](./docs/usage/clusters.md#provisioning-a3-ultra-a3-mega-and-a4-clusters-gpu-machines)                   | [docs](./docs/usage/workloads.md#workloads-for-a3-ultra-a3-mega-and-a4-clusters-gpu-machines)                   |
| GPU         | A3-Ultra (h200)    | [docs](./docs/usage/clusters.md#provisioning-a3-ultra-a3-mega-and-a4-clusters-gpu-machines)                   | [docs](./docs/usage/workloads.md#workloads-for-a3-ultra-a3-mega-and-a4-clusters-gpu-machines)                   |
| GPU         | A4 (b200)          | [docs](./docs/usage/clusters.md#provisioning-a3-ultra-a3-mega-and-a4-clusters-gpu-machines)                   | [docs](./docs/usage/workloads.md#workloads-for-a3-ultra-a3-mega-and-a4-clusters-gpu-machines)                   |
| GPU         | A4X (gb200)        | [docs](./docs/usage/gpu.md)                                                                                   | [docs](./docs/usage/workloads.md)                                                                               |
| CPU         | n2-standard-32     | [docs](./docs/usage/cpu.md)                                                                                   | [docs](./docs/usage/workloads.md)                                                                               |

and the following GPU types:
* A100
* A3-Highgpu (h100)
* A3-Mega (h100-mega) - [Create cluster](./docs/usage/clusters.md#provisioning-a3-ultra-a3-mega-and-a4-clusters-gpu-machines), [Create workloads](./docs/usage/workloads.md#workloads-for-a3-ultra-a3-mega-and-a4-clusters-gpu-machines)
* A3-Ultra (h200) - [Create cluster](./docs/usage/clusters.md#provisioning-a3-ultra-a3-mega-and-a4-clusters-gpu-machines), [Create workloads](./docs/usage/workloads.md#workloads-for-a3-ultra-a3-mega-and-a4-clusters-gpu-machines)
* A4 (b200) - [Create cluster](./docs/usage/clusters.md#provisioning-a3-ultra-a3-mega-and-a4-clusters-gpu-machines), [Create workloads](./docs/usage/workloads.md#workloads-for-a3-ultra-a3-mega-and-a4-clusters-gpu-machines)
* A4X (gb200)
XPK also supports the following [Google Cloud Storage solutions](./docs/usage/storage.md):

and the following CPU types:
* n2-standard-32
| Storage Type                               | Documentation                                                                            |
|--------------------------------------------|------------------------------------------------------------------------------------------|
| Cloud Storage FUSE                         | [docs](./docs/usage/storage.md#fuse)                                                     |
| Filestore                                  | [docs](./docs/usage/storage.md#filestore)                                                |
| Parallelstore                              | [docs](./docs/usage/storage.md#parallelstore)                                            |
| Block storage (Persistent Disk, Hyperdisk) | [docs](./docs/usage/storage.md#block-storage-persistent-disk-hyperdisk)                  |

XPK also supports [Google Cloud Storage solutions](./docs/usage/storage.md):
* [Cloud Storage FUSE](./docs/usage/storage.md#fuse)
* [Filestore](./docs/usage/storage.md#filestore)
* [Parallelstore](./docs/usage/storage.md#parallelstore)
* [Block storage (Persistent Disk, Hyperdisk)](./docs/usage/storage.md#block-storage-persistent-disk-hyperdisk)

# Documentation

* [Permissions](./docs/permissions.md)
* [Installation](./docs/installation.md)
* Usage:
  * [Clusters](./docs/usage/clusters.md)
    * [GPU](./docs/usage/gpu.md)
    * [CPU](./docs/usage/cpu.md)
    * [Autoprovisioning](./docs/usage/autoprovisioning.md)
  * [Workloads](./docs/usage/workloads.md)
    * [Docker](./docs/usage/docker.md)
  * [Storage](./docs/usage/storage.md)
  * [Advanced](./docs/usage/advanced.md)
  * [Inspector](./docs/usage/inspector.md)
  * [Run](./docs/usage/run.md)
  * [Job](./docs/usage/job.md)
* [Troubleshooting](./docs/troubleshooting.md)
* [Local Testing](./docs/local_testing.md)

# Contributing

Please read [`contributing.md`](./docs/contributing.md) for details on our code of conduct, and the process for submitting pull requests to us.

# License

This project is licensed under the Apache License 2.0 - see the [`LICENSE`](./LICENSE) file for details