
import yaml
from ...core.storage import GCS_FUSE_TYPE, get_storage_volumes_yaml_dict

def decorate_jobset(jobset_manifest_str, storages) -> str:
  """
  Decorates a JobSet manifest with the necessary storages.

  Args:
    jobset_manifest_str: The JobSet manifest as a YAML string.

  Returns:
    The modified JobSet manifest as a YAML string.
  """

  manifest = yaml.safe_load(jobset_manifest_str)
  storage_volumes = get_storage_volumes_yaml_dict(storages)
  for job in manifest['spec']['replicatedJobs']:
    job_manifest = job['template']
    add_storage_annotations(job_manifest, storages)
    add_storage_volumes(job_manifest, storage_volumes)
  return yaml.dump(manifest, sort_keys=False)


def add_storage_annotations(job_manifest, storages):
  """Adds or updates storage annotations in the Pod template."""
  annotations = job_manifest['spec']['template']['metadata']['annotations']
  gcs_present = [storage.type == GCS_FUSE_TYPE for storage in storages]
  if gcs_present:
    annotations.update({'gke-gcsfuse/volumes': 'true'})


def add_storage_volumes(job_manifest, storage_volumes):
  volumes = job_manifest['spec']['template']['spec']['volumes']
  volumes.extend(storage_volumes)

