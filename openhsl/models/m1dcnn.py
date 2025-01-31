from openhsl.models.model import Model
from openhsl.hsi import HSImage
from openhsl.hs_mask import HSMask

import copy
from openhsl.data.utils import apply_pca

import numpy as np
import math
from typing import Any, Optional, Dict

import torch
import torch.nn as nn
import torch.optim as optim
from torch.nn import init


class M1DCNN_Net(nn.Module):
    """
        Deep Convolutional Neural Networks for Hyperspectral Image Classification
        Wei Hu, Yangyu Huang, Li Wei, Fan Zhang and Hengchao Li
        Journal of Sensors, Volume 2015 (2015)
        https://www.hindawi.com/journals/js/2015/258619/
        """

    @staticmethod
    def weight_init(m):
        # [All the trainable parameters in our CNN should be initialized to
        # be a random value between −0.05 and 0.05.]
        if isinstance(m, nn.Linear) or isinstance(m, nn.Conv1d):
            init.uniform_(m.weight, -0.05, 0.05)
            init.zeros_(m.bias)
    # ------------------------------------------------------------------------------------------------------------------

    def _get_final_flattened_size(self):
        with torch.no_grad():
            x = torch.zeros(1, 1, self.input_channels)
            x = self.conv_1(x)
            x = self.conv_2(x)
            x = self.pool(x)
        return x.numel()
    # ------------------------------------------------------------------------------------------------------------------

    def __init__(self,
                 input_channels,
                 n_classes,
                 kernel_size=None,
                 pool_size=None):
        super(M1DCNN_Net, self).__init__()
        if kernel_size is None:
            # [In our experiments, k1 is better to be [ceil](n1/9)]
            kernel_size = math.ceil(input_channels / 9)
        if pool_size is None:
            # The authors recommand that k2's value is chosen so that the pooled features have 30~40 values
            # ceil(kernel_size/5) gives the same values as in the paper so let's assume it's okay
            pool_size = math.ceil(kernel_size / 5)
        self.input_channels = input_channels

        # [The first hidden convolution layer C1 filters the n1 x 1 input data with 20 kernels of size k1 x 1]
        self.conv_1 = nn.Conv1d(1, 20, kernel_size)
        self.conv_2 = nn.Conv1d(20, 20, kernel_size)
        self.bn_conv = nn.BatchNorm1d(20)
        self.pool = nn.MaxPool1d(pool_size)
        self.features_size = self._get_final_flattened_size()
        # [n4 is set to be 100]
        self.fc1 = nn.Linear(self.features_size, 100)
        self.fc2 = nn.Linear(100, n_classes)
        self.apply(self.weight_init)
    # ------------------------------------------------------------------------------------------------------------------

    def forward(self, x):
        # [In our design architecture, we choose the hyperbolic tangent function tanh(u)]
        x = x.squeeze(dim=-1).squeeze(dim=-1)
        x = x.unsqueeze(1)
        x = self.conv_1(x)
        x = self.bn_conv(x)
        x = self.conv_2(x)
        x = torch.tanh(self.pool(x))
        x = x.view(-1, self.features_size)
        x = torch.tanh(self.fc1(x))
        x = self.fc2(x)
        return x
# ----------------------------------------------------------------------------------------------------------------------


class M1DCNN(Model):
    def __init__(self,
                 n_classes,
                 device,
                 n_bands,
                 apply_pca=False,
                 path_to_weights=None
                 ):
        super(M1DCNN, self).__init__()
        self.apply_pca = apply_pca
        self.hyperparams: dict[str: Any] = dict()
        self.hyperparams['patch_size'] = 1
        self.hyperparams['n_classes'] = n_classes
        self.hyperparams['ignored_labels'] = [0]
        self.hyperparams['device'] = device
        self.hyperparams['n_bands'] = n_bands
        self.hyperparams['center_pixel'] = True
        self.hyperparams['net_name'] = 'm1dcnn'
        weights = torch.ones(n_classes)
        weights[torch.LongTensor(self.hyperparams["ignored_labels"])] = 0.0
        weights = weights.to(device)
        self.hyperparams["weights"] = weights

        self.model = M1DCNN_Net(n_bands, n_classes)

        if path_to_weights:
            self.model.load_state_dict(torch.load(path_to_weights))

        self.hyperparams.setdefault("supervision", "full")
        self.hyperparams.setdefault("flip_augmentation", False)
        self.hyperparams.setdefault("radiation_augmentation", False)
        self.hyperparams.setdefault("mixture_augmentation", False)
        self.hyperparams["center_pixel"] = True
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
        fit_params.setdefault('batch_size', 100)
        fit_params.setdefault('optimizer_params', {'learning_rate': 0.05})
        fit_params.setdefault('optimizer',
                              optim.SGD(self.model.parameters(),
                                        lr=fit_params['optimizer_params']["learning_rate"]))
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

        self.hyperparams.setdefault('batch_size', 100)
        prediction = super().predict_nn(X=X,
                                        y=y,
                                        model=self.model,
                                        hyperparams=self.hyperparams)
        return prediction
# ----------------------------------------------------------------------------------------------------------------------
