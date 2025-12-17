# PYTHON_ARGCOMPLETE_OK

"""
Copyright 2024 Google LLC

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

r"""xpk (Accelerated Processing Kit).

Next Steps:
- Cluster describe is broken by Cacheimage since that counts as a workload.
- Cluster describe: count by jobset.
- If any instance goes down, bring down the whole job.
- How to more gracefully handle job failures, distinguishing between software
  and infra?
- Look into --docker-name and --docker-image.
  Shouldn't one string be adequate to express what we want?
- Apply learnings from about private, region, coredns, etc:
- Enable special preheater
- Make Argparse logic this a function?
  - Obvious logic that starts in main instead of here in code but args will
    not be a universal argument.
"""

from src.xpk.main import main

print("""
   _   _   _   _   _   _   _
  | | | | | | | | | | | | | |
  | | | | | | | | | | | | | |
  | | | | | | | | | | | | | |
  | | | | | | | | | | | | | |
  |_| |_| |_| |_| |_| |_| |_|

  (_) (_) (_) (_) (_) (_) (_)

  WARNING: Launching via python3 xpk.py is deprecated and will be removed in future versions.
  Please switch to the installed CLI:
  * Development: Run make install (editable install)
  * Production: Run pip install xpk (official release)
  New Usage: xpk <command>

  Read more at: https://github.com/AI-Hypercomputer/xpk/blob/main/docs/installation.md#3-install-xpk


""")

if __name__ == "__main__":
  main()
