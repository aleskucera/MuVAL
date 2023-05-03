import os
import logging

import torch
import wandb
import numpy as np
from omegaconf import DictConfig

from .trainer import SemanticTrainer
from src.selection import get_selector
from src.utils.experiment import Experiment
from src.utils.log import log_dataset_statistics
from src.datasets import SemanticDataset, SemanticKITTIDataset

log = logging.getLogger(__name__)


def train_model(cfg: DictConfig, experiment: Experiment, device: torch.device) -> None:
    """ Trains a semantic segmentation model of the full dataset.

    :param cfg: The configuration object containing the dataset parameters.
    :param experiment: The experiment object containing the names of the artifacts to be used.
    :param device: The device to be used for the training.
    """

    train_ds = SemanticDataset(split='train', cfg=cfg.ds, dataset_path=cfg.ds.path,
                               project_name=experiment.info, num_clouds=cfg.train.dataset_size, al_experiment=False)
    val_ds = SemanticDataset(split='val', cfg=cfg.ds, dataset_path=cfg.ds.path,
                             project_name=experiment.info, num_clouds=cfg.train.dataset_size, al_experiment=False)

    stats = train_ds.statistics
    weights = 1 / (stats['class_distribution'] + 1e-6)

    if abs(stats['labeled_ratio'] - 1) > 1e-6:
        log.error(f'Label ratio is not 1: {stats["labeled_ratio"]}')
        raise ValueError

    trainer = SemanticTrainer(cfg=cfg, train_ds=train_ds, val_ds=val_ds, device=device, weights=weights,
                              model=None, model_name=experiment.model, history_name=experiment.history)
    trainer.train()


def train_model_active(cfg: DictConfig, experiment: Experiment, device: torch.device) -> None:
    """ Trains a semantic segmentation model using active learning. This function executes only one iteration of the
    training. The training is executed in the following steps:
        1. Load the model and the history from the artifacts.
        2. Load the dataset and initialize all labels to unlabeled.
        3. Create a Selector object.
        4. Download the information about the labeled voxels from the artifact and using Selector,
           label the voxels that has been previously selected.
        5. Train the model.
        6. Save the model during the training and the history of the training to the artifact.

    :param cfg: The configuration object containing the dataset parameters.
    :param experiment: The experiment object containing the names of the artifacts to be used.
    :param device: The device to be used for the training.
    """

    criterion = cfg.active.strategy
    selection_objects = cfg.active.cloud_partitions

    model_version = cfg.active.model_version
    selection_version = cfg.active.selection_version

    load_model = cfg.load_model if 'load_model' in cfg else False

    # Load Datasets
    train_ds = SemanticDataset(split='train', cfg=cfg.ds, dataset_path=cfg.ds.path, project_name=experiment.info,
                               num_clouds=cfg.train.dataset_size, al_experiment=True, selection_mode=False)
    val_ds = SemanticDataset(split='val', cfg=cfg.ds, dataset_path=cfg.ds.path, project_name=experiment.info,
                             num_clouds=cfg.train.dataset_size, al_experiment=True, selection_mode=False)

    # Load Selector for selecting labeled voxels
    selector = get_selector(selection_objects=selection_objects, criterion=criterion,
                            dataset_path=cfg.ds.path, project_name=experiment.info,
                            cloud_paths=train_ds.cloud_files, device=device,
                            cfg=cfg)

    # Load selected voxels from W&B
    if cfg.active.selection is not None:
        selection_file = cfg.active.selection.split('/')[-1].split(':')[0]
        artifact_dir = wandb.use_artifact(cfg.active.selection).download()
        selection = torch.load(os.path.join(artifact_dir, f'{selection_file}.pt'))
    else:
        artifact_dir = wandb.use_artifact(f'{experiment.selection}:{selection_version}').download()
        selection = torch.load(os.path.join(artifact_dir, f'{experiment.selection}.pt'))

    # Label train dataset
    selector.load_voxel_selection(selection, train_ds)

    # Load model from W&B
    if load_model:
        if cfg.active.model is not None:
            model_file = cfg.active.model.split('/')[-1].split(':')[0]
            artifact_dir = wandb.use_artifact(cfg.active.model).download()
            model = torch.load(os.path.join(artifact_dir, f'{model_file}.pt'), map_location=device)
        else:
            artifact_dir = wandb.use_artifact(f'{experiment.model}:{model_version}').download()
            model = torch.load(os.path.join(artifact_dir, f'{experiment.model}.pt'), map_location=device)
    else:
        model = None

    # Log dataset statistics and calculate the weights for the loss function from them
    class_distribution = log_dataset_statistics(cfg=cfg, dataset=train_ds, artifact_name=experiment.dataset_stats)
    _ = log_dataset_statistics(cfg=cfg, dataset=val_ds, val=True)
    weights = 1 / (class_distribution + 1e-6)

    # Train model
    trainer = SemanticTrainer(cfg=cfg, train_ds=train_ds, val_ds=val_ds, device=device, weights=weights,
                              model=model, model_name=experiment.model, history_name=experiment.history)
    trainer.train()


def train_semantickitti_original(cfg: DictConfig, experiment: Experiment, device: torch.device) -> None:
    """ Trains a semantic segmentation model of the original SemanticKITTI dataset.

    :param cfg: The configuration object containing the dataset parameters.
    :param experiment: The experiment object containing the names of the artifacts to be used.
    :param device: The device to be used for the training.
    """

    train_ds = SemanticKITTIDataset(cfg.ds, 'train')
    val_ds = SemanticKITTIDataset(cfg.ds, 'val')

    weights = calculate_weights(cfg.ds.content, cfg.ds.learning_map)

    trainer = SemanticTrainer(cfg=cfg, train_ds=train_ds, val_ds=val_ds, device=device, weights=weights,
                              model=None, model_name=experiment.model, history_name=experiment.history)
    trainer.train()


def calculate_weights(content: dict, mapping: dict):
    train_labels = np.unique(np.array(list(mapping.values())))
    sums = np.zeros((len(train_labels)), dtype=np.float32)
    for key, value in content.items():
        sums[mapping[key]] += value
    weights = 1 / (sums + 1e-6)
    return weights
