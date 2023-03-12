import os
import logging

import torch
import wandb
from tqdm import tqdm
from omegaconf import DictConfig
from torch.utils.data import DataLoader, Dataset
import torch.optim as optim

from .loss import get_loss
from .logger import get_logger
from src.models import get_model
from src.datasets import get_parser
from src.active_selectors import get_selector

log = logging.getLogger(__name__)


class BaseTrainer(object):
    def __init__(self, cfg: DictConfig, train_ds: Dataset, val_ds: Dataset,
                 device: torch.device, model_name: str, output_dir: str):
        self.cfg = cfg
        self.device = device
        self.val_ds = val_ds
        self.train_ds = train_ds
        self.model_name = model_name
        self.output_dir = output_dir

        self.batch_size, self.num_workers = cfg.train.batch_size, self._get_num_workers(device)

        self.model = get_model(cfg, device)
        self.loss_fn = get_loss(cfg.model.type, device)
        self.parser = get_parser(cfg.model.type, device)
        self.logger = get_logger(cfg.model.type, cfg.ds.num_classes, cfg.ds.labels_train, device, cfg.ds.ignore_index)

        self.optimizer = optim.Adam(self.model.parameters(), lr=cfg.train.learning_rate)

    def train(self, epochs: int):
        raise NotImplementedError

    def train_epoch(self, epoch: int, validate: bool = True) -> dict:
        train_loader = DataLoader(self.train_ds, batch_size=self.batch_size,
                                  shuffle=True, num_workers=self.num_workers)
        self.model.train()
        for batch_idx, batch in enumerate(tqdm(train_loader, desc=f'Training epoch number {epoch}')):
            self.optimizer.zero_grad()

            inputs, targets = self.parser.parse_batch(batch)

            outputs = self.model(inputs)

            loss = self.loss_fn(outputs, targets)
            loss.backward()

            self.optimizer.step()

            with torch.no_grad():
                self.logger.update(loss.item(), outputs, targets)

        with torch.no_grad():
            self.logger.log_train(epoch)

        if validate:
            return self.validate(epoch)
        else:
            return {}

    def validate(self, epoch: int) -> dict:
        val_loader = DataLoader(self.val_ds, batch_size=self.batch_size,
                                shuffle=False, num_workers=self.num_workers)
        self.model.eval()
        with torch.no_grad():
            for batch_idx, batch in enumerate(tqdm(val_loader, desc=f'Validation epoch number {epoch}')):
                inputs, targets = self.parser.parse_batch(batch)
                outputs = self.model(inputs)
                loss = self.loss_fn(outputs, targets)

                self.logger.update(loss.item(), outputs, targets)
        return self.logger.log_val(epoch)

    @staticmethod
    def _get_num_workers(device: torch.device) -> int:
        if device.type == 'cuda':
            return torch.cuda.device_count() * 4
        else:
            return 4

    def save_state(self, epoch: int, results: dict):
        self.model.eval()
        state_dict = {'epoch': epoch,
                      'model_state_dict': self.model.state_dict(),
                      'optimizer_state_dict': self.optimizer.state_dict()}

        for key, value in results.items():
            state_dict[key] = value

        os.makedirs(self.output_dir, exist_ok=True)
        model_path = os.path.join(self.output_dir, f'{self.model_name}.pt')

        log.info(f'Saving model to {model_path}...')

        torch.save(state_dict, model_path)
        artifact = wandb.Artifact(self.model_name, type='model')
        artifact.add_file(model_path)
        wandb.run.log_artifact(artifact)


class Trainer(BaseTrainer):
    def __init__(self, cfg: DictConfig, train_ds: Dataset, val_ds: Dataset, device: torch.device,
                 model_name: str, output_dir: str, main_metric: str = 'iou'):
        super().__init__(cfg, train_ds, val_ds, device, model_name, output_dir)
        self.max_main_metric = 0
        self.main_metric = main_metric

    def train(self, epochs: int):
        for epoch in range(epochs):
            results = self.train_epoch(epoch, validate=True)

            if results[self.main_metric] > self.max_main_metric:
                self.max_main_metric = results[self.main_metric]
                self.save_state(epoch, results)


class ActiveTrainer(BaseTrainer):
    def __init__(self, cfg: DictConfig, train_ds: Dataset, val_ds: Dataset,
                 device: torch.device, model_name: str, output_dir: str, method: str):
        super().__init__(cfg, train_ds, val_ds, device, model_name, output_dir)
        self.max_iou = 0
        self.method = method

        cloud_ids, sequence_map = train_ds.get_dataset_structure()
        self.selector = get_selector(self.method, self.train_ds.path, cloud_ids, sequence_map, device)

    def train(self, epochs: int):
        while not self.selector.is_finished():
            self.selector.select(self.train_ds, self.model)
            self.train_ds.update()
            break
