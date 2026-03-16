# Workload create pathways
Submits a Pathways-enabled workload to the cluster.

# Running the command
```shell #golden
xpk workload create-pathways --project=golden-project --zone=us-central1-a --cluster=golden-cluster --workload=golden-workload --command "bash hello" --tpu-type=v5p-8 --num-slices=1 --script-dir=/tmp
```
<!--
$ xpk workload create-pathways --project=golden-project --zone=us-central1-a --cluster=golden-cluster --workload=golden-workload --command "bash hello" --tpu-type=v5p-8 --num-slices=1 --script-dir=/tmp
Traceback (most recent call last):
  File "/usr/local/google/home/dominikrabij/pw-ss/bin/xpk", line 3, in <module>
    from xpk.main import main
  File "/usr/local/google/home/dominikrabij/pw-ss/src/xpk/main.py", line 39, in <module>
    from .parser.core import set_parser
  File "/usr/local/google/home/dominikrabij/pw-ss/src/xpk/parser/core.py", line 22, in <module>
    from .cluster import set_cluster_parser
  File "/usr/local/google/home/dominikrabij/pw-ss/src/xpk/parser/cluster.py", line 19, in <module>
    from ..commands.cluster import (
    ...<8 lines>...
    )
  File "/usr/local/google/home/dominikrabij/pw-ss/src/xpk/commands/cluster.py", line 84, in <module>
    from ..utils.validation import validate_dependencies_list, SystemDependency, should_validate_dependencies
  File "/usr/local/google/home/dominikrabij/pw-ss/src/xpk/utils/validation.py", line 23, in <module>
    from .dependencies.manager import ensure_dependency
  File "/usr/local/google/home/dominikrabij/pw-ss/src/xpk/utils/dependencies/manager.py", line 21, in <module>
    from .downloader import fetch_dependency
  File "/usr/local/google/home/dominikrabij/pw-ss/src/xpk/utils/dependencies/downloader.py", line 28, in <module>
    from src.xpk.utils.console import xpk_print
ModuleNotFoundError: No module named 'src'
-->
