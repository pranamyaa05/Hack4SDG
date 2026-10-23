from hashlib import sha256

import cv2
import numpy as np

from backend.measurement.vision import decode_image

from .models import ImageMetadata


def prepare_image(data: bytes):
    image = decode_image(data)
    height, width = image.shape[:2]
    factor = min(1.0, 1000 / max(height, width))
    quality = cv2.resize(
        image,
        (round(width * factor), round(height * factor)),
        interpolation=cv2.INTER_AREA,
    )
    gray = cv2.cvtColor(quality, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    overexposure = float(np.mean(gray >= 250))
    if brightness < 30 or brightness > 245 or overexposure > 0.98:
        raise ValueError("Photo is too dark or overexposed; retake in diffuse light")
    if blur < 20:
        raise ValueError(
            "Photo is blurred or has insufficient detail; retake with the object in focus"
        )
    ok, clean = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not ok:
        raise ValueError("Photo could not be normalized")
    factor = min(1.0, 768 / max(height, width))
    small = cv2.resize(
        image,
        (round(width * factor), round(height * factor)),
        interpolation=cv2.INTER_AREA,
    )
    ok, ai = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise ValueError("Photo could not be prepared for analysis")
    clean_bytes = clean.tobytes()
    metadata = ImageMetadata(
        sha256=sha256(clean_bytes).hexdigest(),
        width=width,
        height=height,
        brightness=brightness,
        blur_score=blur,
        overexposed_fraction=overexposure,
        ai_long_edge_pixels=max(small.shape[:2]),
    )
    return metadata, clean_bytes, ai.tobytes()
