from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import warnings

from PIL import Image, ImageFile, UnidentifiedImageError

from pims_v1.config import settings

# Large personal-library photos (panoramas, high-resolution scans) routinely
# exceed Pillow's conservative default of ~89M pixels. Raise the limit so these
# legitimate files are processed instead of being rejected as decompression
# bombs, while still keeping a ceiling that guards against genuinely abusive
# inputs (Pillow raises DecompressionBombError above 2x this value).
Image.MAX_IMAGE_PIXELS = settings.max_image_pixels

# Tolerate slightly truncated JPEG/PNG streams so a single bad trailing byte
# does not block hashing/thumbnailing of an otherwise readable photo.
ImageFile.LOAD_TRUNCATED_IMAGES = True


class ImageProcessingError(RuntimeError):
    """Expected per-file image processing failure."""


IMAGE_PROCESSING_EXCEPTIONS = (
    OSError,
    UnidentifiedImageError,
    Image.DecompressionBombError,
    Image.DecompressionBombWarning,
)


@contextmanager
def safe_image_open(
    path: str | Path,
    *,
    prescale: tuple[int, int] | None = None,
) -> Iterator[Image.Image]:
    """Open an image, converting expected per-file failures into ImageProcessingError.

    When ``prescale`` is given and the source is a JPEG, Pillow's draft mode is
    used to decode at a reduced resolution. This dramatically lowers decode time
    and memory for very large images when the caller only needs a downscaled
    result (thumbnails, perceptual hashes).
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if prescale is not None:
                    try:
                        image.draft(None, prescale)
                    except (OSError, ValueError):
                        pass
                yield image
    except IMAGE_PROCESSING_EXCEPTIONS as exc:
        raise ImageProcessingError(str(exc)) from exc
