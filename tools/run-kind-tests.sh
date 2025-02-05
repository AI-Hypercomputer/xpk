#!/bin/bash

set -o errexit

SOURCE_DIR="$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT_DIR="$SOURCE_DIR/.."
source "${SOURCE_DIR}/task_logger.sh"

KIND_CLUSTER_NAME="xpk-kind-test"
WORKLOAD_NAME="xpk-wl-test"
PW_WORKLOAD_NAME="xpk-pw-wl-test"

function cleanup() {
    python xpk.py kind delete --cluster ${KIND_CLUSTER_NAME}
    rm -f batch.sh
    rm -f create-shell.exp
}

trap 'reset; cleanup' EXIT

log_group_start "Create a cluster"
python xpk.py kind create --cluster ${KIND_CLUSTER_NAME}
log_group_end "Create a cluster"

log_group_start "List out the nodepools on the cluster"
python xpk.py cluster describe --kind-cluster --cluster ${KIND_CLUSTER_NAME}
log_group_end "List out the nodepools on the cluster"

log_group_start "Run a base-docker-image workload"
python xpk.py workload create --kind-cluster --cluster ${KIND_CLUSTER_NAME} --workload ${WORKLOAD_NAME} --command 'echo "Hello world!"' --docker-image=ubuntu
log_group_end "Run a base-docker-image workload"

log_group_start "Run xpk inspector with the workload created above"
python xpk.py inspector --kind-cluster --cluster ${KIND_CLUSTER_NAME} --workload ${WORKLOAD_NAME}
log_group_end "Run xpk inspector with the workload created above"

log_group_start "Wait for workload completion and confirm it succeeded"
python xpk.py workload list --kind-cluster --cluster ${KIND_CLUSTER_NAME} --wait-for-job-completion ${WORKLOAD_NAME} --timeout 300
log_group_end "Wait for workload completion and confirm it succeeded"

log_group_start "List out the workloads on the cluster"
python xpk.py workload list --kind-cluster --cluster ${KIND_CLUSTER_NAME}
log_group_end "List out the workloads on the cluster"

log_group_start "Run xpk info"
python xpk.py info --kind-cluster --cluster ${KIND_CLUSTER_NAME}
log_group_end "Run xpk info"

log_group_start "Delete the workload on the cluster"
python xpk.py workload delete --kind-cluster --cluster ${KIND_CLUSTER_NAME} --workload ${WORKLOAD_NAME}
log_group_end "Delete the workload on the cluster"

log_group_start "Create test script to execute in batch"
echo -e '#!/bin/bash \n#SBATCH --unknown-flag=value\n echo "Hello world from a test script!"' > batch.sh
log_group_end "Create test script to execute in batch"

log_group_start "Run a batch job on the cluster"
python xpk.py batch --kind-cluster --cluster ${KIND_CLUSTER_NAME} batch.sh --ignore-unknown-flags --array 1-5 --nodes 2 --ntasks 3 --time 60
log_group_end "Run a batch job on the cluster"

log_group_start "List out the jobs on the cluster"
python xpk.py job ls --kind-cluster --cluster ${KIND_CLUSTER_NAME} | grep 'xpk-def-app-profile-slurm-'
log_group_end "List out the jobs on the cluster"

log_group_start "Get created job name"
JOB_NAME=$(python xpk.py job ls --kind-cluster --cluster ${KIND_CLUSTER_NAME} | grep 'xpk-def-app-profile-slurm-' | head -1 | awk '{print $1}')
log_group_end "Get created job name"

log_group_start "Check created job"
kubectl get job ${JOB_NAME} -o jsonpath='{.metadata.labels}' | grep '"kueue.x-k8s.io/max-exec-time-seconds":"3600"'
job_spec=$(kubectl get job ${JOB_NAME} -o jsonpath='{.spec}')
echo "$job_spec" | grep '"completions":2'
echo "$job_spec" | grep '"parallelism":2'
echo "$job_spec" | jq '.template.spec.containers | length' | grep 3
log_group_end "Check created job"

log_group_start "Get job info for the last job created on the cluster"
python xpk.py job info --kind-cluster ${JOB_NAME} | grep -e "Entrypoint environment variables template:" -e "Job name:" -e "Labels:" -e "Mounts:" -e "Pods:" -e "Profile:" -e "Script name:" | wc -l | grep "7"
log_group_end "Get job info for the last job created on the cluster"

log_group_start "Cancel the batch job on the cluster"
python xpk.py job cancel ${JOB_NAME} --kind-cluster --cluster ${KIND_CLUSTER_NAME} | grep "job.batch/${JOB_NAME} deleted"
log_group_end "Cancel the batch job on the cluster"

log_group_start "Create shell and exit it immediately"
cat <<'EOF' >> create-shell.exp
##!/usr/bin/expect
spawn python ./xpk.py shell
expect "/ # "
send "exit\n"
EOF
chmod +x ./create-shell.exp
expect ./create-shell.exp
log_group_end "Create shell and exit it immediately"

log_group_start "Stop the shell"
python xpk.py shell stop
log_group_end "Stop the shell"
