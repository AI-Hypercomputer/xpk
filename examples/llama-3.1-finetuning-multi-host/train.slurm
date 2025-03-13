#!/bin/bash

#SBATCH --job-name=llama3-finetune        # Job name
#SBATCH --nodes=2                         # Number of nodes
#SBATCH --gpus-per-task=nvidia.com/gpu:4  # Requested GPU per node/task
#SBATCH --output=%x-%j.out                # Standard output file (%x = job name, %j = job ID)
#SBATCH --error=%x-%j.err                 # Standard error file (%x = job name, %j = job ID)

# Activate Python environment
source llama3_env/bin/activate

# Run the training script
# https://pytorch.org/docs/stable/elastic/run.html
srun torchrun \
    --nnodes=${SLURM_NNODES} \
    --nproc_per_node=${SLURM_GPUS} \
    --max-restarts=3 \
    --rdzv-id=$TASK_ID \
    --rdzv-backend=c10d \
    --rdzv-endpoint="${SLURM_JOB_FIRST_NODE_IP}:29400" \
    train.py
