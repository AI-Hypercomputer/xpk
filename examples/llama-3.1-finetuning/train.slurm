#!/bin/bash

#SBATCH --job-name=llama3-finetune        # Job name (for easy identification)
#SBATCH --nodes=1                      # Number of nodes (usually 1 for single-GPU training)
#SBATCH --ntasks=1                     # Number of tasks (processes) per node
#SBATCH --gpus-per-task=nvidia.com/gpu:8                    # Request 8 GPU per node

cd /home/llama3

# Activate your Python environment:
source llama3_env/bin/activate

# Run the training script
python3 train.py
