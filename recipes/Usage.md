# View XPK version and usage instructions

```shell #golden
xpk
```
<!--
$ xpk
[XPK] Starting xpk v0.0.0
[XPK] Welcome to XPK! See below for overall commands:
usage: xpk [-h] [--dry-run | --no-dry-run]
           {workload,storage,cluster,inspector,info,version,config} ...

xpk command

options:
  -h, --help            show this help message and exit
  --dry-run, --no-dry-run
                        If given `--dry-run`, xpk will print the commands it
                        wants to run but not run them. This is perfect in
                        cases where xpk might branch based on the output of
                        commands

xpk subcommands:
  {workload,storage,cluster,inspector,info,version,config}
                        Top level commands
    workload            Commands around workload management
    storage             Commands around storage management
    cluster             Commands around creating, deleting, and viewing
                        clusters.
    inspector           Commands around investigating workload, and Kueue
                        failures.
    info                Commands around listing kueue clusterqueues and
                        localqueues.
    version             Command to get xpk version
    config              Commands to set and retrieve values from xpk config.
usage: xpk cluster [-h]
                   {create,create-pathways,create-ray,delete,cacheimage,describe,list,adapt} ...

options:
  -h, --help            show this help message and exit

cluster subcommands:
  {create,create-pathways,create-ray,delete,cacheimage,describe,list,adapt}
                        These are commands related to cluster management. Look
                        at help for specific subcommands for more details.
    create              Create cloud clusters.
    create-pathways     Create Pathways-on-Cloud clusters.
    create-ray          Create RayCluster
    delete              Delete cloud clusters.
    cacheimage          Cache image.
    describe            Describe a cluster.
    list                List cloud clusters.
    adapt               Adapt an existing cluster for XPK.
usage: xpk workload [-h] {create,create-pathways,delete,list} ...

options:
  -h, --help            show this help message and exit

workload subcommands:
  {create,create-pathways,delete,list}
                        `create`, `create-pathways`, `list` and `delete`
                        workloads on clusters
    create              Create a new job.
    create-pathways     Create a new job.
    delete              Delete job.
    list                List jobs.
usage: xpk info [-h] --cluster CLUSTER [--namespace NAMESPACE]
                [--clusterqueue | --localqueue] [--project PROJECT]
                [--project-number PROJECT_NUMBER] [--zone ZONE]
                [--dry-run | --no-dry-run]
                [--skip-validation | --no-skip-validation]
                [--quiet | --no-quiet]
                [--sandbox-kubeconfig | --no-sandbox-kubeconfig]

options:
  -h, --help            show this help message and exit

Required Arguments:
  Arguments required for info.

  --cluster CLUSTER     Cluster to which command applies.

Optional Arguments:
  Arguments optional for info.

  --namespace NAMESPACE
                        Namespace to which resources and queues belong
  --clusterqueue        Show only clusterqueues resources and usage
  --localqueue          Show only localqueues resources and usage
  --project PROJECT     GCE project name, defaults to "gcloud config project."
  --project-number PROJECT_NUMBER
                        GCE project number. If provided, skips the Cloud
                        Resource Manager API call to translate project ID to
                        project number. Useful when the API is not enabled or
                        you lack permissions.
  --zone ZONE           GCE zone, e.g. us-central2-b, defaults to "gcloud
                        config compute/zone." Only one of --zone or --region
                        is allowed in a command.
  --dry-run, --no-dry-run
                        If given `--dry-run`, xpk will print the commands it
                        wants to run but not run them. This is perfect in
                        cases where xpk might branch based on the output of
                        commands
  --skip-validation, --no-skip-validation
                        Skip dependency validation checks (kubectl, gcloud,
                        docker, etc). Independent of --dry-run.
  --quiet, --no-quiet   Disables prompting before unintended destructive
                        actions.
  --sandbox-kubeconfig, --no-sandbox-kubeconfig
                        Whether to sandbox k8s config. (Experimental)
usage: xpk version [-h] [--project PROJECT] [--project-number PROJECT_NUMBER]
                   [--zone ZONE] [--dry-run | --no-dry-run]
                   [--skip-validation | --no-skip-validation]
                   [--quiet | --no-quiet]
                   [--sandbox-kubeconfig | --no-sandbox-kubeconfig]

options:
  -h, --help            show this help message and exit
  --project PROJECT     GCE project name, defaults to "gcloud config project."
  --project-number PROJECT_NUMBER
                        GCE project number. If provided, skips the Cloud
                        Resource Manager API call to translate project ID to
                        project number. Useful when the API is not enabled or
                        you lack permissions.
  --zone ZONE           GCE zone, e.g. us-central2-b, defaults to "gcloud
                        config compute/zone." Only one of --zone or --region
                        is allowed in a command.
  --dry-run, --no-dry-run
                        If given `--dry-run`, xpk will print the commands it
                        wants to run but not run them. This is perfect in
                        cases where xpk might branch based on the output of
                        commands
  --skip-validation, --no-skip-validation
                        Skip dependency validation checks (kubectl, gcloud,
                        docker, etc). Independent of --dry-run.
  --quiet, --no-quiet   Disables prompting before unintended destructive
                        actions.
  --sandbox-kubeconfig, --no-sandbox-kubeconfig
                        Whether to sandbox k8s config. (Experimental)
usage: xpk config [-h] [--project PROJECT] [--project-number PROJECT_NUMBER]
                  [--zone ZONE] [--dry-run | --no-dry-run]
                  [--skip-validation | --no-skip-validation]
                  [--quiet | --no-quiet]
                  [--sandbox-kubeconfig | --no-sandbox-kubeconfig]
                  {set,get} ...

options:
  -h, --help            show this help message and exit
  --project PROJECT     GCE project name, defaults to "gcloud config project."
  --project-number PROJECT_NUMBER
                        GCE project number. If provided, skips the Cloud
                        Resource Manager API call to translate project ID to
                        project number. Useful when the API is not enabled or
                        you lack permissions.
  --zone ZONE           GCE zone, e.g. us-central2-b, defaults to "gcloud
                        config compute/zone." Only one of --zone or --region
                        is allowed in a command.
  --dry-run, --no-dry-run
                        If given `--dry-run`, xpk will print the commands it
                        wants to run but not run them. This is perfect in
                        cases where xpk might branch based on the output of
                        commands
  --skip-validation, --no-skip-validation
                        Skip dependency validation checks (kubectl, gcloud,
                        docker, etc). Independent of --dry-run.
  --quiet, --no-quiet   Disables prompting before unintended destructive
                        actions.
  --sandbox-kubeconfig, --no-sandbox-kubeconfig
                        Whether to sandbox k8s config. (Experimental)

config subcommands:
  {set,get}
    set                 set config key
    get                 get config key
usage: xpk storage [-h] {attach,list,detach,create,delete} ...

options:
  -h, --help            show this help message and exit

storage subcommands:
  {attach,list,detach,create,delete}
                        These are commands related to storage management. Look
                        at help for specific subcommands for more details.
    attach              attach XPK Storage.
    list                List XPK Storages.
    detach              Detach XPK Storage.
    create              create XPK Storage.
    delete              Delete XPK Storage.
[XPK] XPK Done.
-->
