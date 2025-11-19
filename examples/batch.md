### Running batch tasks in xpk

### Preparation

This section should describe how to prepare volumes and add external files executed in script.

### Execution

To run xpk batch script run:
```bash
xpk batch --cluster my-cluster job.sh
```

To view results run:
```bash
kubectl get pods
```
Names of pods from slurm task execution begin with "xpk-def-app-profile-slurm".

To see logs run:
```bash
kubectl logs <pod_name>
```

