<h1 align="center">ALVE-3D</h1>

<p align="center">
<img src="https://img.shields.io/badge/Python-14354C?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/PyTorch-%23EE4C2C.svg?style=for-the-badge&logo=PyTorch&logoColor=white" alt="PyTorch"/>
<img src="https://img.shields.io/badge/TensorFlow-%23FF6F00.svg?style=for-the-badge&logo=TensorFlow&logoColor=white" alt="Tensorflow"/>
<img src="https://img.shields.io/badge/numpy-%23013243.svg?style=for-the-badge&logo=numpy&logoColor=white" alt="NumPy"/>
</p>

## Introduction

This code is official implementation of the project **ALVE-3D (Active Learning with Viewpoint Entropy
for 3D Semantic Segmentation)**. We propose a novel active learning framework for 3D semantic segmentation based on the
viewpoint entropy.
The framework is will be evaluated on SemanticKITTI and SemanticUSL datasets.

## Overview

- [Requirements](#requirements)
- [Project Architecture](#project-architecture)
    - [Repository Structure](#repository-structure)
    - [Basic Principles](#basic-principles)
        - [Configuration](#configuration)
        - [Monitoring](#monitoring)
        - [Logging](#logging)
- [Usage](#usage)
    - [Available Demos](#available-demos)
- [Implementation Details](#implementation-details)
    - [Dataset](#dataset)
    - [Sample Class](#sample-class)
    - [Sequence Class](#sequence-class)

## Requirements

- Python 3.9

for all other requirements, please see `environment.yaml`. You can recreate the environment with:

    conda env create -f environment.yaml

## Project Architecture

### Repository Structure

    .
    ├── conf
    ├── data
    │   ├── SemanticKITTI -> /path/to/SemanticKITTI
    │   └── SemanticUSL -> /path/to/SemanticUSL
    ├── models
    │   └── pretrained
    ├── outputs
    ├── scripts
    ├── singularity
    ├── src
    ├── demo.py
    ├── environment.yaml
    └── main.py

- `conf`: Folder containing the configuration files for the experiments. The configuration files are in YAML format.
  The project depends on [Hydra](https://hydra.cc/) for configuration management. More details about the configuration
  in the [Configuration](#configuration) section.
- `data`: Folder containing the symbolic links to the datasets.
  It is recommended to create symbolic links to the datasets in this folder, but you can also change the paths
  in the configuration files.
- `models`: Folder containing the models that are used in the experiments.
  For evaluation of the pretrained models, please use the pretrained directory.
- `outputs`: Folder containing logs of the experiments. More details in the [Logging](#logging) section.
- `scripts`: Folder containing the scripts for training, evaluation and visualization of the models on RCI cluster.
- `src`: Folder containing the source code of the project.
- `demo.py`: Script is used for demo of the finished features of the project.
- `main.py`: The main script of the project. It is used for training and testing of the model. More details in
  the [Usage](#usage) section.

### Basic Principles

#### Configuration

This section describes the basic principles of the project. For faster development, the [Hydra](https://hydra.cc/) is
used for configuration management. Before running the project, you should set the configuration file. Let's dive into
the
details.

The main configuration file is `conf/config.yaml`. This file contains the following sections:

- `defaults`: These are default configuration files. The items have the following syntax `directory:filename`. The
  directory
  is the relative path to the `conf` directory. The filename is the name of the configuration file without the
  extension.
  The configuration files are loaded in the order they are specified in the list.
- **other variables**: These are the variables that are defined directly in the `config.yaml` file or in the one of
  the `run`
  configuration files. These variables are used for determining, what should be run in the project.

    1. **action**: This variable is used for determining, what action should be performed. The possible values are:
        - `train`: This value is used for training of the model. (only when running `main.py`)
        - `test`: This value is used for testing of the model. (only when running `main.py`)

    2. **node**: This variable is used for determining, what node is the project running on. The possible values
       are:
        - `master` (PC): This value is used for running the project on a local machine.
        - `slave` (RCI): This value is used for running the project on a cluster.

    3. **connection**: This variable is used for determining, what connection is used for running the project. The
       possible values are:
        - `local`: This value is used for running the project on a local machine.
        - `remote`: When this value is used, it indicates, that the communication between the master and the slave
          will be used.

---

*Supported configurations* - The project supports the following configurations:

- `train`/`test` on `master` with `local` connection - This configuration is used for development on a local
  machine. The development configuration files will be loaded. The monitoring of the progress will be used.

- `train`/`test` on `master` with `remote` connection - This configuration is used for supervision of the
  training and the testing on the RCI cluster. The monitoring of the progress will be used.

- `train`/`test` on `slave` with `remote` connection - This configuration will be activated on the RCI
  cluster when previous configuration is used. This configuration is used for training and testing of the model on
  the RCI cluster.

- `train`/`test` on `slave` with `local` connection - This configuration is used for development on the RCI
  cluster. The development configuration files will be loaded. The monitoring software will not be used.

> **Note**: These configurations are only for `main.py`. When running the `demo.py` script, the `action` variable is
> used for determining, what demo should be run. More about supported demos can be found in the [Usage](#usage).

---

#### Monitoring

There was mentioned monitoring software. The project uses [Tensorboard](https://www.tensorflow.org/tensorboard) for the
monitoring. When running the project on the local machine (the `master` node is used), the Tensorboard will be started
automatically, even when the computing will be done on the RCI cluster (the `remote` connection is used). This is
possible by synchronization of the Tensorboard logs between the local machine and the RCI cluster. More information
logging can be found in the [Logging](#logging) section.

---

#### Logging

The project uses Hydra logging. It is configured in the `conf/hydra` files so that the logs will be saved in
the `outputs/{date}/{time}` directory. The `date` and `time` are the date and the time when the project was started.
Then there are the following subdirectories:

- `master`: This directory contains the logs of the `master` node when is used.
- `slave`: This directory contains the logs of the `slave` node when is used.
- *tensorboard file*: This file is used for the Tensorboard. It is created when the Tensorboard is used (when the
  `master` node is used).

## Usage

The project can be used for training and testing of the model. Run the `main.py` script for training and testing of the
model by:

    python main.py action={action} node={node} connection={connection}

more information about the configuration variables can be found in the [Configuration](#configuration) section.

You can also run the `demo.py` script for demo of the finished features of the project by:

    python demo.py action={action}

#### Available Demos

- `simulation`: Demo of the remote communication between the `master` and the `slave` node.
- `global_cloud`: Demo of the global point cloud visualization.
- `sample`: Demo of the sample visualization.
- `sample_formats`: Demo of 3 different sample formats.
- `paths`: Demo of the absolute paths in the configuration files.

## Implementation Details

### Dataset

The object SemanticDataset is Pytorch Dataset wrapper for SemanticKITTI and SemanticUSL datasets.
It is used for loading the data and creating the global map of the dataset.

Dataset uses two new [dataclasses](https://docs.python.org/3/library/dataclasses.html) for storing the data:

- `Sample`: This dataclass is used for storing the data of a single sample. It contains everything that is needed for
  training and evaluation of the model. For better performance, only the essential data are stored permanently in the
  dataset and the rest of are loaded on demand (e.g. point clouds, labels, etc.). More information about the dataclass
  can be found in the Sample section.
- `Sequence`: This dataclass is used for storing information about a structure of a single sequence. The structure of a
  sequence is defined by the `sequence_structure` parameter in the configuration file. The structure is used for
  creating the global map of the dataset.

### Sample class

The `Sample` class is used for storing the data of a single sample. It contains everything that is needed for training
and visualization of the dataset.
For better performance, only the essential data are stored permanently in the dataset and the rest of are loaded on
demand (e.g. point clouds, labels, etc.).
There are 3 main types of data that can be loaded in the `Sample` class:

- `learning_data`: This data are used for training and evaluation of the model. The data are loaded from the dataset
  and stored permanently in the `Sample` class by function `load_learning_data`.
- `semantic_cloud_data`: This data are used for visualization of the semantic point cloud. The data are loaded from the
  dataset
  and stored permanently in the `Sample` class by function `load_semantic_cloud`.
- `depth_image_data`: This data are used for visualization of the depth image. The data are loaded from the dataset
  and stored permanently in the `Sample` class by function `load_depth_image`.

### Sequence class

The `Sequence` class is used for storing information about a structure of a single sequence. The structure
of a sequence is defined by the `sequence_structure` parameter in the configuration file. It is used
loading the data and creating `Sample` objects by calling the `get_samples` function.




