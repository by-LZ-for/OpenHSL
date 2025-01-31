from openhsl.hsi import HSImage
from openhsl.hs_mask import HSMask

import copy
from openhsl.data.utils import apply_pca

from openhsl.models.model import Model

import numpy as np
from typing import Any, Optional, Dict

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from torch.nn import init


class ParallelConvBlock(nn.Module):
    def __init__(self, inp, out):
        super().__init__()
        self.conv1 = nn.Conv3d(inp, 16, (1, 1, 1), padding=(0, 0, 0))
        self.bn_conv1 = nn.BatchNorm3d(16)
        self.conv2 = nn.Conv3d(16, 16, (3, 1, 1), padding=(1, 0, 0))
        self.bn_conv2 = nn.BatchNorm3d(16)
        self.conv3 = nn.Conv3d(16, 16, (5, 1, 1), padding=(2, 0, 0))
        self.bn_conv3 = nn.BatchNorm3d(16)
        self.conv4 = nn.Conv3d(16, out, (11, 1, 1), padding=(5, 0, 0))
        self.bn_conv4 = nn.BatchNorm3d(out)

    def forward(self, x, **kwargs):

        x1 = self.conv1(x)
        x2 = self.conv2(x)
        x3 = self.conv3(x)
        x4 = self.conv4(x)

        return x1 + x2 + x3 + x4


class NM3DCNN_Net(nn.Module):
    """
    MULTI-SCALE 3D DEEP CONVOLUTIONAL NEURAL NETWORK FOR HYPERSPECTRAL
    IMAGE CLASSIFICATION
    Mingyi He, Bo Li, Huahui Chen
    IEEE International Conference on Image Processing (ICIP) 2017
    https://ieeexplore.ieee.org/document/8297014/

    modified by N.A. Firsov, A.V. Nikonorov
    DOI: 10.18287/2412-6179-CO-1038
    """

    @staticmethod
    def weight_init(m):
        if isinstance(m, nn.Linear) or isinstance(m, nn.Conv3d):
            init.kaiming_uniform_(m.weight)
            init.zeros_(m.bias)
    # ------------------------------------------------------------------------------------------------------------------

    def __init__(self, input_channels, n_classes, patch_size=7):
        super(NM3DCNN_Net, self).__init__()
        self.input_channels = input_channels
        self.patch_size = patch_size

        self.conv1 = nn.Conv3d(1, 16, (11, 3, 3), stride=(3, 1, 1))
        self.bn_conv1 = nn.BatchNorm3d(16)

        self.pcb_1 = ParallelConvBlock(inp=16, out=16)
        self.bn_pcb_1 = nn.BatchNorm3d(16)

        self.pcb_2 = ParallelConvBlock(inp=16, out=16)
        self.bn_pcb_2 = nn.BatchNorm3d(16)

        self.conv4 = nn.Conv3d(16, 16, (3, 2, 2))
        self.bn_conv4 = nn.BatchNorm3d(16)

        self.features_size = self._get_final_flattened_size()
        print(self.features_size)

        self.fc = nn.Linear(self.features_size, n_classes)

        self.apply(self.weight_init)
    # ------------------------------------------------------------------------------------------------------------------

    def _get_final_flattened_size(self):
        with torch.no_grad():
            x = torch.zeros(
                (1, 1, self.input_channels, self.patch_size, self.patch_size)
            )
            x = self.conv1(x)
            x = self.bn_conv1(x)

            x = self.pcb_1(x)
            x = self.bn_pcb_1(x)

            x = self.pcb_2(x)
            x = self.bn_pcb_2(x)

            x = self.conv4(x)
            x = self.bn_conv4(x)

            _, t, c, w, h = x.size()
        return t * c * w * h
    # ------------------------------------------------------------------------------------------------------------------

    def forward(self, x):

        x = self.conv1(x)
        x = self.bn_conv1(x)
        x = F.relu(x)
        x = self.pcb_1(x)
        x = F.relu(x)
        x = self.pcb_2(x)
        x = F.relu(x)

        x = self.conv4(x)
        x = self.bn_conv4(x)
        x = F.relu(x)

        x = x.view(-1, self.features_size)
        x = self.fc(x)
        return x
