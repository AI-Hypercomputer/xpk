<!--
 Copyright 2023 Google LLC

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
# Changelog

<!--

Changelog follow the https://keepachangelog.com/ standard (at least the headers)

This allow to:

* auto-parsing release notes during the automated releases from github-action:
  https://github.com/marketplace/actions/pypi-github-auto-release
* Have clickable headers in the rendered markdown

To release a new version (e.g. from `1.0.0` -> `2.0.0`):

* Create a new `# [2.0.0] - YYYY-MM-DD` header and detail the changes to be released.
* At the end of the file:
  * Define the new link url:
  `[2.0.0]: https://github.com/google/xpk/compare/v1.0.0...v2.0.0`

-->

## [Unreleased]
- Move away from static GKE version and use RAPID release default.

## [0.4.0] - 2024-04-17
- Enable Autoprovisioning support.
- Support deletion of subnets when cluster is deleted.
- Integrate Vertex AI functionality to create Vertex AI Tensorboard and upload logs in Tensorboard directory to Vertex AI Tensorboard.
- Integrate Pathways.
- Add retry logic to Kueue, jobset and cluster credential steps.
- Bump Kueue version to 0.6.1.
- Add XPK inspector.

## [0.3.0] - 2024-02-26

- Bump Jobset version to 0.3.2.
- Bump Kueue version to 0.6.0.
- Add single GPU support. Multislice, and A3 GPU optimizations in progress.
- Add CPU single and multislice support to XPK. Tested up to 1500 VMs.
- Fail workload creation early if the cluster doesn't have that resource type.
- Enable multiple workload deletion in parallel based on cluster name, and filters.
- Add `--enable-debug-logs` to workload create to add debug logs to a workload.
- Support SIGTERM handling in xpk workload command, and propagate exit code from
  user jobs to cloud composer UI.
- Add sidecar container to display stack traces, and README details.
- Add label for xpk initiated TPU pods.

## [0.2.0] - 2023-12-07

### Added
- Add a reservation exists check and provide help if this errors
- Add error message and self-help instructions to readme for troubleshooting problems
- Add v5p support
- Add xpk cluster create flags for reservation/on-demand/spot
- Change GKE version to 1.28.3-gke.1286000
- Change cpu node pool defaults to be better adapted to demand
- Fix empty results from filter-by-status=QUEUED / FAILED / RUNNING
- Fix parallel execution of node pool commands (concurrent ops)
- Fix pip-changelog to the wrong package

## [0.1.0] - 2023-11-17

### Added
- Initial release of xpk PyPI package

[0.1.0]: https://github.com/google/xpk/releases/tag/v0.1.0
[0.2.0]: https://github.com/google/xpk/compare/v0.1.0...v0.2.0
[0.3.0]: https://github.com/google/xpk/compare/v0.2.0...v0.3.0
[0.4.0]: https://github.com/google/xpk/compare/v0.3.0...v0.4.0
