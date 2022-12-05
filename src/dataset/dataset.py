import os
import logging

import numpy as np

from torch.utils.data import Dataset
from omegaconf import DictConfig
from src.laserscan import SemLaserScan
from .utils import dict_to_label_map, open_sequence, apply_augmentations

log = logging.getLogger(__name__)


class SemanticDataset(Dataset):
    def __init__(self, dataset_path: str, cfg: DictConfig, sequences: list = None,
                 split: str = None, size: int = None, indices: list = None):

        self.cfg = cfg
        self.size = size
        self.split = split
        self.indices = indices
        self.path = dataset_path

        if sequences is None:
            sequences = cfg.split[split]
        self.sequences = sequences

        self.points = []
        self.labels = []

        self.label_map = dict_to_label_map(cfg.learning_map)
        self.scan = SemLaserScan()

        self.init()

    def __getitem__(self, index):
        points_path = self.points[index]
        label_path = self.labels[index]

        self.scan.open_scan(points_path)
        self.scan.open_label(label_path)

        image = self.scan.proj_depth[np.newaxis, ...]
        label = self.label_map[self.scan.proj_sem_label].astype(np.long)

        if self.split == 'train':
            image, label = apply_augmentations(image, label)

        return image, label, index

    def __len__(self):
        return len(self.points)

    def init(self):
        log.info(f"Initializing dataset from path {self.path}")

        # ----------- LOAD -----------

        path = os.path.join(self.path, 'sequences')
        for seq in self.sequences:
            seq_path = os.path.join(path, f"{seq:02d}")
            points, labels = open_sequence(seq_path)
            self.points += points
            self.labels += labels

        log.info(f"Found {len(self.points)} samples")
        assert len(self.points) == len(self.labels), "Number of points and labels must be equal"

        # ----------- CROP -----------

        self.points = self.points[:self.size]
        self.labels = self.labels[:self.size]

        log.info(f"Cropped dataset to {len(self.points)} samples")

        # ----------- USE INDICES -----------

        if self.indices is not None:
            self.choose_data()
            log.info(f"Using samples {self.indices} for {self.split} split")

        log.info(f"Dataset initialized with {len(self.points)} samples")

    def choose_data(self, indices=None):
        if indices:
            self.indices = indices
        assert self.indices is not None

        self.indices.sort()

        assert max(self.indices) < len(self.points), "Index out of range"

        self.points = [self.points[i] for i in self.indices]
        self.labels = [self.labels[i] for i in self.indices]


def inspect_semantic_kitti360():
    import open3d as o3d
    from kitti360scripts.helpers.labels import id2label
    import matplotlib.pyplot as plt

    # id       color
    color_map = {
        0: (0, 0, 0),
        1: (0, 0, 0),
        2: (0, 0, 0),
        3: (0, 0, 0),
        4: (0, 0, 0),
        5: (111, 74, 0),
        6: (81, 0, 81),
        7: (128, 64, 128),
        8: (244, 35, 232),
        9: (250, 170, 160),
        10: (230, 150, 140),
        11: (70, 70, 70),
        12: (102, 102, 156),
        13: (190, 153, 153),
        14: (180, 165, 180),
        15: (150, 100, 100),
        16: (150, 120, 90),
        17: (153, 153, 153),
        18: (153, 153, 153),
        19: (250, 170, 30),
        20: (220, 220, 0),
        21: (107, 142, 35),
        22: (152, 251, 152),
        23: (70, 130, 180),
        24: (220, 20, 60),
        25: (255, 0, 0),
        26: (0, 0, 142),
        27: (0, 0, 70),
        28: (0, 60, 100),
        29: (0, 0, 90),
        30: (0, 0, 110),
        31: (0, 80, 100),
        32: (0, 0, 230),
        33: (119, 11, 32),
        34: (64, 128, 128),
        35: (190, 153, 153),
        36: (150, 120, 90),
        37: (153, 153, 153),
        38: (0, 64, 64),
        39: (0, 128, 192),
        40: (128, 64, 0),
        41: (64, 64, 128),
        42: (102, 0, 0),
        43: (51, 0, 51),
        44: (32, 32, 32),
        -1: (0, 0, 142),
    }

    data_dir = os.environ['KITTI360_DATASET']
    # data_dir = "/home/ruslan/data/datasets/KITTI/KITTI-360/"
    scan = SemLaserScan(colorize=True, sem_color_dict=color_map, H=64, W=1024, fov_up=13.4, fov_down=-13.4)

    for seq in ['2013_05_28_drive_0000_sync']:
        pts_folder = os.path.join(data_dir, 'SemanticKITTI-360', seq, 'velodyne')

        for pts_file in os.listdir(pts_folder):
            pts_file = os.path.join(pts_folder, pts_file)
            ids_file = pts_file.replace('velodyne', 'labels').replace('.bin', '.label')

            points = np.load(pts_file)
            ids = np.load(ids_file)

            scan.set_points(points)
            scan.set_label(ids)

            plt.figure(figsize=(20, 10))
            plt.subplot(2, 1, 1)
            plt.imshow(scan.proj_depth)
            plt.title('Depth image')

            plt.subplot(2, 1, 2)
            plt.imshow(scan.proj_sem_color)
            plt.title('Semantic classes')
            plt.show()

            color = np.zeros((ids.size, 3))
            for uid in np.unique(ids):
                color[ids == uid] = id2label[uid].color

            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points)
            pcd.colors = o3d.utility.Vector3dVector(color / color.max())

            o3d.visualization.draw_geometries([pcd])


if __name__ == "__main__":
    inspect_semantic_kitti360()
