<!--
 Copyright 2024 Google LLC

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

# Integration Test Workflows
The following tests are currently implemented through Github Actions:
* Create an XPK Cluster with zero node pools
* Delete the cluster created
* Create a Private XPK Cluster with 2x v4-8 nodepools
* Delete the cluster created
* Create an XPK Cluster with 2x v4-8 nodepools
* Delete the cluster created

## Nightly Tests:
A cron job is scheduled to run at 12AM PST daily. The details of the jobs run are in `xpk/.github/workflows/nightly_tests.yaml`

## Integration Tests:
Integration tests are run on a push to the `main` branch and on an approved PR. The details of the jobs run are in `xpk/.github/workflows/build_tests.yaml`
