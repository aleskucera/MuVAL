#!/bin/bash

#SBATCH --nodes=1                         # 1 node
#SBATCH --ntasks-per-node=8               # 8 CPUs per node
#SBATCH --time=12:00:00                   # time limits: 12 hours
#SBATCH --error=myJob.err                 # standard error file
#SBATCH --output=myJob.out                # standard output file
#SBATCH --partition=amdgpu                # partition name
#SBATCH --gres=gpu:1                      # number of GPUs per node
#SBATCH --mail-user=kuceral4@fel.cvut.cz  # where send info about job
#SBATCH --mail-type=ALL                   # what to send, valid type values are NONE, BEGIN, END, FAIL, REQUEUE, ALL

singularity run --nv singularity/alve-3d.sif python ./src/superpixels/supervised_partition.py --ROOT_PATH=/mnt/personal/kuceral4/S3DIS
