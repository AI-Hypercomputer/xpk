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

# More advanced facts:

* Workload create has two mutually exclusive ways to override the environment of a workload:
  *  a `--env` flag to specify each environment variable separately. The format is:

     `--env VARIABLE1=value --env VARIABLE2=value`

  *  a `--env-file` flag to allow specifying the container's
environment from a file. Usage is the same as Docker's
[--env-file flag](https://docs.docker.com/engine/reference/commandline/run/#env)

    Example Env File:
    ```shell
    LIBTPU_INIT_ARGS=--my-flag=true --performance=high
    MY_ENV_VAR=hello
    ```

* Workload create accepts a --debug-dump-gcs flag which is a path to GCS bucket.
Passing this flag sets the XLA_FLAGS='--xla_dump_to=/tmp/xla_dump/' and uploads
hlo dumps to the specified GCS bucket for each worker.
