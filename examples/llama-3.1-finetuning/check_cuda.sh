#!/bin/bash

cd /home/llama3
source llama3_env/bin/activate

python3 <<EOF
import torch
print("CUDA available:", torch.cuda.is_available())
print("Device count:", torch.cuda.device_count())
EOF
