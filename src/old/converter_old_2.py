import os
import logging

import h5py
import torch
import numpy as np
import open3d as o3d
from tqdm import tqdm
import matplotlib.pyplot as plt
from omegaconf import DictConfig
from mpl_toolkits.axes_grid1 import ImageGrid
from sklearn.linear_model import RANSACRegressor

from src.ply_c import libply_c
from kitti360.ply import read_kitti360_ply
from src.utils import project_points, visualize_cloud_values
from src.utils import map_labels, map_colors
from src.losses.crosspartition import compute_partition, compute_dist
from src.models.pointnet_sp import LocalCloudEmbedder
from src.utils import transform_points, downsample_cloud, nearest_neighbors, \
    nearest_neighbors_2, connected_label_components, nn_graph
from kitti360.kitti360 import get_disjoint_ranges, read_kitti360_poses, read_kitti360_scan, get_window_range, \
    create_model, read_txt

log = logging.getLogger(__name__)


class KITTI360Converter:
    def __init__(self, cfg: DictConfig):

        # ----------------- KITTI-360 structure attributes -----------------
        self.cfg = cfg
        self.sequence = cfg.sequence if 'sequence' in cfg else 3
        self.seq_name = f'2013_05_28_drive_{self.sequence:04d}_sync'

        self.velodyne_path = os.path.join(cfg.ds.path, 'data_3d_raw', self.seq_name, 'velodyne_points', 'data')
        self.semantics_path = os.path.join(cfg.ds.path, 'data_3d_semantics')

        self.train_windows_path = os.path.join(self.semantics_path, 'train', '2013_05_28_drive_train.txt')
        self.val_windows_path = os.path.join(self.semantics_path, 'train', '2013_05_28_drive_val.txt')

        # Transformations from camera to world frame file
        self.poses_path = os.path.join(cfg.ds.path, 'data_poses', self.seq_name, 'cam0_to_world.txt')

        # Transformation from velodyne to camera frame file
        self.calib_path = os.path.join(cfg.ds.path, 'calibration', 'calib_cam_to_velo.txt')

        static_windows_dir = os.path.join(self.semantics_path, 'train', self.seq_name, 'static')
        dynamic_windows_dir = os.path.join(self.semantics_path, 'train', self.seq_name, 'dynamic')
        self.static_windows = sorted([os.path.join(static_windows_dir, f) for f in os.listdir(static_windows_dir)])
        self.dynamic_windows = sorted([os.path.join(dynamic_windows_dir, f) for f in os.listdir(dynamic_windows_dir)])

        # Create a disjoint set of ranges for the windows
        self.window_ranges = get_disjoint_ranges(self.static_windows)

        # Get the train and validation splits with the corresponding new cloud names (without overlap)
        splits = self.get_splits(self.window_ranges, self.train_windows_path, self.val_windows_path)
        self.train_samples, self.val_samples, self.train_clouds, self.val_clouds = splits

        # ----------------- Conversion attributes -----------------
        self.static_threshold = cfg.conversion.static_threshold
        self.dynamic_threshold = cfg.conversion.dynamic_threshold

        # Sequence info
        self.num_scans = len(os.listdir(self.velodyne_path))
        self.num_windows = len(self.static_windows)

        self.semantic = None
        # self.instances = None

        # ----------------- Transformations -----------------

        self.T_cam_to_velo = np.concatenate([np.loadtxt(self.calib_path).reshape(3, 4), [[0, 0, 0, 1]]], axis=0)
        self.T_velo_to_cam = np.linalg.inv(self.T_cam_to_velo)
        self.poses = read_kitti360_poses(self.poses_path, self.T_velo_to_cam)

        # ----------------- Visualization attributes -----------------

        # Point clouds for visualization
        self.scan = o3d.geometry.PointCloud()
        self.static_window = o3d.geometry.PointCloud()
        self.dynamic_window = o3d.geometry.PointCloud()

        self.semantic_color = None

        # Visualization parameters
        self.scan_num = 0
        self.window_num = 0

        self.visualization_step = cfg.conversion.visualization_step

        # Color map for instance labels
        # self.cmap = cm.get_cmap('Set1')
        # self.cmap_length = 9

        self.key_callbacks = {
            ord(']'): self.prev_window,
            ord(']'): self.next_window,
            ord('N'): self.next_scan,
            ord('B'): self.prev_scan,
            ord('Q'): self.quit,
        }

        self.k_nn_adj = 5
        self.k_nn_local = 20

    def convert(self):
        """Convert KITTI-360 dataset to SemanticKITTI format. That is done by following these steps:

        1. Create a new directory structure for the sequence
        2. Load the static windows, dynamic windows and the voxel clouds
        3. For each scan:
            - Load the velodyne scan
            - Transform the scan to the world frame
            - Find the nearest points in the dynamic window and remove them from the scan
            - Find the nearest points in the static window and assign them corresponding RGB colors
            - Find the nearest points in the voxel clouds and assign them corresponding labels and voxel ID
            - Save the scan and the labels in the new directory structure
        4. Save the sequence info (train and val samples)

        The sequence directory will contain the following files:
            - velodyne: Velodyne scans
            - labels: Labels for each scan
            - info.npz: Sequence info (train and val samples)
            - voxel_clouds: Voxel clouds for each window in the KITTI-360 dataset (this has to be created beforehand)
        """

        # Create output directories
        sequence_path = os.path.join(self.cfg.ds.path, 'sequences', f'{self.sequence:02d}')

        # Labels directory
        labels_dir = os.path.join(sequence_path, 'labels')
        os.makedirs(labels_dir, exist_ok=True)

        # Velodyne directory
        velodyne_dir = os.path.join(sequence_path, 'velodyne')
        os.makedirs(velodyne_dir, exist_ok=True)

        # Clouds directory
        voxel_clouds_dir = os.path.join(sequence_path, 'voxel_clouds')
        assert os.path.exists(voxel_clouds_dir), f'Global clouds directory {voxel_clouds_dir} does not exist'

        voxel_clouds = sorted([os.path.join(voxel_clouds_dir, f) for f in os.listdir(voxel_clouds_dir)])

        val_samples, train_samples = self.val_samples.astype('S'), self.train_samples.astype('S')
        val_clouds, train_clouds = self.val_clouds.astype('S'), self.train_clouds.astype('S')

        # Write the sequence info to a file
        with h5py.File(os.path.join(sequence_path, 'info.h5'), 'w') as f:
            f.create_dataset('val', data=val_samples)
            f.create_dataset('train', data=train_samples)
            f.create_dataset('val_clouds', data=val_clouds)
            f.create_dataset('train_clouds', data=train_clouds)
            f.create_dataset('selection_mask', data=np.ones(len(train_samples), dtype=np.bool))

        for i, files in enumerate(zip(self.static_windows, self.dynamic_windows, voxel_clouds)):
            log.info(f'Converting window {i + 1}/{self.num_windows}')

            # Load the static and dynamic windows
            static_file, dynamic_file, voxel_cloud_file = files
            static_points, static_colors, _, _ = read_kitti360_ply(static_file)
            dynamic_points, _, _, _ = read_kitti360_ply(dynamic_file)

            # Load the voxel cloud
            with h5py.File(voxel_cloud_file, 'r') as f:
                voxel_points = np.asarray(f['points'])
                voxel_labels = np.asarray(f['labels'])
            voxel_mask = np.zeros(len(voxel_points), dtype=np.bool)

            # For each scan in the window, find the points that belong to it and write them to a files
            log.info(f'Window range: {self.window_ranges[i]}')
            start, end = self.window_ranges[i]
            for j in tqdm(range(start, end + 1), desc=f'Creating samples {start} - {end}'):
                scan = read_kitti360_scan(self.velodyne_path, j)
                scan_points = scan[:, :3]
                scan_remissions = scan[:, 3]

                # Transform scan to the current pose
                transformed_scan_points = transform_points(scan_points, self.poses[j])

                # Find neighbors in the dynamic window and remove dynamic points
                if len(dynamic_points) > 0:
                    dists, indices = nearest_neighbors_2(dynamic_points, transformed_scan_points, k_nn=1)
                    mask = np.logical_and(dists >= 0, dists <= self.dynamic_threshold)
                    transformed_scan_points = transformed_scan_points[~mask]
                    scan_remissions = scan_remissions[~mask]
                    scan_points = scan_points[~mask]

                # Find neighbours in the static window and assign their color
                dists, indices = nearest_neighbors_2(static_points, transformed_scan_points, k_nn=1)
                mask = np.logical_and(dists >= 0, dists <= self.static_threshold)
                colors = static_colors[indices[mask]].astype(np.float32)
                transformed_scan_points = transformed_scan_points[mask]
                scan_remissions = scan_remissions[mask]
                scan_points = scan_points[mask]

                # Find neighbours in the voxel cloud and assign their label and index
                dists, voxel_indices = nearest_neighbors_2(voxel_points, transformed_scan_points, k_nn=1)
                labels = voxel_labels[voxel_indices].astype(np.uint8)
                voxel_mask[voxel_indices] = True

                # Write the scan to a file
                with h5py.File(os.path.join(velodyne_dir, f'{j:06d}.h5'), 'w') as f:
                    f.create_dataset('colors', data=colors, dtype=np.float32)
                    f.create_dataset('points', data=scan_points, dtype=np.float32)
                    f.create_dataset('remissions', data=scan_remissions, dtype=np.float32)
                    f.create_dataset('pose', data=self.poses[j], dtype=np.float32)

                # Write the labels to a file
                with h5py.File(os.path.join(labels_dir, f'{j:06d}.h5'), 'w') as f:
                    f.create_dataset('labels', data=labels, dtype=np.uint8)
                    f.create_dataset('voxel_map', data=voxel_indices.astype(np.uint32), dtype=np.uint32)
                    f.create_dataset('label_mask', data=np.zeros_like(labels, dtype=np.bool), dtype=np.bool)

            # with h5py.File(voxel_cloud_file, 'r+') as f:
            #     f.create_dataset('voxel_mask', data=voxel_mask, dtype=np.bool)

    def create_global_clouds(self):
        sequence_path = os.path.join(self.cfg.ds.path, 'sequences', f'{self.sequence:02d}')
        global_cloud_dir = os.path.join(sequence_path, 'voxel_clouds')
        os.makedirs(global_cloud_dir, exist_ok=True)

        clouds = np.sort(np.concatenate([self.train_clouds, self.val_clouds]))
        for window, name in tqdm(zip(self.static_windows, clouds), total=len(clouds), desc='Creating global clouds'):
            output_file = h5py.File(os.path.join(global_cloud_dir, name), 'w')

            # Read static window and downsample
            points, colors, labels, _ = read_kitti360_ply(window)
            points, colors, labels = downsample_cloud(points, colors, labels, 0.2)

            # Compute graph edges
            edge_sources, edge_targets, distances = nn_graph(points, self.k_nn_adj)

            # Compute local neighbors
            local_neighbors, _ = nearest_neighbors(points, self.k_nn_local)

            # Computes object in point cloud and transition edges
            objects = connected_label_components(labels, edge_sources, edge_targets)
            edge_transitions = objects[edge_sources] != objects[edge_targets]

            # Create label mask
            label_mask = np.zeros(len(points), dtype=np.bool)

            output_file.create_dataset('points', data=points, dtype='float32')
            output_file.create_dataset('colors', data=colors, dtype='float32')
            output_file.create_dataset('labels', data=labels.flatten(), dtype='uint8')
            output_file.create_dataset('objects', data=objects, dtype='uint32')
            output_file.create_dataset('label_mask', data=label_mask, dtype='bool')

            output_file.create_dataset('edge_sources', data=edge_sources, dtype='uint32')
            output_file.create_dataset('edge_targets', data=edge_targets, dtype='uint32')
            output_file.create_dataset('edge_transitions', data=edge_transitions, dtype='uint8')
            output_file.create_dataset('local_neighbors', data=local_neighbors, dtype='uint32')

    def create_superpoints(self, device: torch.device):
        subgraph = False

        sequence_path = os.path.join(self.cfg.ds.path, 'sequences', f'{self.sequence:02d}')
        global_cloud_dir = os.path.join(sequence_path, 'voxel_clouds')
        model_path = os.path.join(self.cfg.path.models, 'pretrained', 'cv3', 'model.pth.tar')
        checkpoint = torch.load(model_path)

        # dataset = KITTI360Dataset(self.cfg, self.cfg.ds.path, 'val')
        # print(dataset[0])

        model = create_model(checkpoint['args'])
        model.load_state_dict(checkpoint['state_dict'])
        ptn_cloud_embedder = LocalCloudEmbedder(checkpoint['args'])

        model.eval()
        model.to(device)

        cloud_names = np.sort(np.concatenate([self.train_clouds, self.val_clouds]))
        for cloud_name in tqdm(cloud_names, desc='Creating superpoints'):

            # Load the voxel cloud
            with h5py.File(os.path.join(global_cloud_dir, cloud_name), 'r') as cloud:
                points = np.asarray(cloud['points'])
                objects = np.asarray(cloud['objects'])

                edge_sources = np.asarray(cloud['edge_sources'])
                edge_targets = np.asarray(cloud['edge_targets'])
                local_neighbors = np.asarray(cloud['local_neighbors']).reshape((points.shape[0], self.k_nn_local))

            selected_ver = np.ones((points.shape[0],), dtype=bool)
            is_transition = objects[edge_sources] != objects[edge_targets]

            # If the subgraph is enabled select a random subgraph
            if subgraph:
                # Randomly select a subgraph
                selected_edg, selected_ver = libply_c.random_subgraph(points.shape[0], edge_sources.astype('uint32'),
                                                                      edge_targets.astype('uint32'),
                                                                      30000)
                # Change the type to bool
                selected_edg = selected_edg.astype(bool)
                selected_ver = selected_ver.astype(bool)

                new_ver_index = -np.ones((points.shape[0],), dtype=int)
                new_ver_index[selected_ver.nonzero()] = range(selected_ver.sum())

                edge_sources = new_ver_index[edge_sources[selected_edg]]
                edge_targets = new_ver_index[edge_targets[selected_edg]]

                is_transition = is_transition[selected_edg]
                local_neighbors = local_neighbors[selected_ver,]

            # Compute elevation
            low_points = (points[:, 2] - points[:, 2].min() < 5).nonzero()[0]
            if low_points.shape[0] > 100:
                reg = RANSACRegressor(random_state=0).fit(points[low_points, :2], points[low_points, 2])
                elevation = points[:, 2] - reg.predict(points[:, :2])
            else:
                elevation = np.zeros((points.shape[0],), dtype=np.float32)

            # Compute the xyn (normalized x and y)
            ma, mi = np.max(points[:, :2], axis=0, keepdims=True), np.min(points[:, :2], axis=0, keepdims=True)
            xyn = (points[:, :2] - mi) / (ma - mi)
            xyn = xyn[selected_ver,]

            # Compute the local geometry
            clouds = points[local_neighbors,]
            diameters = np.sqrt(clouds.var(1).sum(1))
            clouds = (clouds - points[selected_ver, np.newaxis, :]) / (diameters[:, np.newaxis, np.newaxis] + 1e-10)
            clouds = np.concatenate([clouds, points[local_neighbors,]], axis=2)
            clouds = clouds.transpose([0, 2, 1])

            # Compute the global geometry
            clouds_global = np.hstack(
                [diameters[:, np.newaxis], elevation[selected_ver, np.newaxis], points[selected_ver,], xyn])

            # Convert to torch
            clouds = torch.from_numpy(clouds).float().to(device)
            clouds_global = torch.from_numpy(clouds_global).float().to(device)

            # Compute embeddings
            with torch.no_grad():
                embeddings = ptn_cloud_embedder.run_batch(model, clouds, clouds_global)
                diff = compute_dist(embeddings, edge_sources.astype(np.int64), edge_targets.astype(np.int64),
                                    'euclidian')
                pred_comp, in_comp = compute_partition(embeddings, edge_sources, edge_targets, diff,
                                                       points[selected_ver,])

            # with h5py.File(os.path.join(global_cloud_dir, cloud_name), 'r+') as superpoint:
            #     superpoint.create_dataset('superpoints', data=in_comp)

            visualize_cloud_values(points[selected_ver,], in_comp, random_colors=True)

    def get_splits(self, window_ranges: list[tuple[int, int]], train_file: str, val_file: str) -> tuple:
        """ Get the train and validation splits for the dataset. Also returns the cloud names.

        :param window_ranges: List of tuples containing the start and end scan of each window.
        :param train_file: Path to the train split file.
        :param val_file: Path to the validation split file.
        :return: Tuple containing the train and validation splits and the cloud names.
        """

        val_clouds = np.array([], dtype=np.str_)
        val_samples = np.array([], dtype=np.str_)
        train_clouds = np.array([], dtype=np.str_)
        train_samples = np.array([], dtype=np.str_)

        val_ranges = [get_window_range(path) for path in read_txt(val_file, self.seq_name)]
        train_ranges = [get_window_range(path) for path in read_txt(train_file, self.seq_name)]

        for i, window in enumerate(window_ranges):
            cloud_name = f'{window[0]:06d}_{window[1]:06d}.h5'
            window_samples = np.array([f'{j:06d}.h5' for j in np.arange(window[0], window[1] + 1)], dtype='S')
            for train_range in train_ranges:
                if train_range[0] == window[0]:
                    train_samples = np.concatenate((train_samples, window_samples))
                    train_clouds = np.append(train_clouds, cloud_name)
            for val_range in val_ranges:
                if val_range[0] == window[0]:
                    val_samples = np.concatenate((val_samples, window_samples))
                    val_clouds = np.append(val_clouds, cloud_name)

        return train_samples, val_samples, train_clouds, val_clouds

    def update_window(self):
        static_points, static_colors, self.semantic, _ = read_kitti360_ply(self.static_windows[self.window_num])

        self.semantic = map_labels(self.semantic, self.cfg.ds.learning_map).flatten()
        self.semantic_color = map_colors(self.semantic, self.cfg.ds.color_map_train)

        dynamic_points, _, _, _ = read_kitti360_ply(self.dynamic_windows[self.window_num])
        dynamic_colors = np.ones_like(dynamic_points) * [0, 0, 1]

        self.static_window.points = o3d.utility.Vector3dVector(static_points)
        self.static_window.colors = o3d.utility.Vector3dVector(static_colors)

        self.dynamic_window.points = o3d.utility.Vector3dVector(dynamic_points)
        self.dynamic_window.colors = o3d.utility.Vector3dVector(dynamic_colors)

        self.scan_num = self.window_ranges[self.window_num][0]
        self.update_scan()

    def update_scan(self):

        # Read scan
        scan = read_kitti360_scan(self.velodyne_path, self.scan_num)
        scan_points = scan[:, :3]

        # Transform scan to world coordinates
        transformed_scan_points = transform_points(scan_points, self.poses[self.scan_num])

        # Find neighbours in the static window
        dists, indices = nearest_neighbors_2(self.static_window.points, transformed_scan_points, k_nn=1)
        mask = np.logical_and(dists >= 0, dists <= self.static_threshold)

        # Extract RGB values from the static window
        rgb = np.array(self.static_window.colors)[indices[mask]]

        # Color of the scan in world coordinates
        scan_colors = np.ones_like(scan_points) * [1, 0, 0]
        scan_colors[mask] = [0, 1, 0]

        # Get point cloud labels
        semantics = np.array(self.semantic_color)[indices[mask]]

        # Project the scan to the camera
        projection = project_points(scan_points, 64, 1024, 3, -25.0)
        proj_mask = projection['mask']

        # Project the filtered scan to the camera
        filtered_projection = project_points(scan_points[mask], 64, 1024, 3, -25.0)
        filtered_proj_mask = filtered_projection['mask']
        filtered_proj_indices = filtered_projection['idx'][filtered_proj_mask]

        # Project color, semantic and instance labels to the camera
        proj_color = np.zeros((64, 1024, 3), dtype=np.float32)
        proj_semantics = np.zeros((64, 1024, 3), dtype=np.float32)
        proj_instances = np.zeros((64, 1024, 3), dtype=np.float32)

        proj_color[filtered_proj_mask] = rgb[filtered_proj_indices]
        proj_semantics[filtered_proj_mask] = semantics[filtered_proj_indices]

        # Visualize the projection
        fig = plt.figure(figsize=(11, 4), dpi=150)
        grid = ImageGrid(fig, 111, nrows_ncols=(5, 1), axes_pad=0.4)

        images = [proj_mask, filtered_proj_mask, proj_color, proj_semantics, proj_instances]
        titles = ['Projection Mask', 'Filtered Projection Mask', 'RGB Color', 'Semantic Labels', 'Instance Labels']

        for ax, image, title in zip(grid, images, titles):
            ax.set_title(title)
            ax.imshow(image, aspect='auto')
            ax.axis('off')

        plt.show()

        self.scan.points = o3d.utility.Vector3dVector(transformed_scan_points)
        self.scan.colors = o3d.utility.Vector3dVector(scan_colors)

    def next_window(self, vis):
        self.window_num += 1
        self.update_window()
        vis.update_geometry(self.static_window)
        vis.update_geometry(self.dynamic_window)
        vis.update_geometry(self.scan)
        vis.reset_view_point(True)
        vis.update_renderer()
        return False

    def prev_window(self, vis):
        self.window_num -= self.visualization_step
        self.update_window()
        vis.update_geometry(self.static_window)
        vis.update_geometry(self.dynamic_window)
        vis.update_geometry(self.scan)
        vis.reset_view_point(True)
        vis.update_renderer()
        return False

    def next_scan(self, vis):
        self.scan_num += self.visualization_step
        self.update_scan()
        vis.update_geometry(self.scan)
        vis.update_renderer()
        return False

    def prev_scan(self, vis):
        self.scan_num -= self.visualization_step
        self.update_scan()
        vis.update_geometry(self.scan)
        vis.update_renderer()
        return False

    @staticmethod
    def quit(vis):
        vis.destroy_window()
        return True

    def visualize(self):
        log.info('Visualizing the KITTI-360 conversion')
        print('\nControls:')
        print('  - Press "b" to go to the next scan')
        print('  - Press "p" to go to the previous scan')
        print('  - Press "]" to go to the next window')
        print('  - Press "[" to go to the previous window')
        self.update_window()
        self.update_scan()
        o3d.visualization.draw_geometries_with_key_callbacks(
            [self.static_window, self.scan],
            self.key_callbacks)
