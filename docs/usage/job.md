
## Job List

*   Job List (see jobs submitted via batch command):

    ```shell
    python3 xpk.py job ls --cluster xpk-test
    ```

* Example Job List Output:

  ```
    NAME                              PROFILE               LOCAL QUEUE   COMPLETIONS   DURATION   AGE
    xpk-def-app-profile-slurm-74kbv   xpk-def-app-profile                 1/1           15s        17h
    xpk-def-app-profile-slurm-brcsg   xpk-def-app-profile                 1/1           9s         3h56m
    xpk-def-app-profile-slurm-kw99l   xpk-def-app-profile                 1/1           5s         3h54m
    xpk-def-app-profile-slurm-x99nx   xpk-def-app-profile                 3/3           29s        17h
  ```

## Job Cancel

*   Job Cancel (delete job submitted via batch command):

    ```shell
    python3 xpk.py job cancel xpk-def-app-profile-slurm-74kbv --cluster xpk-test
    ```
