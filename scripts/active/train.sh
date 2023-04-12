#!/bin/bash

# Set default values for variables
cpu_arg=""
load_model_arg=""
objects="voxels"
criterion="random"
dataset_size="null"


# Define a function to display help information
show_help () {
  echo "Usage: train.sh [options]"
  echo "Options:"
  echo "  --cpu                 Use CPU instead of GPU"
  echo "  --load_model          Load model from the latest checkpoint"
  echo "  -c, --criterion       Active learning criterion"
  echo "  -o, --objects         Active learning objects"
  echo "  -s, --size            Dataset size"
  echo "  -h, --help            Display this help and exit"
}

# Parse command line arguments
while [ "$#" -gt 0 ]; do
  case $1 in
    --cpu) cpu_arg="+device=cpu" ;;
    --load_model) load_model_arg="+load_model=False" ;;
    -c|--criterion) criterion="$2"; shift ;;
    -o|--objects) objects="$2"; shift ;;
    -s|--size) dataset_size="$2"; shift ;;
    -h|--help) show_help; exit 0 ;;
    *) echo "Unknown parameter passed: $1"; exit 1 ;;
  esac
  shift
done

# Print the values of the variables
echo "cpu: $cpu_arg"
echo "load_model: $load_model_arg"
echo "criterion: $criterion"
echo "objects: $objects"
echo "dataset_size: $dataset_size"

#singularity run --nv --bind /mnt --env WANDB_API_KEY=c54dade10e3c04fca21bf96016298e59b1e030ae \
#            singularity/alve-3d.sif python main.py "$cpu_arg" "$load_model_arg" \
#            action=train_active \
#            active.selection_objects="$objects" \
#            active.criterion="$criterion" \
#            train.dataset_size="$dataset_size"