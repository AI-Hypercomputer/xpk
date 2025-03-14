#!/bin/bash
#SBATCH --job-name=nccl-tests
#SBATCH --cpus-per-task=8
#SBATCH --nodes=4
#SBATCH --ntasks=1

set -x
apt update -y
apt install -y iputils-ping
/scripts/container_entry.sh daemon &

export POSTFIX=$(hostname --fqdn | cut -d . -f 2-)
export WORKERS_BASENAME=$(hostname --fqdn | cut -d . -f 1 | rev | cut -d - -f 2- | rev )
export NODE_RANK=$SLURM_JOB_ID-1

for i in `seq 0 $(($SLURM_NNODES-1))`; do
  OTHER=${WORKERS_BASENAME}-${i}.${POSTFIX}
  until ssh -p 222 -o StrictHostKeyChecking=no $OTHER hostname; do
    echo "Waiting for ${OTHER}..."
    sleep 10
  done
  echo ${OTHER} port=222 slots=8 | tee -a /tmp/hostfile;
done

cat /tmp/hostfile
echo "nodepool size"
echo $(( ${SLURM_GPUS} * "${SLURM_NNODES}" ))
if [[ "${NODE_RANK}" -eq "0" ]]; then
    export NCCL_TESTS_SPLIT_MASK="0x0";
    export NCCL_LIB_DIR=$LD_LIBRARY_PATH
    ENV_VARS=$(echo ${!NCCL*} ${!OMPI*} LD_LIBRARY_PATH PATH | sed 's/ / -x /g')
    mpirun --hostfile /tmp/hostfile \
        -x $ENV_VARS \
        --allow-run-as-root \
        -np $(( ${SLURM_GPUS} * "${SLURM_NNODES}" )) \
        --mca orte_keep_fqdn_hostnames 1 \
        --mca btl tcp,self \
        --mca btl_tcp_if_include eth0 \
        --mca plm_rsh_agent "ssh -q -o LogLevel=ERROR -o StrictHostKeyChecking=no -p 222" \
        taskset -c 32-63 /scripts/demo_mpi_entry_with_config_profile.sh all_gather_perf \
          -b 1K -e 8G -f 2 -g 1 -w 5 --iters 100
else
    while ping -c 1 ${WORKERS_BASENAME}-0.${POSTFIX}; do
    sleep 5
done
fi
