#!/usr/bin/env python
#filename: hello_pytorch_distributed.py

import os
import torch
import torch.distributed as dist
import socket

hostname = socket.getfqdn()
local_rank = int(os.environ["LOCAL_RANK"])
global_rank = int(os.environ["SLURM_PROCID"])

torch.cuda.set_device(local_rank)
dist.init_process_group("nccl")
print(f"Hello from rank {dist.get_rank()} on SLURM PROCID {global_rank} out of {dist.get_world_size()} on {hostname}. Before barrier.")
dist.barrier()
print(f"Rank {dist.get_rank()} reached the other side of the barrier.")
dist.destroy_process_group()
