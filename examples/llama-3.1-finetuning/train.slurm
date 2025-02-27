#!/bin/bash

#SBATCH --job-name=llama3-finetune        # Job name
#SBATCH --nodes=1                         # Number of nodes
#SBATCH --gpus-per-task=nvidia.com/gpu:8  # Request 8 GPU per node/task
#SBATCH --output=%x-%j.out                # Standard output file (%x = job name, %j = job ID)
#SBATCH --error=%x-%j.err                 # Standard error file (%x = job name, %j = job ID)

# Activate Python environment
cd /home/llama3/
source llama3_env/bin/activate

# Run the training script
python3 train.py
