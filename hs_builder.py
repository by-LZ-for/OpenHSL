import numpy as np
from hsi import HSImage
from hs_raw_pb_data import RawData
from gaidel_legacy import build_hypercube_by_videos
from typing import Optional
from utils import gaussian

import cv2
import math
from tqdm import tqdm
from matplotlib import pyplot as plt
from sklearn.linear_model import LinearRegression


class HSBuilder:
    """
    HSBuilder(path_to_data, path_to_metadata=None, data_type=None)

        Build a HSI object from HSRawData

        Parameters
        ----------
        path_to_data : str

        path_to_metadata : str

        data_type : str
            'images'
            'video'

        Attributes
        ----------
        hsi : HSImage
        frame_iterator: RawData
        Examples
        --------

    """

    def __init__(self, path_to_data, path_to_metadata=None, data_type=None):
        """

        """
        self.path_to_data = path_to_data
        self.path_to_metadata = path_to_metadata
        self.hsi: Optional[HSImage] = None
        self.frame_iterator = RawData(path_to_data=path_to_data, type_data=data_type)
    # ------------------------------------------------------------------------------------------------------------------

    # TODO must be realised
    def __norm_frame_camera_illumination(self, frame: np.ndarray, light_coeff: np.ndarray) -> np.ndarray:
        """
        Normalizes illumination on frame.
        Frame have heterogeneous illumination by slit defects. It must be corrected

        Parameters
        ----------
        frame

        Returns
        -------
        frame
        """
        if frame.shape != light_coeff.shape:
            raise Exception("Uncomparable shapes of frame and light source")

        return np.multiply(frame, light_coeff)
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def __get_slit_angle(frame: np.ndarray) -> float:
        """
            Returns slit tilt angle in degrees (nor radians!)
        """

        _, frame_t = cv2.threshold(frame, 250, 255, cv2.THRESH_BINARY)
        y, x = np.where(frame_t > 0)
        lr = LinearRegression().fit(x.reshape(-1, 1), y)
        ang = math.degrees(math.atan(lr.coef_))
        return ang
    # ------------------------------------------------------------------------------------------------------------------

    @staticmethod
    def __norm_rotation_frame(frame: np.ndarray) -> np.ndarray:
        """
            Normalizes slit angle
        """
        angle = HSBuilder.__get_slit_angle(frame)
        #  rotate frame while angle is not in (-0.01; 0.01) degrees
        while abs(angle) > 0.01:
            h, w = frame.shape
            center_x, center_y = (w // 2, h // 2)
            angle = HSBuilder.__get_slit_angle(frame)
            rotation_matrix = cv2.getRotationMatrix2D((center_x, center_y), angle, 1.0)
            frame = cv2.warpAffine(frame, rotation_matrix, (w, h))

        return frame

    # TODO must be realised
    def __norm_frame_camera_geometry(self,
                                     frame: np.ndarray,
                                     norm_rotation=False,
                                     barrel_dist_norm=False) -> np.ndarray:
        """
        Normalizes geometric distortions on frame.

        Parameters
        ----------
        frame

        Returns
        -------
        frame

        """
        if norm_rotation:
            frame = HSBuilder.__norm_rotation_frame(frame=frame)

        return frame
    # ------------------------------------------------------------------------------------------------------------------

    # TODO must be realised
    @staticmethod
    def get_roi(frame: np.ndarray) -> np.ndarray:
        """
        For this moment works to microscope rough settings
        Parameters
        ----------
        frame :

        Returns
        -------

        """
        gap_coord = 620
        range_to_spectrum = 185
        range_to_end_spectrum = 250
        left_bound_spectrum = 490
        right_bound_spectrum = 1390
        x1 = gap_coord + range_to_spectrum
        x2 = x1 + range_to_end_spectrum
        return frame[x1: x2, left_bound_spectrum: right_bound_spectrum].T
    # ------------------------------------------------------------------------------------------------------------------

    # TODO must be realised
    def __some_preparation_on_frame(self, frame: np.ndarray) -> np.ndarray:
        """

        Parameters
        ----------
        frame : np.ndarray

        Returns
        -------
        """
        return frame
# ------------------------------------------------------------------------------------------------------------------

    # TODO works not correct!
    @staticmethod
    def __principal_slices(frame: np.ndarray, nums_bands: int) -> np.ndarray:
        """
        Compresses the frame by number of channels
        
        Parameters
        ----------
        frame: np.ndarray
            2D frame which we wanna compress from shape (W, H) ---> (W, nums_bands) 
        
        nums_bands: int
            Final numbers of channels 

        Returns
        -------
        Compress np.ndarray

        """
        n, m = frame.shape 

        width = m // nums_bands 
        gaussian_window = gaussian(width, width / 2.0, width / 6.0) 
        mid = len(gaussian_window) // 2 
        gaussian_window[mid] = 1.0 - np.sum(gaussian_window) + gaussian_window[mid] 
        ans = np.zeros(shape=(n, nums_bands), dtype=np.uint8) 
        for j in range(nums_bands): 
            left_bound = j * m // nums_bands 
            ans[:, j] = np.tensordot( 
                frame[:, left_bound:left_bound + len(gaussian_window)], 
                gaussian_window, 
                axes=([1], [0]), 
            )
        return ans
# ------------------------------------------------------------------------------------------------------------------

    def build(self,
              principal_slices,
              norm_rotation=False,
              barrel_dist_norm=False,
              light_norm=False,
              roi=False):
        """
            Creates HSI from device-data
        """
        preproc_frames = []

        # TODO remake it! It's hardcoded
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
        light_coeff = cv2.imread('./test_data/builder/micro_light_source.png', 0)
        light_coeff = HSBuilder.__norm_rotation_frame(light_coeff)
        light_coeff = HSBuilder.get_roi(frame=light_coeff)
        light_coeff = 1 / (light_coeff / np.max(light_coeff))
        # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

        for frame in tqdm(self.frame_iterator, total=len(self.frame_iterator), desc='Preprocessing frames'):
            frame = self.__norm_frame_camera_geometry(frame=frame,
                                                      norm_rotation=norm_rotation,
                                                      barrel_dist_norm=barrel_dist_norm)
            if roi:
                frame = HSBuilder.get_roi(frame=frame)
            if principal_slices:
                frame = self.__principal_slices(frame, principal_slices)
            if light_norm:
                frame = self.__norm_frame_camera_illumination(frame=frame, light_coeff=light_coeff)
            preproc_frames.append(frame)
            
        data = np.array(preproc_frames)
        if self.path_to_metadata:
            data = build_hypercube_by_videos(data, self.path_to_metadata)
            
        self.hsi = HSImage(hsi=data, wavelengths=None)
    # ------------------------------------------------------------------------------------------------------------------

    def get_hsi(self) -> HSImage:
        """

        Returns
        -------
        self.hsi : HSImage
            Builded from source hsi object

        """
        try:
            return self.hsi
        except:
            pass
    # ------------------------------------------------------------------------------------------------------------------
