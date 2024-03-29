import logging
from omegaconf import DictConfig

log = logging.getLogger(__name__)


class Experiment(object):
    def __init__(self, cfg: DictConfig):
        self.cfg = cfg
        log.info(self.__repr__())

    @property
    def project(self):
        if self.cfg.project is not None:
            return self.cfg.project
        if self.cfg.action == 'train_model':
            return 'Train-Semantic-Model'
        elif self.cfg.action == 'train_model_active':
            return f'AL-{self.cfg.ds.name}'
        elif self.cfg.action == 'select_voxels':
            return f'AL-{self.cfg.ds.name}'
        elif self.cfg.action == 'train_semantickitti_original':
            return 'Train-SemanticKITTI-Original'

    @property
    def group(self):
        if self.cfg.group is not None:
            return self.cfg.group
        if self.cfg.action == 'train_model':
            return self.cfg.ds.name
        elif self.cfg.action == 'train_model_active':
            return f'{self.cfg.active.strategy}-{self.cfg.active.cloud_partitions}'
        elif self.cfg.action == 'select_voxels':
            return f'{self.cfg.active.strategy}-{self.cfg.active.cloud_partitions}'
        elif self.cfg.action == 'train_semantickitti_original':
            return None

    @property
    def job_type(self):
        if self.cfg.job_type is not None:
            return self.cfg.job_type
        if self.cfg.action == 'train_model':
            return None
        elif self.cfg.action == 'train_model_active':
            return 'Training'
        elif self.cfg.action == 'select_voxels':
            return 'Selection'
        elif self.cfg.action == 'train_semantickitti_original':
            return None

    @property
    def name(self):
        if self.cfg.run_name is not None:
            return self.cfg.run_name
        if self.cfg.action == 'train_model':
            return f'{self.cfg.model.architecture}-{self.cfg.train.loss}'
        elif self.cfg.action == 'train_model_active':
            return f'{self.cfg.active.percentage}%'
        elif self.cfg.action == 'select_voxels':
            return f'{self.cfg.active.percentage}%'
        elif self.cfg.action == 'train_semantickitti_original':
            return f'{self.cfg.model.architecture}-{self.cfg.train.loss}'

    @property
    def info(self):
        if self.cfg.action == 'train_model':
            return f'{self.cfg.model.architecture}_{self.cfg.ds.name}_{self.cfg.train.loss}'
        elif self.cfg.action == 'train_model_active':
            return f'{self.cfg.active.strategy}_{self.cfg.active.cloud_partitions}' \
                   f'_{self.cfg.model.architecture}_{self.cfg.ds.name}'
        elif self.cfg.action == 'select_voxels':
            return f'{self.cfg.active.strategy}_{self.cfg.active.cloud_partitions}' \
                   f'_{self.cfg.model.architecture}_{self.cfg.ds.name}'
        elif self.cfg.action == 'train_semantickitti_original':
            return f'{self.cfg.model.architecture}_{self.cfg.train.loss}_SemanticKITTI_Original'

    @property
    def model(self):
        return f'Model_{self.info}'

    @property
    def selection(self):
        return f'Selection_{self.info}'

    @property
    def history(self):
        return f'History_{self.info}'

    @property
    def metric_stats(self):
        return f'MetricStats_{self.info}'

    @property
    def weighted_metric_stats(self):
        return f'WeightedMetricStats_{self.info}'

    @property
    def dataset_stats(self):
        return f'DatasetStats_{self.info}'

    def __str__(self):
        return f'\n\nExperiment: \n' \
               f'\t - Project: {self.project}\n' \
               f'\t - Group: {self.group}\n' \
               f'\t - Job Type: {self.job_type}\n' \
               f'\t - Name: {self.name}\n' \
               f'\t - Info: {self.info}\n' \
               f'\t - Model: {self.model}\n' \
               f'\t - History: {self.history}\n' \
               f'\t - Selection: {self.selection}\n' \
               f'\t - Metric Stats: {self.metric_stats}\n' \
               f'\t - Dataset Stats: {self.dataset_stats}\n'

    def __repr__(self):
        return self.__str__()
