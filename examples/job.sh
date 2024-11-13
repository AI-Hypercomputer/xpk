#!/bin/bash

#SBATCH --array=1-3%2

echo "Now processing task ID: ${SLURM_ARRAY_TASK_ID}"
for i; do 
   echo $i 
done
sleep 30
echo "exit"

exit 0