# ----------------------------------------------------------------------------------------------------------------------


class NM3DCNN(Model):
    def __init__(self,
                 n_classes,
                 device,
                 n_bands,
                 apply_pca=False,
                 path_to_weights=None
                 ):
        super(NM3DCNN, self).__init__()
        self.apply_pca = apply_pca
        self.hyperparams: dict[str: Any] = dict()
        self.hyperparams['patch_size'] = 7
        self.hyperparams['n_bands'] = n_bands
        self.hyperparams['net_name'] = 'nm3dcnn'
        self.hyperparams['n_classes'] = n_classes
        self.hyperparams['ignored_labels'] = [0]
        self.hyperparams['device'] = device

        weights = torch.ones(n_classes)
        weights[torch.LongTensor(self.hyperparams["ignored_labels"])] = 0.0
        weights = weights.to(device)
        self.hyperparams["weights"] = weights

        self.model = NM3DCNN_Net(n_bands, n_classes, patch_size=self.hyperparams["patch_size"])
        # For Adagrad, we need to load the model on GPU before creating the optimizer
        self.model = self.model.to(device)

        self.hyperparams.setdefault("supervision", "full")
        self.hyperparams.setdefault("flip_augmentation", False)
        self.hyperparams.setdefault("radiation_augmentation", False)
        self.hyperparams.setdefault("mixture_augmentation", False)
        self.hyperparams["center_pixel"] = True

        if path_to_weights:
            self.model.load_state_dict(torch.load(path_to_weights))
    # ------------------------------------------------------------------------------------------------------------------

    def fit(self,
            X: HSImage,
            y: HSMask,
            fit_params: Dict):

        if self.apply_pca:
            X = copy.deepcopy(X)
            X.data, _ = apply_pca(X.data, self.hyperparams['n_bands'])
        else:
            print('PCA will not apply')

        fit_params.setdefault('epochs', 10)
        fit_params.setdefault('train_sample_percentage', 0.5)
        fit_params.setdefault('dataloader_mode', 'random')
        fit_params.setdefault('loss', nn.CrossEntropyLoss(weight=self.hyperparams["weights"]))
        fit_params.setdefault('batch_size', 40)
        fit_params.setdefault('optimizer_params', {'learning_rate': 0.01, 'weight_decay': 0.01})
        fit_params.setdefault('optimizer',
                              optim.SGD(self.model.parameters(),
                                        lr=fit_params['optimizer_params']["learning_rate"],
                                        weight_decay=fit_params['optimizer_params']['weight_decay']))
        fit_params.setdefault('scheduler_type', None)
        fit_params.setdefault('scheduler_params', None)

        self.model, history = super().fit_nn(X=X,
                                             y=y,
                                             hyperparams=self.hyperparams,
                                             model=self.model,
                                             fit_params=fit_params)
        self.train_loss = history["train_loss"]
        self.val_loss = history["val_loss"]
        self.train_accs = history["train_accuracy"]
        self.val_accs = history["val_accuracy"]
    # ------------------------------------------------------------------------------------------------------------------

    def predict(self,
                X: HSImage,
                y: Optional[HSMask] = None) -> np.ndarray:

        if self.apply_pca:
            X = copy.deepcopy(X)
            X.data, _ = apply_pca(X.data, self.hyperparams['n_bands'])
        else:
            print('PCA will not apply')

        self.hyperparams.setdefault('batch_size', 40)
        prediction = super().predict_nn(X=X,
                                        y=y,
                                        model=self.model,
                                        hyperparams=self.hyperparams)

        return prediction
# ----------------------------------------------------------------------------------------------------------------------

