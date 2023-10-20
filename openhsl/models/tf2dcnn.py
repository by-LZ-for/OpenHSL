import os
import copy
import numpy as np
import wandb

from typing import Optional, Dict, Any

import tensorflow as tf
from keras.models import Sequential
from keras.layers import Dense, Dropout, Flatten, Conv2D, BatchNormalization
from keras.optimizers import SGD

from openhsl.hsi import HSImage
from openhsl.hs_mask import HSMask
from openhsl.data.utils import apply_pca
from openhsl.data.tf_dataloader import preprocess_data, get_data_generator, get_test_generator, get_train_val_gens
from openhsl.utils import init_wandb

os.environ["CUDA_VISIBLE_DEVICES"] = "0"


class TF2DCNN:

    def __init__(self,
                 n_classes: int,
                 n_bands: int,
                 apply_pca=False,
                 path_to_weights: str = None,
                 device: str = 'cpu'):

        self.hyperparams: dict[str: Any] = dict()
        self.hyperparams['patch_size'] = 5
        self.hyperparams['n_classes'] = n_classes
        self.hyperparams['ignored_labels'] = [0]
        self.hyperparams['device'] = device
        self.hyperparams['n_bands'] = n_bands
        self.hyperparams['center_pixel'] = True
        self.hyperparams['net_name'] = 'tf2d'

        self.pca = None

        self.train_loss = []
        self.val_loss = []
        self.train_accs = []
        self.val_accs = []

        self.apply_pca = apply_pca
        input_shape = (self.hyperparams['n_bands'], self.hyperparams['patch_size'], self.hyperparams['patch_size'])

        C1 = 3 * self.hyperparams['n_bands']

        self.model = Sequential()

        self.model.add(Conv2D(C1, (3, 3), activation='relu', input_shape=input_shape))
        self.model.add(BatchNormalization())
        self.model.add(Conv2D(3 * C1, (3, 3), activation='relu'))
        self.model.add(Dropout(0.25))

        self.model.add(Flatten())
        self.model.add(Dense(6 * self.hyperparams['n_bands'], activation='relu'))
        self.model.add(Dropout(0.5))
        self.model.add(Dense(self.hyperparams['n_classes'], activation='softmax'))

        sgd = SGD(learning_rate=0.0001,
                  decay=1e-6,
                  momentum=0.9,
                  nesterov=True)

        self.model.compile(loss='categorical_crossentropy',
                           optimizer=sgd,
                           metrics=['accuracy'])
        if path_to_weights:
            self.model.load_weights(path_to_weights)
    # ------------------------------------------------------------------------------------------------------------------

    def fit(self,
            X: HSImage,
            y: HSMask,
            fit_params: Dict):

        if self.apply_pca:
            X = copy.deepcopy(X)
            X.data, self.pca = apply_pca(X.data, self.hyperparams['n_bands'])
        else:
            print('PCA will not apply')

        fit_params.setdefault('epochs', 10)
        fit_params.setdefault('train_sample_percentage', 0.5)
        fit_params.setdefault('batch_size', 32)
        # ToDo: add setdefault for optimizer, optimizer params and loss as in other models fit
        fit_params.setdefault('scheduler_type', None)
        fit_params.setdefault('scheduler_params', None)
        fit_params.setdefault('wandb_vis', False)
        fit_params.setdefault('tensorboard_vis', False)

        train_generator, val_generator = get_train_val_gens(X=X.data,
                                                            y=y.get_2d(),
                                                            train_sample_percentage=fit_params['train_sample_percentage'],
                                                            patch_size=5)

        types = (tf.float32, tf.int32)
        shapes = ((self.hyperparams['n_bands'],
                   self.hyperparams['patch_size'],
                   self.hyperparams['patch_size']),
                  (self.hyperparams['n_classes'],))

        ds_train = tf.data.Dataset.from_generator(lambda: train_generator, types, shapes)
        ds_train = ds_train.batch(fit_params['batch_size']).repeat()
        ds_val = tf.data.Dataset.from_generator(lambda: val_generator, types, shapes)
        ds_val = ds_val.batch(fit_params['batch_size']).repeat()

        steps = len(train_generator) / fit_params['batch_size']
        val_steps = len(val_generator) / fit_params['batch_size']

        checkpoint_filepath = './checkpoints/tf2dcnn/'

        if not os.path.exists(checkpoint_filepath):
            os.makedirs(checkpoint_filepath)

        # add visualisations via callbacks
        callbacks = []

        if fit_params['wandb_vis']:
            wandb_run = init_wandb(path='wandb.yaml')
            if wandb_run:
                wandb_callback = wandb.keras.WandbCallback(monitor='val_loss',

                                                           log_evaluation=True,
                                                           )
                callbacks.append(wandb_callback)

        if fit_params['tensorboard_vis']:
            tensorboard_callback = tf.keras.callbacks.TensorBoard(log_dir="./tensorboard")
            callbacks.append(tensorboard_callback)

        history = self.model.fit(ds_train,
                                 validation_data=ds_val,
                                 validation_steps=val_steps,
                                 validation_batch_size=fit_params['batch_size'],
                                 batch_size=fit_params['batch_size'],
                                 epochs=fit_params['epochs'],
                                 steps_per_epoch=steps,
                                 verbose=1,
                                 callbacks=callbacks
                                 )

        self.train_loss = history.history.get('loss', [])
        self.val_loss = history.history.get('val_loss', [])
        self.train_accs = history.history.get('accuracy', [])
        self.val_accs = history.history.get('val_accuracy', [])

        self.model.save(f'{checkpoint_filepath}/weights.h5')

        if fit_params['wandb_vis']:
            if wandb_run:
                wandb_run.finish()
    # ------------------------------------------------------------------------------------------------------------------

    def predict(self,
                X: HSImage,
                y: Optional[HSMask] = None) -> np.ndarray:

        if self.apply_pca:
            X = copy.deepcopy(X)
            X.data, _ = apply_pca(X.data, self.hyperparams['n_bands'], self.pca)
        else:
            print('PCA will not apply')

        types = tf.float32
        shapes = (self.hyperparams['n_bands'], self.hyperparams['patch_size'], self.hyperparams['patch_size'])

        X = X.data

        test_generator = get_test_generator(X, patch_size=self.hyperparams['patch_size'])
        ds_test = tf.data.Dataset.from_generator(lambda: test_generator, types, shapes).batch(128)

        # TODO bad issue
        total = sum([1 for i in ds_test])

        test_generator = get_test_generator(X, patch_size=self.hyperparams['patch_size'])
        ds_test = tf.data.Dataset.from_generator(lambda: test_generator, types, shapes).batch(128)

        prediction = self.model.predict(ds_test, steps=total)
        pr = np.argmax(prediction, axis=1)
        predicted_mask = np.reshape(pr, (X.data.shape[0], X.data.shape[1]))

        return predicted_mask
    # ------------------------------------------------------------------------------------------------------------------
