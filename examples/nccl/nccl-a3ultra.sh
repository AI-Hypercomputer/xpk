# """
# Copyright 2025 Google LLC

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#      https://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# """

# This is a script to execute a nccl test. See https://github.com/NVIDIA/nccl-tests for more details

#!/bin/bash

set -x
echo "Starting workload container for $NNODES benchmark"

# Load all the cuda libs
/sbin/ldconfig

# Install ping
apt update -y
apt install -y iputils-ping

# Start sshd
/scripts/container_entry.sh daemon &

# Get helper variables to form all hostnames
export POSTFIX=$(hostname --fqdn | cut -d . -f 2-)
export WORKERS_BASENAME=$(hostname --fqdn | cut -d . -f 1 | rev | cut -d - -f 2- | rev )
export NODE_RANK=$JOB_COMPLETION_INDEX


# For every worker, wait till online and add to hostfile
for i in `seq 0 $(($NNODES-1))`; do
  OTHER=${WORKERS_BASENAME}-${i}.${POSTFIX}
  until ssh -p 222 -o StrictHostKeyChecking=no $OTHER hostname; do
    echo Waiting for ${OTHER}...
    sleep 10
  done
  echo ${OTHER} port=222 slots=8 | tee -a /tmp/hostfile;
done

cat /tmp/hostfile

# Launch from head node
if [[ "${NODE_RANK}" -eq "0" ]]; then

    # World Level = 0x0, Rail Aligned = 0x7
    export NCCL_TESTS_SPLIT_MASK="0x0";

    # Force use of libnccl-gib
    export NCCL_NET=gIB

    # Set all the correct libnccl-gib environment variables
    source /usr/local/gib/scripts/set_nccl_env.sh

    # Get all relevant NCCL / env vars to pass to all workers
    ENV_VARS=$(echo ${!NCCL*} ${!OMPI*} LD_LIBRARY_PATH PATH | sed 's/ / -x /g')

    mpirun --hostfile /tmp/hostfile \
      -x $ENV_VARS  \
      --allow-run-as-root \
      --mca plm_rsh_no_tree_spawn 1 \
      --mca orte_keep_fqdn_hostnames 1 \
      --mca btl self,tcp \
      --mca btl_tcp_if_include eth0 \
      --bind-to none \
      --mca plm_rsh_agent "ssh -q -o LogLevel=ERROR -o StrictHostKeyChecking=no -p 222" \
      /third_party/nccl-tests/build/all_gather_perf -b 1K -e 8G -f 2 -g 1 -w 5 --iters 100 -c 1

else
    while ping -c 1 ${WORKERS_BASENAME}-0.${POSTFIX}; do
    sleep 5
done
fi

exit 0