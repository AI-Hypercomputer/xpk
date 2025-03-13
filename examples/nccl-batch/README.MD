# Running NCCL tests on GPU clusters using xpk slurm mode.

This document provides an introduction to running tests for the NVIDIA Collective Communications Library (NCCL). NCCL is a high-performance, multi-GPU communications library used in deep learning and other applications. The test suite helps verify the correct functionality and performance of NCCL on your system. Please visit [NCCL tests github](https://github.com/NVIDIA/nccl-tests?tab=readme-ov-file#nccl-tests) to learn more about NCCL and running it.

Steps presented in this document are designed to run on A3 Ultra and A3 Mega machines (`DEVICE_TYPE=h200-141gb-8` or `DEVICE_TYPE=h100-mega-80gb-8`).

### 1. Create cluster

Skip this step if you have already provisioned a GKE cluster with A3 Ultra or A3 Mega machines.

First step is to create a cluster with A3 Ultra or A3 Mega machine. Execute command below:

```
python3 xpk.py cluster create \
    --cluster=$CLUSTER_NAME --device-type=$DEVICE_TYPE \
    --zone=$COMPUTE_ZONE  --project=$PROJECT_ID \
    --num-nodes=$CLUSTER_NUM_NODES --reservation=$RESERVATION_ID
```

### 2. Run NCCL workload

The command to run NCCL tests on A3 clusters depends on the type of machine.


#### A3 Mega

It is neccessary to set batch image to run nccl tests in slurm mode.

```bash
python3 xpk.py config set batch-working-directory /home/nccl
```

Docker image provided by google will be used.
```bash
python3 xpk.py config set batch-image us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpxo/nccl-plugin-gpudirecttcpx-dev:v1.0.8-1
```

Command `xpk run` will be used to start running nccl tests.

```bash
python3 xpk.py run \
    --cluster $CLUSTER_NAME --zone $COMPUTE_ZONE \
    --project $PROJECT_ID \
    --nodes $NUM_NODES \
    --gpus-per-task nvidia.com/gpu:8 \
    examples/nccl-batch/a3mega.slurm
```

### Troubleshooting

If you are getting a 403 Forbidden Error when creating docker image, make sure to add `us-docker.pkg.dev` to the list of gcloud credential helpers using this command:

```bash
gcloud auth configure-docker us-docker.pkg.dev
```