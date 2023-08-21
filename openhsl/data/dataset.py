import numpy as np
from typing import Optional
from openhsl.hsi import HSImage
from openhsl.hs_mask import HSMask
from typing import Tuple


def get_dataset(hsi: HSImage, mask: Optional[HSMask], norm=None) -> Tuple[np.ndarray, np.ndarray]:
    """
    return data from .mat files in tuple

    Parameters
    ----------
    hsi: HSImage
    mask: HSMask
    Returns
    ----------
    img : np.array
        hyperspectral image
    gt : np.ndarray
        mask of hyperspectral image

    """
    ignored_labels = [0]
    img = hsi.data

    if mask:
        gt = mask.get_2d()
        label_values = np.unique(gt)
    else:
        gt = None
        label_values = [0]

    img = img.astype("float32")

    return img, gt
