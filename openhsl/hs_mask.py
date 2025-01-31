import h5py
import numpy as np
from PIL import Image
from scipy.io import loadmat, savemat
from typing import Optional, Dict
import os.path


class HSMask:
    """
    HSMask()
        Image-like object which contains:
            2D-Array
                Each pixel has value from [0, class_counts - 1]
            3D-Array
                Each layer is binary image where 1 is class and 0 is not-class

        Parameters
        ----------
        mask: np.ndarray
            3D-matrix which has a dimension X - Y - Z.
            where:
                X, Y data resolution.
                Z is a count of channels (1, 3, 4).
        label_class: dict
            dictionary where keys are number of the binary layer in mask
            and values are description class of this layer

        Attributes
        ----------
        data: np.ndarray

        label_class: dict

        Examples
        --------
            arr = np.zeros((100, 100, 3))
            md = {'1':'class_1', '2':'class_2'}

            hsi = HSMask(hsi=arr, metadata=md)
    """

    def __init__(self,
                 mask: Optional[np.array] = None,
                 label_class: Optional[Dict] = None):
        if np.any(mask):
            if HSMask.__is_correct_2d_mask(mask):
                print("got 2d mask")
                self.data = HSMask.convert_2d_to_3d_mask(mask)

            elif HSMask.__is_correct_3d_mask(mask):
                print("got 3d mask")
                self.data = mask
            else:
                print("Void data or incorrect data. Set data and label classes to None and None")
                self.data = None

            if np.any(self.data) and HSMask.__is_correct_class_dict(d=label_class, class_count=self.data.shape[-1]):
                self.label_class = label_class
            else:
                print("Void data or incorrect data. Set label classes to None")
                self.label_class = None

            self.n_classes = self.data.shape[-1]
        else:
            print("void mask")
            self.data = None
            self.label_class = None
    # ------------------------------------------------------------------------------------------------------------------

    def __getitem__(self, item):
        if item < len(self):
            return self.data[:, :, item]
        else:
            raise IndexError(f"{item} is too much for {len(self)} channels in hsi")
    # ------------------------------------------------------------------------------------------------------------------

    def __len__(self):
        if np.any(self.data):
            return self.data.shape[-1]
        else:
            return 0
    # ------------------------------------------------------------------------------------------------------------------

    def get_2d(self) -> np.ndarray:
        """
        get_2d()
            returns 2d-mask with values in [0,1,2...]

        """
        return HSMask.convert_3d_to_2d_mask(self.data)
    # ------------------------------------------------------------------------------------------------------------------

    def get_3d(self) -> np.ndarray:
        """
        get_3d()
            returns 3d-mask where each layer (Z-axe) is binary image
        """
        return self.data
    # ------------------------------------------------------------------------------------------------------------------

    def __update_label_class(self, label_class: Dict):
        if HSMask.__is_correct_class_dict(d=label_class,
                                          class_count=len(self.data)):
            self.label_class = label_class
    # ------------------------------------------------------------------------------------------------------------------

    def delete_layer(self, pos: int):
        """
        delete_layer(pos)
            deletes layer in mask by index
            Parameters
            ----------
            pos: int
                layer number for deleting
        """
        tmp_list = list(np.transpose(self.data, (2, 0, 1)))
        tmp_list.pop(pos)
        self.data = np.transpose(np.array(tmp_list), (1, 2, 0))
    # ------------------------------------------------------------------------------------------------------------------

    def add_void_layer(self, pos: int):
        """
        add_void_layer(pos)
            adds filled by zeros layer in mask by index
            Parameters
            ----------
            pos: int
                layer position for adding
        """
        tmp_list = list(np.transpose(self.data, (2, 0, 1)))
        tmp_list.insert(pos, np.zeros(self.data.shape[:-1], dtype="uint8"))
        self.data = np.transpose(np.array(tmp_list), (1, 2, 0))
    # ------------------------------------------------------------------------------------------------------------------

    def add_completed_layer(self, pos: int, layer: np.ndarray):
        """
        add_completed_layer(pos, layer)
            adds filled by completed layer in mask by index
            Parameters
            ----------
            pos: int
                layer position for adding
            layer: np.ndarray
                binary layer
        """
        if self.__is_correct_binary_layer(layer):
            tmp_list = list(np.transpose(self.data, (2, 0, 1)))
            tmp_list.insert(pos, layer)
            self.data = np.transpose(np.array(tmp_list), (1, 2, 0))
        else:
            raise ValueError("Incorrect layer!")
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def __is_correct_2d_mask(mask: np.ndarray) -> bool:
        """
        __is_correct_2d_mask(mask)
            2D mask must have class values as 0,1,2...
            minimal is 0 and 1 (binary image)

            Parameters
            ----------
            mask: np.ndarray

        """
        # input mask must have 2 dimensions
        if len(mask.shape) > 2:
            return False

        # data type in mask must be integer
        if mask.dtype not in ["uint8", "uint16", "uint32", "uint64",
                              "int8", "int16", "int32", "int64"]:
            return False

        # number of classes in mask must be as 0,1,2... not 1,2... not 0,2,5 ...
        if np.all(np.unique(mask) != np.array(range(0, len(np.unique(mask))))):
            return False

        return True
    # ------------------------------------------------------------------------------------------------------------------

    def __is_correct_binary_layer(self, layer: np.ndarray) -> bool:
        """
        __is_correct_binary_layer(layer)
            checks is input layer has only binary values (0 and 1) or not

            Parameters
            ----------
            layer: np.ndarray
        """
        return np.all(layer.shape == self.data.shape[:-1]) and np.all(np.unique(layer) == np.array([0, 1]))
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def __is_correct_3d_mask(mask: np.ndarray) -> bool:
        """
        __is_correct_3d_mask(mask)
            3D mask must have class values as binary image in N-layers
            Each layer must be binary!
            minimal is two-layer image

            Parameters
            ----------
            mask: np.ndarray

            Returns
            -------
        """
        # check 3D-condition and layer (class) count
        if len(mask.shape) != 3 and mask.shape[-1] < 2:
            return False

        # check each layer that it's binary
        for layer in np.transpose(mask, (2, 0, 1)):
            if np.all(np.unique(layer) != np.array([0, 1])):
                return False

        return True
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def __is_correct_class_dict(d: dict, class_count: int) -> bool:
        """
        __is_correct_class_dict(d, class_count)
            checks class descriptions in input dictionary
            Parameters
            ----------
            d: dict
            class_count: int
        """

        if not d:
            return False

        if len(d) != class_count and np.all(np.array(d.keys()) != np.array(range(0, class_count))):
            return False

        return True
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def convert_2d_to_3d_mask(mask: np.ndarray) -> np.ndarray:
        """
        convert_2d_to_3d_mask(mask)
            returns 3d mask consists binary layers from 2d mask

            Parameters
            ----------
            mask: np.ndarray
        """
        mask_3d = []
        for cl in np.unique(mask):

            mask_3d.append((mask == cl).astype('uint8'))
        mask_3d = np.array(mask_3d)

        return np.transpose(mask_3d, (1, 2, 0))
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def convert_3d_to_2d_mask(mask: np.ndarray) -> np.ndarray:
        mask_2d = np.zeros(mask.shape[:2])
        for cl, layer in enumerate(np.transpose(mask, (2, 0, 1))):
            mask_2d[layer == 1] = cl

        return mask_2d.astype('uint8')
    # ------------------------------------------------------------------------------------------------------------------

    def load(self,
             path_to_data: str,
             key: str = None):

        """
        load_mask(path_to_file, mat_key, h5_key)

            Reads information from a file,
            converting it to the numpy.ndarray format

            input data shape:
            ____________
            3-dimensional images in png, bmp, jpg
            format or h5, math, npy files are submitted to the input
            ____________

            Parameters
            ----------
            path_to_file: str
                Path to file
            key: str
                Key for field in .mat and .h5 file as dict object
                file['image']
        """

        def load_img(path_to_image: str) -> np.ndarray:
            """
            ____________
            necessary for reading 3-dimensional images
            ____________

            Parameters
            ----------
            path_to_image: str
                Path to file
            """
            img = Image.open(path_to_image).convert("L")
            img = np.array(img)
            if HSMask.__is_correct_2d_mask(img):
                return HSMask.convert_2d_to_3d_mask(img)
            else:
                raise ValueError("Not supported image type")

        _, file_extension = os.path.splitext(path_to_data)

        if file_extension in ['.jpg', '.jpeg', '.bmp', '.png']:
            '''
            loading a mask from images
            '''
            self.data = load_img(path_to_data)

        elif file_extension == '.npy':
            '''
            loading a mask from numpy file
            '''
            tmp_data = np.load(path_to_data)
            if HSMask.__is_correct_2d_mask(tmp_data):
                self.data = HSMask.convert_2d_to_3d_mask(tmp_data)
            elif HSMask.__is_correct_3d_mask(tmp_data):
                self.data = tmp_data
            else:
                raise ValueError("Unsupported type of mask")

        elif file_extension == '.mat':
            '''
            loading a mask from mat file
            '''
            tmp_data = loadmat(path_to_data)[key]
            if HSMask.__is_correct_2d_mask(tmp_data):
                self.data = HSMask.convert_2d_to_3d_mask(tmp_data)
            elif HSMask.__is_correct_3d_mask(tmp_data):
                self.data = tmp_data
            else:
                raise ValueError("Unsupported type of mask")

        elif file_extension == '.h5':
            '''
            loading a mask from h5 file
            '''
            tmp_data = h5py.File(path_to_data, 'r')[key]
            if HSMask.__is_correct_2d_mask(tmp_data):
                self.data = HSMask.convert_2d_to_3d_mask(tmp_data)
            elif HSMask.__is_correct_3d_mask(tmp_data):
                self.data = tmp_data
            else:
                raise ValueError("Unsupported type of mask")

        # updates number of classes after loading mask
        self.n_classes = self.data.shape[-1]
        self.label_class = {}
    # ------------------------------------------------------------------------------------------------------------------

    def save_to_mat(self,
                    path_to_file: str,
                    mat_key: str):
        """
        save_to_mat(path_to_file, mat_key)

            ____________
            save the mask in mat format
            ____________

            Parameters
            ----------
            path_to_file: str
                Path to file
            mat_key: str
                Key for field in .mat file as dict object
                mat_file['image']
        """
        temp_dict = {mat_key: self.data}
        savemat(path_to_file, temp_dict)
    # ------------------------------------------------------------------------------------------------------------------

    def save_to_h5(self,
                   path_to_file: str,
                   h5_key: str):
        """
        save_to_h5(path_to_file, h5_key)

        ____________
        save the mask in h5 format
        ____________

        Parameters
        ----------
        path_to_file: str
            Path to file
        h5_key: str
            Key for field in .mat file as dict object
            mat_file['image']
        h5_key: str
            Key for field in .h5 file as 5h object
        """

        with h5py.File(path_to_file, 'w') as f:
            f.create_dataset(h5_key, data=self.data)
    # ------------------------------------------------------------------------------------------------------------------
    
    def save_to_npy(self,
                    path_to_file: str):
        """
        save_to_npy(path_to_file)

        ____________
        save the mask in numpy format
        ____________

        Parameters
        ----------
        path_to_file: str
            Path to file
        """
        np.save(path_to_file, self.data)
    # ------------------------------------------------------------------------------------------------------------------

    def save_image(self,
                   path_to_save_file: str):
        """
        save_image(path_to_save_file)

        ____________
        save the mask in 'jpg','jpeg','bmp','png' format
        ____________

        Parameters
        ----------
        path_to_save_file: str
            Path to file
        """
        img = Image.fromarray(self.data[:, :, 0])
        img.save(path_to_save_file)
    # ------------------------------------------------------------------------------------------------------------------

    def load_class_info(self):
        pass
    # ------------------------------------------------------------------------------------------------------------------

    def save_class_info(self):
        pass
    # ------------------------------------------------------------------------------------------------------------------
