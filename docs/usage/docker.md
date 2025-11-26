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
 
# How to add docker images to a xpk workload

The default behavior is `xpk workload create` will layer the local directory (`--script-dir`) into
the base docker image (`--base-docker-image`) and run the workload command.
If you don't want this layering behavior, you can directly use `--docker-image`. Do not mix arguments from the two flows in the same command.

## Recommended / Default Docker Flow: `--base-docker-image` and `--script-dir`
This flow pulls the `--script-dir` into the `--base-docker-image` and runs the new docker image.

* The below arguments are optional by default. xpk will pull the local
  directory with a generic base docker image.

  - `--base-docker-image` sets the base image that xpk will start with.

  - `--script-dir` sets which directory to pull into the image. This defaults to the current working directory.

  See `xpk workload create --help` for more info.

* Example with defaults which pulls the local directory into the base image:
  ```shell
  echo -e '#!/bin/bash 
 echo "Hello world from a test script!"' > test.sh
xpk workload create --cluster xpk-test \
--workload xpk-test-workload-base-image --command "bash test.sh" \
--tpu-type=v5litepod-16 --num-slices=1
  ```

* Recommended Flow For Normal Sized Jobs (fewer than 10k accelerators):
  ```shell
  xpk workload create --cluster xpk-test \
--workload xpk-test-workload-base-image --command "bash custom_script.sh" \
--base-docker-image=gcr.io/your_dependencies_docker_image \
--tpu-type=v5litepod-16 --num-slices=1
  ```

## Optional Direct Docker Image Configuration: `--docker-image`
If a user wants to directly set the docker image used and not layer in the
current working directory, set `--docker-image` to the image to be use in the
workload.

* Running with `--docker-image`:
  ```shell
  xpk workload create --cluster xpk-test \
--workload xpk-test-workload-base-image --command "bash test.sh" \
--tpu-type=v5litepod-16 --num-slices=1 --docker-image=gcr.io/your_docker_image
  ```

* Recommended Flow For Large Sized Jobs (more than 10k accelerators):
  ```shell
  xpk cluster cacheimage \
--cluster xpk-test --docker-image gcr.io/your_docker_image
# Run workload create with the same image.
xpk workload create --cluster xpk-test \
--workload xpk-test-workload-base-image --command "bash test.sh" \
--tpu-type=v5litepod-16 --num-slices=1 --docker-image=gcr.io/your_docker_image
  ```
