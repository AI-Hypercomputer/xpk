#!/bin/bash

#SBATCH --job-name=llama3-finetune        # Job name
#SBATCH --nodes=2                         # Number of nodes
#SBATCH --gpus-per-task=nvidia.com/gpu:8  # GPU per node/task
#SBATCH --output=%x-%j.out                # Standard output file (%x = job name, %j = job ID)
#SBATCH --error=%x-%j.err                 # Standard error file (%x = job name, %j = job ID)

# Activate Python environment
source llama3_env/bin/activate

echo "Master address: ${SLURM_JOB_FIRST_NODE_IP}:29400"

# Run the training script
torchrun \
    --nproc_per_node=${SLURM_GPUS} \
    --nnodes=${SLURM_NNODES} \
    --rdzv-id="${TASK_ID}" \
    --rdzv-backend="c10d" \
    --rdzv-endpoint="${SLURM_JOB_FIRST_NODE_IP}:29400" \
    train.py
