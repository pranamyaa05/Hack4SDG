"""One layout shared by PDF, synthetic fixtures, and calibration."""

from io import BytesIO

import cv2
import numpy as np
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

PAGE_MM = (210, 297)
PPM = 10
MARKER_SIZE_MM = 30
MARKERS = {0: (12, 12), 1: (168, 12), 2: (12, 255), 3: (168, 255)}
WORK_AREA = (45, 48, 165, 205)
CARD_RECT = (60, 215, 85.60, 53.98)
MM_TO_PT = 72 / 25.4


def dictionary():
    return cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def marker_image(marker_id: int):
    return cv2.aruco.generateImageMarker(dictionary(), marker_id, 300)


def marker_corners(marker_id: int):
    x, y = MARKERS[marker_id]
    s = MARKER_SIZE_MM
    return np.array([[x, y], [x + s, y], [x + s, y + s], [x, y + s]], dtype=np.float64)


def render_sheet():
    """Raster companion for calibration tests and on-screen guidance, not print scaling."""
    image = np.full((2970, 2100, 3), 255, dtype=np.uint8)
    x0, y0, x1, y1 = WORK_AREA
    image[y0 * PPM : y1 * PPM, x0 * PPM : x1 * PPM] = 166
    for marker_id, (x, y) in MARKERS.items():
        image[y * PPM : (y + 30) * PPM, x * PPM : (x + 30) * PPM] = cv2.cvtColor(
            marker_image(marker_id), cv2.COLOR_GRAY2BGR
        )
    return image


def fit_sheet_pdf() -> bytes:
    stream = BytesIO()
    c = canvas.Canvas(
        stream, pagesize=(210 * MM_TO_PT, 297 * MM_TO_PT), pageCompression=1
    )
    c.setTitle("ReFit Fit Sheet v1 - print at actual size")

    def text(x, y, value, size=8):
        c.setFont("Helvetica", size)
        c.setFillGray(0)
        c.drawString(x * MM_TO_PT, (297 - y) * MM_TO_PT, value)

    def rect(x, y, w, h, fill=0):
        c.rect(
            x * MM_TO_PT,
            (297 - y - h) * MM_TO_PT,
            w * MM_TO_PT,
            h * MM_TO_PT,
            stroke=1,
            fill=fill,
        )

    text(48, 15, "ReFit / FIT SHEET v1", 14)
    text(48, 23, "A4 - print at 100% / Actual size", 9)
    text(48, 30, "Disable Fit to page. Keep the sheet flat.")
    text(48, 37, "Overhead photo; all markers visible; diffuse light.")
    c.setFillGray(166 / 255)
    c.setStrokeGray(166 / 255)
    rect(45, 48, 120, 157, fill=1)
    c.setStrokeGray(0)
    for marker_id, (x, y) in MARKERS.items():
        c.drawImage(
            ImageReader(Image.fromarray(marker_image(marker_id))),
            x * MM_TO_PT,
            (297 - y - 30) * MM_TO_PT,
            width=30 * MM_TO_PT,
            height=30 * MM_TO_PT,
            mask=None,
        )
    text(48, 44, "Place the object inside the gray area.")
    text(60, 211, "Scale check: bank/ID card must match BOTH axes.")
    rect(*CARD_RECT)
    text(65, 228, "85.60 x 53.98 mm", 11)
    text(65, 235, "Compare a card, or measure the box.")
    text(65, 242, "Do not photograph personal card details.")
    text(65, 249, "Mismatch? Reprint at Actual size.")
    # Vertical 150 mm ruler and strip stay outside the clear measurement work area.
    for x in (22, 185):
        c.setLineWidth(0.3)
        for mm in range(151):
            y = (297 - 50 - mm) * MM_TO_PT
            length = 5 if mm % 10 == 0 else (3 if mm % 5 == 0 else 1.5)
            c.line(x * MM_TO_PT, y, (x + length) * MM_TO_PT, y)
            if mm % 10 == 0:
                text(x + 5.5, 51 + mm, str(mm), 6)
    rect(181, 50, 18, 150)
    text(12, 211, "mm ruler", 7)
    text(173, 209, "Cut-out strip", 7)
    text(48, 278, "Check scale before use. Photos do not reveal hidden thickness.", 8)
    text(48, 284, "Drawers: cut a window in the gray area; keep all markers intact.", 7)
    text(
        48,
        290,
        "Tape flat to the drawer face. Not a medical device; test physical fit.",
        7,
    )
    c.showPage()
    c.save()
    return stream.getvalue()
