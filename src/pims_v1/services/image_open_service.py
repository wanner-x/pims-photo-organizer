from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import warnings

from PIL import Image, UnidentifiedImageError


class ImageProcessingError(RuntimeError):
    """Expected per-file image processing failure."""


IMAGE_PROCESSING_EXCEPTIONS = (
    OSError,
    UnidentifiedImageError,
    Image.DecompressionBombError,
    Image.DecompressionBombWarning,
)


@contextmanager
def safe_image_open(path: str | Path) -> Iterator[Image.Image]:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                yield image
    except IMAGE_PROCESSING_EXCEPTIONS as exc:
        raise ImageProcessingError(str(exc)) from exc
