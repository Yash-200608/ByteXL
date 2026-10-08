import cv2
import numpy as np
from PIL import Image


def to_gray(image: Image.Image) -> np.ndarray:
    arr = np.array(image.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)


def estimate_skew(gray: np.ndarray, max_angle: float = 10.0) -> float:
    small = gray
    scale = 1.0
    if max(gray.shape) > 1600:
        scale = 1600 / max(gray.shape)
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    binary = cv2.adaptiveThreshold(small, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 15)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
    merged = cv2.dilate(binary, kernel, iterations=1)
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    angles, weights = [], []
    for c in contours:
        (cx, cy), (w, h), angle = cv2.minAreaRect(c)
        if w < h:
            w, h = h, w
            angle = angle - 90
        if w < 60 or h < 4 or w / max(h, 1) < 4:
            continue
        if angle > 45:
            angle -= 90
        if angle < -45:
            angle += 90
        if abs(angle) <= max_angle:
            angles.append(angle)
            weights.append(w)
    if not angles:
        return 0.0
    order = np.argsort(angles)
    a = np.array(angles)[order]
    w = np.array(weights)[order]
    cum = np.cumsum(w)
    return float(a[np.searchsorted(cum, cum[-1] / 2)])


def rotate(gray: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.2:
        return gray
    h, w = gray.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def enhance_contrast(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    out = clahe.apply(gray)
    lo, hi = np.percentile(out, (1, 99))
    if hi - lo < 10:
        return out
    stretched = np.clip((out.astype(np.float32) - lo) * 255.0 / (hi - lo), 0, 255)
    return stretched.astype(np.uint8)


def preprocess_photo(image: Image.Image) -> tuple[Image.Image, float]:
    gray = to_gray(image)
    angle = estimate_skew(gray)
    gray = rotate(gray, angle)
    gray = enhance_contrast(gray)
    return Image.fromarray(gray).convert("RGB"), angle
