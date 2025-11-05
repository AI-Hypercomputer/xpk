<!--
 Copyright 2025 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 -->

# Use Slurm like commands in XPK to execute workloads on top of GKE

XPK enables intuitive workload scheduling for ML researchers by offering Slurm-like commands and usage patterns.

This document provides a guide to fine-tuning Large Language Models (LLMs) using XPK Slurm Like commands. By leveraging the power of XPK and adapting its familiar Slurm command structures, users can efficiently train and optimize LLMs for specific use cases.

Slurm - XPK commands mapping:

| Slurm command | XPK command |
| --- | --- |
|Slurm login node| xpk shell |
|srun |xpk run  |
|sbatch |xpk batch |
|squeue |xpk job ls |
|scancel |xpk job cancel |
|sacct |xpk job info |
|sinfo |xpk info|
|Array jobs| See [Array jobs](#array-jobs) |
|Options |See [Options](#options)|



## Set up the environment

To recreate a usual Slurm setup, first prepare your environment by provisioning the cluster and creating and attaching storage. 

1. Export the variables for easier commands manipulation:

	```shell
	export CLUSTER_NAME="CLUSTER NAME"
	export COMPUTE_ZONE="COMPUTE ZONE"
	export PROJECT_ID="PROJECT ID"
	```
 	Replace the following variables:
	- `CLUSTER NAME` - name of your cluster
 	- `COMPUTE ZONE `- compute zone the cluster is at
  	- `PROJECT ID`- id of your project
3. Create a cluster using `xpk cluster create` command and providing machine type and provisioning mode of your choice. 
	```shell
	xpk cluster create \
	--cluster=$CLUSTER_NAME \
	--zone=$COMPUTE_ZONE \
	--project=$PROJECT_ID \
	--device-type=DEVICE_TYPE \
	--num-nodes=NUM_NODES \
	--PROVISIONING MODE \
	--enable-workload-identity  \
	--enable-gcpfilestore-csi-driver  \
	--default-pool-cpu-num-nodes=2 
 	```
 
	Replace the following variables:
	- `DEVICE_TYPE`: name of your machine
	- `NUM_NODES`: number of worker nodes in the nodepool
	- `PROVISIONING MODE`: provide provisioning mode of your choice.\
	`--enable-workload-identity` and `--enable-gcpfilestore-csi-driver` options are not required but they will speed up shared file system creation in the next step.

4. Create storage using `xpk storage create` command. XPK supports attaching GCS Bucket and Filestore storages and creating Filestore storage. If you already have the storage, follow the instructions outlined in [Storage](https://github.com/AI-Hypercomputer/xpk/blob/main/README.md#storage.)
	```shell
	xpk storage create STORAGE_NAME \
	--project=$PROJECT_ID \
	--zone=$COMPUTE_ZONE \
	--cluster=$CLUSTER_NAME \
	--type=gcpfilestore \
	--size=1024 \
	--access-mode=ReadWriteMany \
	--vol=home \
	--tier=REGIONAL \
	--mount-point /home \
	--auto-mount=true \
	--readonly=false 
	 ```
	Replace the following variables:
	- `STORAGE_NAME` name of your storage
	
 
5. Initialize XPK configuration. You can customize the configuration based on your needs, like in the example of Llama 3 finetuning provided below:

```shell
xpk config set shell-interactive-command /bin/bash
xpk config set shell-working-directory /home/llama3
xpk config set shell-image pytorch/pytorch:2.6.0-cuda12.6-cudnn9-devel
xpk config set batch-working-directory /home/llama3
xpk config set batch-image pytorch/pytorch:2.6.0-cuda12.6-cudnn9-runtime
```

## Prepare and upload scripts

### 1. Prepare scripts
This section specifies the changes needed for Slurm scripts used for batch executions for slurm-like commands in XPK.	
	
Currently xpk batch supports the following Slurm script cases:
1. Batch job with a single task and single step per task.
2. Batch job with multiple parallel tasks and single step per task.
3. Array job with a single task per job and single step per task.
As a result, XPK runs script validation to ensure it executes only the above use cases.

For successful script validation and later job execution, apply the following script updates:
- The number of steps in a task is limited to one. Thus, ensure there is only one step in the job script, invoked by one srun invocation.
- Ensure there is only one srun invocation per script and it is the final command in the script.
- Do not include other Slurm commands invocation within the script (e.g. scontrol, sinfo etc.).

### 2. xpk shell | Slurm login node - download scripts, models and data sets:
Through the xpk shell you can access the shared file system or edit files (e.g. when quick model changes are needed). It is the equivalent of the Slurm login node. To access the remote system use xpk shell command:
```shell
xpk shell \
--project $PROJECT \
--zone $ZONE \
--cluster $CLUSTER
```

This should open a console on the cluster with /home/llama3 set as the shell’s current working directory config. The subsequent commands in this section should be run on the login node within the XPK shell command. 

### 3. Create Python virtual environment and activate it

While in shell, run the below command:
```shell
python3 -m venv ./llama3_env
source ./llama3_env/bin/activate
```
As an alternative user may want to use conda - https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html
### 4. Upload your training scripts and training data to the created storage.
While in shell, run the below commands:
```shell
python3 <<EOF
import urllib.request
urllib.request.urlretrieve("https://raw.githubusercontent.com/AI-Hypercomputer/xpk/refs/heads/slurm-fixes/examples/llama-3.1-finetuning/requirements.txt", "requirements.txt")
urllib.request.urlretrieve("https://raw.githubusercontent.com/AI-Hypercomputer/xpk/refs/heads/slurm-fixes/examples/llama-3.1-finetuning/train.py", "train.py")
urllib.request.urlretrieve("https://raw.githubusercontent.com/AI-Hypercomputer/xpk/refs/heads/slurm-fixes/examples/llama-3.1-finetuning/training_data.jsonl", "training_data.jsonl")
EOF
```

### 5. Install necessary Python libraries
While in shell, run the below commands:
```shell
pip install -r requirements.txt
```

### 6. Download llama 3.1 model weights
While in shell,  download the model from a models platform e.g. HuggingFace
```shell
pip install huggingface_hub[cli]
huggingface-cli download "meta-llama/Llama-3.1-8B-Instruct" \
--local-dir "meta-llama/Llama-3.1-8B-Instruct" \
--token [hf_token]
```
For this to work you need to:
- create HuggingFace account
- create HuggingFace access token - hf_token
- request access to llama 3.1 models and wait for this request to be approved - https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct

Now you can exit the shell to continue with running batch commands:
```shell
exit
```

## Submit jobs - run CUDA and Llama 3 fine tuning script
Just like in Slurm, you can submit jobs in XPK using the following methods: batch jobs, array jobs and interactive jobs.

### 1. xpk run | srun - run CUDA in interactive mode
xpk run command runs a job in an interactive and blocking way, the results are printed over terminal and no other commands can be executed till the end.
```shell
xpk run \
--project [project] \
--zone [zone] \
--cluster [cluster] \
--nodes 1 \
--gpus-per-task nvidia.com/gpu:8 \
examples/llama-3.1-finetuning/check_cuda.sh
```

The interface should display the following:
```shell
CUDA available: True
Device count: 8
```

### 2. xpk batch | sbatch - run training script in batch mode
Once your script is ready, simply run the xpk batch command specifying which script to run to execute your workload.
```shell
xpk batch \
--project [project] \
--zone [zone] \
--cluster [cluster] \
examples/llama-3.1-finetuning/batch_script.sh
```
The command will finish displaying the name of the created job:
```shell
[XPK] Job name: xpk-def-app-profile-slurm-9zm2g
```

but the job execution might run longer depending on your job.
The output from the script execution will be written to relevant folders in the attached storage determined in -mount-point parameter of storage create command. You can see their content by running the following command from the xpk shell command:
```shell
tail -f example_script.out example_script.err
```
Once the execution is finished you should be able to see in the logs:
```shell
2025-02-21 13:02:08.431 GMT
{'train_runtime': 689.2645, 'train_samples_per_second': 0.048, 'train_steps_per_second': 0.004, 'train_loss': 2.037710189819336, 'epoch': 3.0}
```

## Cleanup
### 1. Stop shell
```shell
xpk shell stop \
--project $PROJECT \
--zone $ZONE \
--cluster $CLUSTER
```

### 2. Delete shared storage
```shell
xpk storage delete \
--project $PROJECT \
--zone $ZONE \
--cluster $CLUSTER
```

### 3. Delete XPK cluster
```shell
xpk cluster delete \
--project $PROJECT \
--zone $ZONE \
--cluster $CLUSTER
```
# More Slurm mode features:

## Job management - check the status of your job
### 1. xpk job ls | squeue

As in slurm squeue command, xpk uses xpk job ls command to list the jobs in the queue, which were scheduled through Slurm-like mode over a specific cluster.  It lists the jobs with the tasks completion status, duration and age
```shell
xpk job ls \
--project $PROJECT \
--zone $ZONE \
--cluster $CLUSTER
```

The output should look like this:
```shell
NAME                              PROFILE               LOCAL QUEUE        COMPLETIONS   DURATION   AGE
xpk-def-app-profile-slurm-6s6ff   xpk-def-app-profile   multislice-queue   1/1           8s         66m
xpk-def-app-profile-slurm-fz5z8   xpk-def-app-profile   multislice-queue   1/1           4s         63m
```

### 2. xpk cancel | scancel
If you want to cancel a job, use xpk cancel and provide the job id you wish to cancel.
```shell
xpk cancel <job_id>
```

### 3. xpk job info | sacct
To see the details of the job you submitted you can use xpk job info command. 
```shell
xpk job info JOB NAME \
--project $PROJECT \
--zone $ZONE \
--cluster $CLUSTER
```

The expected output should look like this:
```
Job name: xpk-def-app-profile-slurm-6s6ff
Script name: ./job.sh
Profile: default_xpk-def-app-profile
Labels:
  kjobctl.x-k8s.io/mode: Slurm
  kjobctl.x-k8s.io/profile: xpk-def-app-profile
  kueue.x-k8s.io/queue-name: multislice-queue
Mounts:
- mountPath: /slurm/scripts
  name: slurm-scripts
- mountPath: /slurm/env
  name: slurm-env
Pods:
- Name: xpk-def-app-profile-slurm-6s6ff-0-kgtv8
  Status: Completed
Entrypoint environment variables template:
- SLURM_ARRAY_JOB_ID=1
- SLURM_ARRAY_TASK_COUNT=1
- SLURM_ARRAY_TASK_MAX=0
- SLURM_ARRAY_TASK_MIN=0
- SLURM_TASKS_PER_NODE=1
- SLURM_CPUS_PER_TASK=
- SLURM_CPUS_ON_NODE=
- SLURM_JOB_CPUS_PER_NODE=
- SLURM_CPUS_PER_GPU=
- SLURM_MEM_PER_CPU=
- SLURM_MEM_PER_GPU=
- SLURM_MEM_PER_NODE=
- SLURM_GPUS=
- SLURM_NTASKS=1
- SLURM_NTASKS_PER_NODE=1
- SLURM_NPROCS=1
- SLURM_NNODES=1
- SLURM_SUBMIT_DIR=/slurm/scripts
- SLURM_SUBMIT_HOST=$HOSTNAME
- SLURM_JOB_NODELIST=xpk-def-app-profile-slurm-6s6ff-0.xpk-def-app-profile-slurm-6s6ff
- SLURM_JOB_FIRST_NODE=xpk-def-app-profile-slurm-6s6ff-0.xpk-def-app-profile-slurm-6s6ff
- SLURM_JOB_ID=$(expr $JOB_COMPLETION_INDEX \* 1 + $i + 1)
- SLURM_JOBID=$(expr $JOB_COMPLETION_INDEX \* 1 + $i + 1)
- SLURM_ARRAY_TASK_ID=$container_index
- SLURM_JOB_FIRST_NODE_IP=${SLURM_JOB_FIRST_NODE_IP:-""}
```

### 4. xpk info | sinfo
To monitor the status of queues, use xpk info command, which will provide an overview of the local and cluster queues as well as their status. 

```
[XPK] Local Queues usage 
QUEUE               ADMITTED_WORKLOADS    PENDING_WORKLOADS  2xv4-8:google.com/tpu
multislice-queue                     0                    0  0/8
[XPK] Cluster Queues usage 
QUEUE            ADMITTED_WORKLOADS    PENDING_WORKLOADS  2xv4-8:google.com/tpu
cluster-queue
```

## Array jobs

Slurm mode in XPK supports execution of array jobs, provided that the job scripts follow the requirements described in section Prepare your scripts . 
The script example below defines an array job named array_job with ten jobs (indices 1 through 10), each job using one task with one CPU and 4 GB of memory. The job runs in the compute partition with a wall time limit of one hour. Output for each job is directed to a file named array_job_%A_%a.out, where %A is the job ID and %a is the array index. Within each job, the SLURM_ARRAY_TASK_ID variable is used to construct an input file name, and srun executes my_program with one task and input from the corresponding file.

```bash
#!/bin/bash
#SBATCH --job-name=array_job
#SBATCH --array=1-10
#SBATCH -n 1
#SBATCH -c 1
#SBATCH --mem=4G
#SBATCH -p compute
#SBATCH -t 0-1
#SBATCH -o array_job_%A_%a.out

input_file=input_${SLURM_ARRAY_TASK_ID}.txt

srun -n 1 my_program < $input_file
```

## Options
Slurm like commands support the following Slurm-like options:

| Option | Description |
| --- | --- |
|-a, --array | array job  |
| --cpus-per-task | how much cpus a container inside a pod requires. |
|-e, --error | where to redirect std error stream of a task.  If not passed it proceeds to stdout, and is available via kubectl logs.|
|--gpus-per-task | how much gpus a container inside a pod requires.|
|- -i, –input | what to pipe into the script.|
|-J, --job-name=<jobname> | what is the job name |
| --mem-per-cpu | how much memory a container requires, it multiplies the number of requested cpus per task by mem-per-cpu.|
|--mem-per-task | how much memory a container requires.|
|-N, --nodes | number of pods to be used at a time - parallelism in indexed jobs.|
|-n, --ntasks| number of identical containers inside of a pod, usually 1.|
|-o, --output| where to redirect the standard output stream of a task. If not passed it proceeds to stdout, and is available via kubectl logs.|
|-D, --chdir| Change directory before executing the script.|
|--partition| local queue name|

Flags can be passed as a part of command line or inside of the script using the following format:
```
#SBATCH --job-name=array_job\
#SBATCH --output=array_job_%A_%a.out\
#SBATCH --error=array_job_%A_%a.err\
#SBATCH --array=1-22
```
Inline parameters (the ones provided in the CLI command) overwrite the parameters in the script.
