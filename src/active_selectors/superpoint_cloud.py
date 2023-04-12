import torch
from .base_cloud import Cloud


class SuperpointCloud(Cloud):
    def __init__(self, path: str, size: int, cloud_id: int, superpoint_map: torch.Tensor):
        super().__init__(path, size, cloud_id)
        self.superpoint_map = superpoint_map

    @property
    def num_superpoints(self) -> int:
        return self.superpoint_map.max().item() + 1

    def average_by_superpoint(self, values: torch.Tensor):
        superpoint_sizes = torch.zeros((self.num_superpoints,), dtype=torch.long)
        average_superpoint_values = torch.full((self.num_superpoints,), float('nan'), dtype=torch.float32)

        superpoints, sizes = torch.unique(self.superpoint_map, return_counts=True)
        superpoint_sizes[superpoints] = sizes

        # Average the values by superpoint
        for superpoint in torch.unique(self.superpoint_map):
            indices = torch.where(self.superpoint_map == superpoint)
            superpoint_values = values[indices]
            valid_superpoint_values = superpoint_values[~torch.isnan(superpoint_values)]
            if len(valid_superpoint_values) > 0:
                average_superpoint_values[superpoint] = torch.mean(valid_superpoint_values)
        return average_superpoint_values, superpoint_sizes

    def return_values(self, values: torch.Tensor):
        superpoint_values, superpoint_sizes = self.average_by_superpoint(values)
        valid_indices = ~torch.isnan(superpoint_values)

        filtered_values = superpoint_values[valid_indices]
        filtered_superpoint_sizes = superpoint_sizes[valid_indices]
        filtered_superpoint_map = self.superpoint_map[valid_indices]
        filtered_cloud_ids = torch.full((self.num_superpoints,), self.id, dtype=torch.long)[valid_indices]

        return filtered_values, filtered_superpoint_map, filtered_superpoint_sizes, filtered_cloud_ids

    def __str__(self):
        ret = f'\nSuperpointCloud:\n' \
              f'\t - Cloud ID = {self.id}, \n' \
              f'\t - Cloud path = {self.path}, \n' \
              f'\t - Number of voxels in cloud = {self.size}\n' \
              f'\t - Number of superpoints in cloud = {self.num_superpoints}\n' \
              f'\t - Number of model predictions = {self.predictions.shape[0]}\n'
        if self.num_classes > 0:
            ret += f'\t - Number of semantic classes = {self.num_classes}\n'
        ret += f'\t - Percentage labeled = {torch.sum(self.label_mask) / self.size * 100:.2f}%\n'
        return ret
