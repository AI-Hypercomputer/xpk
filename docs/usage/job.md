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
 
## Job List

*   Job List (see jobs submitted via batch command):

    ```shell
    xpk job ls --cluster xpk-test
    ```

* Example Job List Output:

  ```
    NAME                              PROFILE               LOCAL QUEUE   COMPLETIONS   DURATION   AGE
    xpk-def-app-profile-slurm-74kbv   xpk-def-app-profile                 1/1           15s        17h
    xpk-def-app-profile-slurm-brcsg   xpk-def-app-profile                 1/1           9s         3h56m
    xpk-def-app-profile-slurm-kw99l   xpk-def-app-profile                 1/1           5s         3h54m
    xpk-def-app-profile-slurm-x99nx   xpk-def-app-profile                 3/3           29s        17h
  ```

## Job Cancel

*   Job Cancel (delete job submitted via batch command):

    ```shell
    xpk job cancel xpk-def-app-profile-slurm-74kbv --cluster xpk-test
    ```
