### Running NCCL on GPU clusters using xpk

This document provides a brief introduction to running tests for the NVIDIA Collective Communications Library (NCCL). NCCL is a high-performance, multi-GPU communications library used in deep learning and other applications.  The test suite helps verify the correct functionality and performance of NCCL on your system. Please visit [NCCL tests github](https://github.com/NVIDIA/nccl-tests?tab=readme-ov-file#nccl-tests) to learn more about NCCL and running it.

Steps presented in this document runs on A3 ultra machines. To change machine type to A3 mega set: `--device-type=h100-mega-80gb-8`

## Create cluster

First step is to create a cluster with A3 ultra machine. Execute below step:
```
python3 xpk.py cluster create \
--cluster $CLUSTER_NAME --device-type=h200-141gb-8 \
--zone=$COMPUTE_ZONE  --project=$PROJECT_ID \
--num-nodes=4 --reservation=$RESERVATION_ID
```

## Run NCCL workload

To run NCCL tests on created cluster workload will be submitted using xpk. See below steps:
```
python3 xpk.py workload create \
--workload=$WORKLOAD_NAME --command="./examples/running-nccl/nccl.sh" \
--docker-image=us-docker.pkg.dev/gce-ai-infra/gpudirect-gib/nccl-plugin-gib-diagnostic:v1.0.3 \
--cluster=$CLUSTER_NAME --device-type=h200-141gb-8 \
--zone=$COMPUTE_ZONE  --project=$PROJECT_ID \
--num-nodes=$WORKLOAD_NUM_NODES
```
