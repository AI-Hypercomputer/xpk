# Running NCCL tests on GPU clusters using xpk

This document provides an introduction to running tests for the NVIDIA Collective Communications Library (NCCL). NCCL is a high-performance, multi-GPU communications library used in deep learning and other applications. The test suite helps verify the correct functionality and performance of NCCL on your system. Please visit [NCCL tests github](https://github.com/NVIDIA/nccl-tests?tab=readme-ov-file#nccl-tests) to learn more about NCCL and running it.

Steps presented in this document are designed to run on A3 Ultra machines (`DEVICE_TYPE=h200-141gb-8`).

### 1. Create cluster

Skip this step if you have already provisioned a GKE cluster with A3 Ultra machines.

First step is to create a cluster with A3 Ultra machine. Execute command below:

```
python3 xpk.py cluster create \
    --cluster=$CLUSTER_NAME --device-type=$DEVICE_TYPE \
    --zone=$COMPUTE_ZONE  --project=$PROJECT_ID \
    --num-nodes=$CLUSTER_NUM_NODES --reservation=$RESERVATION_ID
```

### 2. Run NCCL workload

To run NCCL tests on created cluster a workload will be submitted using xpk as follows:

```
python3 xpk.py workload create \
    --workload=nccl-test --command="./examples/nccl/nccl.sh" \
    --base-docker-image=us-docker.pkg.dev/gce-ai-infra/gpudirect-gib/nccl-plugin-gib-diagnostic:v1.0.3 \
    --cluster=$CLUSTER_NAME --device-type=$DEVICE_TYPE \
    --zone=$COMPUTE_ZONE  --project=$PROJECT_ID \
    --num-nodes=$WORKLOAD_NUM_NODES
```
