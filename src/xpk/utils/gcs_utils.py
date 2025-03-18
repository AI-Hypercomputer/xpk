"""
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
"""

from pathlib import Path

from google.cloud.storage import transfer_manager, Client
from .console import xpk_print


def upload_file_to_gcs(
    storage_client: Client, bucket_name: str, bucket_path: str, file: str
):
  bucket = storage_client.bucket(bucket_name)
  blob = bucket.blob(bucket_path)
  blob.upload_from_filename(file)


def upload_directory_to_gcs(
    storage_client: Client,
    bucket_name: str,
    bucket_path: str,
    source_directory: str,
    workers: int = 8,
):
  """Upload every file in a directory, including all files in subdirectories.

  Each blob name is derived from the filename, not including the `directory`
  parameter itself. For complete control of the blob name for each file (and
  other aspects of individual blob metadata), use
  transfer_manager.upload_many() instead.
  """
  xpk_print(f"Uploading directory {source_directory} to bucket {bucket_name}")
  bucket = storage_client.bucket(bucket_name)

  directory_as_path_obj = Path(source_directory)
  paths = directory_as_path_obj.rglob("*")

  # Filter so the list only includes files, not directories themselves.
  file_paths = [path for path in paths if path.is_file()]

  # These paths are relative to the current working directory. Next, make them
  # relative to `directory`
  relative_paths = [path.relative_to(source_directory) for path in file_paths]

  # Finally, convert them all to strings.
  string_paths = [str(path) for path in relative_paths]

  xpk_print(f"Found {len(string_paths)} files.")
  # Start the upload.
  results = transfer_manager.upload_many_from_filenames(
      bucket=bucket,
      filenames=string_paths,
      source_directory=source_directory,
      max_workers=workers,
      blob_name_prefix=bucket_path,
  )

  for name, result in zip(string_paths, results):
    # The results list is either `None` or an exception for each filename in
    # the input list, in order.

    if isinstance(result, Exception):
      xpk_print(f"Failed to upload {name} due to exception: {result}")
    else:
      xpk_print(f"Uploaded {name} to {bucket.name}.")


def check_file_exists(
    storage_client: Client, bucket_name: str, filename: str
) -> bool:
  xpk_print(f"Checking if file {filename} exists in bucket: {bucket_name}")
  bucket = storage_client.get_bucket(bucket_name)
  is_file: bool = bucket.blob(filename).exists()
  return is_file


def download_bucket_to_dir(
    storage_client: Client,
    bucket_name: str,
    bucket_path: str,
    destination_directory: str = "",
    workers: int = 8,
    max_results: int = 1000,
):
  """Download all of the blobs in a bucket, concurrently in a process pool.

  The filename of each blob once downloaded is derived from the blob name and
  the `destination_directory `parameter. For complete control of the filename
  of each blob, use transfer_manager.download_many() instead.

  Directories will be created automatically as needed, for instance to
  accommodate blob names that include slashes.
  """
  bucket = storage_client.bucket(bucket_name)

  blob_names = [
      blob.name
      for blob in bucket.list_blobs(max_results=max_results, prefix=bucket_path)
  ]

  results = transfer_manager.download_many_to_path(
      bucket,
      blob_names,
      destination_directory=destination_directory,
      max_workers=workers,
  )

  for name, result in zip(blob_names, results):
    if isinstance(result, Exception):
      xpk_print(f"Failed to download {name} due to exception: {result}")
    else:
      xpk_print(f"Downloaded {name} to {destination_directory + name}.")
