"""
Build the production image assets from the deskewed hand-drawn cocktail cards.

Outputs:
  1. site/assets/cards/<id>.jpg             clean same-ratio recipe card
  2. site/assets/illustrations/<id>.png     transparent 4:5 drink illustration
  3. site/assets/illustrations/<id>.jpg     normalized kraft fallback
  4. work/debug/*_sheet.*                   visual QA contact sheets

The deskewed sources in work/cards are intentionally treated as the source of
truth: they preserve the watercolor line work better than starting over from
the original angled photos.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

try:
    from rembg import new_session, remove
except Exception:  # pragma: no cover - optional dependency for local rebuilds
    new_session = None
    remove = None


ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "work" / "cards"
WEB_CARDS = ROOT / "site" / "assets" / "cards"
ILLU = ROOT / "site" / "assets" / "illustrations"
DEBUG = ROOT / "work" / "debug"

CARD_SIZE = (900, 1260)          # 1:1.4, consistent across the site
ILLU_SIZE = (1200, 1500)         # 4:5, long edge >= 1200px
PAPER_TARGET = np.array([229, 215, 177], dtype=np.float32)
LABEL_BG = (28, 24, 20)
_REMBG_SESSION = None

# Hand-tuned safe windows for the left-side watercolor artwork. The cards have
# fixed editorial layouts, and these windows remove nearby recipe text before
# the alpha pass starts.
ART_WINDOWS = {
    "americano": (0.105, 0.250, 0.455, 0.560),
    "aviation": (0.155, 0.185, 0.430, 0.760),
    "basil-smash": (0.120, 0.200, 0.455, 0.660),
    "bloody-mary": (0.070, 0.170, 0.465, 0.535),
    "blue-hawaii": (0.110, 0.185, 0.345, 0.760),
    "caipirinha": (0.055, 0.270, 0.545, 0.590),
    "gin-fizz": (0.150, 0.205, 0.500, 0.655),
    "lychee-gimlet": (0.160, 0.230, 0.450, 0.600),
    "manhattan": (0.195, 0.195, 0.500, 0.780),
    "margarita": (0.080, 0.260, 0.535, 0.720),
    "mojito": (0.075, 0.225, 0.440, 0.760),
    "moscow-mule": (0.145, 0.205, 0.520, 0.725),
    "negroni": (0.105, 0.225, 0.575, 0.775),
    "old-fashioned": (0.095, 0.230, 0.575, 0.700),
    "pina-colada": (0.170, 0.220, 0.550, 0.735),
    "sidecar": (0.060, 0.205, 0.495, 0.780),
    "spicy-lemon-drop": (0.110, 0.220, 0.530, 0.665),
    "strawberry-daiquiri": (0.070, 0.260, 0.545, 0.690),
    "tequila-sunrise": (0.205, 0.190, 0.520, 0.790),
    "whiskey-sour": (0.115, 0.220, 0.505, 0.720),
}


@dataclass
class ProcessedItem:
    name: str
    card_path: Path
    png_path: Path
    jpg_path: Path
    art_box: tuple[int, int, int, int]
    card_box: tuple[int, int, int, int]


def ensure_dirs() -> None:
    for path in (WEB_CARDS, ILLU, DEBUG):
        path.mkdir(parents=True, exist_ok=True)


def rembg_spatial_alpha(rgb: np.ndarray) -> np.ndarray | None:
    """Return a soft spatial keep mask from rembg, if available."""
    global _REMBG_SESSION
    if remove is None or new_session is None:
        return None
    if _REMBG_SESSION is None:
        _REMBG_SESSION = new_session("u2netp")
    try:
        cut = remove(Image.fromarray(rgb, "RGB"), session=_REMBG_SESSION).convert("RGBA")
    except Exception:
        return None
    alpha = np.array(cut.getchannel("A"))
    keep = (alpha > 7).astype(np.uint8) * 255
    keep = cv2.dilate(keep, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    keep = cv2.GaussianBlur(keep.astype(np.float32), (0, 0), 1.1)
    return np.clip(keep, 0, 255).astype(np.uint8)


def read_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.array(im.convert("RGB"))


def write_rgb(path: Path, rgb: np.ndarray, quality: int = 90) -> None:
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").save(
        path, quality=quality, optimize=True
    )


def paper_candidates(rgb: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    warm = r.astype(np.int16) - b.astype(np.int16)
    return (
        (gray > 135)
        & (hsv[..., 1] < 88)
        & (warm > 12)
        & (warm < 135)
        & (g.astype(np.int16) >= b.astype(np.int16) - 12)
    )


def normalize_paper(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """White-balance each card against its kraft paper background."""
    candidates = paper_candidates(rgb)
    if candidates.sum() < 500:
        bg = np.median(rgb.reshape(-1, 3), axis=0).astype(np.float32)
    else:
        bg = np.median(rgb[candidates], axis=0).astype(np.float32)
    gain = np.clip(PAPER_TARGET / np.maximum(bg, 1), 0.72, 1.32)
    balanced = np.clip(rgb.astype(np.float32) * gain, 0, 255).astype(np.uint8)
    return balanced, bg


def smooth_argmax(values: np.ndarray, start: int, end: int) -> int:
    segment = values[start:end].astype(np.float32)
    if segment.size == 0:
        return start
    k = max(5, int(segment.size * 0.015) | 1)
    segment = cv2.GaussianBlur(segment.reshape(1, -1), (k, 1), 0).ravel()
    return int(start + np.argmax(segment))


def first_strong(values: np.ndarray, start: int, end: int, frac: float = 0.38) -> int:
    segment = values[start:end].astype(np.float32)
    if segment.size == 0:
        return start
    k = max(5, int(segment.size * 0.035) | 1)
    smoothed = cv2.GaussianBlur(segment.reshape(-1, 1), (1, k), 0).ravel()
    threshold = max(5, float(smoothed.max()) * frac)
    hits = np.where(smoothed >= threshold)[0]
    return int(start + (hits[0] if hits.size else np.argmax(smoothed)))


def last_strong(values: np.ndarray, start: int, end: int, frac: float = 0.38) -> int:
    segment = values[start:end].astype(np.float32)
    if segment.size == 0:
        return end
    k = max(5, int(segment.size * 0.035) | 1)
    smoothed = cv2.GaussianBlur(segment.reshape(-1, 1), (1, k), 0).ravel()
    threshold = max(5, float(smoothed.max()) * frac)
    hits = np.where(smoothed >= threshold)[0]
    return int(start + (hits[-1] if hits.size else np.argmax(smoothed)))


def detect_inner_card_box(rgb: np.ndarray) -> tuple[int, int, int, int]:
    """Find the printed border and crop just inside it."""
    h, w = rgb.shape[:2]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    dark = ((gray < 118) & (hsv[..., 1] > 18)).astype(np.uint8)

    y_mid0, y_mid1 = int(h * 0.11), int(h * 0.91)
    x_mid0, x_mid1 = int(w * 0.13), int(w * 0.88)
    col_counts = dark[y_mid0:y_mid1].sum(axis=0)
    row_counts = dark[:, x_mid0:x_mid1].sum(axis=1)

    left_line = smooth_argmax(col_counts, int(w * 0.015), int(w * 0.16))
    right_line = smooth_argmax(col_counts, int(w * 0.84), int(w * 0.985))
    top_line = first_strong(row_counts, int(h * 0.005), int(h * 0.135))
    bottom_line = last_strong(row_counts, int(h * 0.84), int(h * 0.995))

    # Step inside the double border. This removes the ring/string area and
    # printed frame while keeping the title, recipe body, and SOING mark.
    left = left_line + int(w * 0.074)
    right = right_line - int(w * 0.060)
    top = top_line + int(h * 0.066)
    bottom = bottom_line - int(h * 0.040)

    # Fallbacks keep malformed detections from producing tiny crops.
    if right - left < w * 0.62:
        left, right = int(w * 0.08), int(w * 0.94)
    if bottom - top < h * 0.70:
        top, bottom = int(h * 0.07), int(h * 0.94)

    return (
        max(0, left),
        max(0, top),
        min(w, right),
        min(h, bottom),
    )


def resize_on_paper(crop: np.ndarray, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    bg = Image.new("RGB", size, tuple(int(v) for v in PAPER_TARGET))
    im = Image.fromarray(crop, "RGB")
    im.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
    bg.paste(im, ((target_w - im.width) // 2, (target_h - im.height) // 2))
    return bg.filter(ImageFilter.UnsharpMask(radius=0.8, percent=70, threshold=3))


def lab_diff_from_paper(roi: np.ndarray) -> tuple[np.ndarray, np.ndarray, int, int]:
    candidates = paper_candidates(roi)
    if candidates.sum() < 200:
        bg_rgb = np.median(roi.reshape(-1, 3), axis=0).astype(np.float32)
    else:
        bg_rgb = np.median(roi[candidates], axis=0).astype(np.float32)
    bg_patch = np.uint8([[np.clip(bg_rgb, 0, 255)]])
    lab = cv2.cvtColor(roi, cv2.COLOR_RGB2LAB).astype(np.float32)
    bg_lab = cv2.cvtColor(bg_patch, cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
    diff = np.linalg.norm(lab - bg_lab, axis=2)
    bg_gray = int(np.dot(bg_rgb, [0.299, 0.587, 0.114]))
    hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
    bg_sat = int(np.median(hsv[..., 1][candidates])) if candidates.any() else 45
    return diff, bg_rgb, bg_gray, bg_sat


def keep_art_components(strong: np.ndarray, color_hint: np.ndarray) -> np.ndarray:
    h, w = strong.shape
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    coarse = cv2.morphologyEx(strong.astype(np.uint8), cv2.MORPH_CLOSE, kernel_close)
    coarse = cv2.morphologyEx(coarse, cv2.MORPH_OPEN, kernel_open)
    coarse = cv2.dilate(coarse, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

    n, labels, stats, centroids = cv2.connectedComponentsWithStats(coarse, 8)
    if n <= 1:
        return coarse.astype(bool)

    min_area = max(130, int(h * w * 0.0012))
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = np.zeros_like(coarse, dtype=bool)

    color_hint = color_hint.astype(bool)
    candidates: list[tuple[float, int, int, int, int, int, int]] = []
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        bw = int(stats[label, cv2.CC_STAT_WIDTH])
        bh = int(stats[label, cv2.CC_STAT_HEIGHT])
        cx, cy = centroids[label]
        color_area = int(color_hint[labels == label].sum())
        slender_edge = (x <= w * 0.025 or x + bw >= w * 0.985) and bw < w * 0.055 and bh > h * 0.45
        right_gray_text = cx > w * 0.43 and color_area < max(16, int(area * 0.018))
        if slender_edge or right_gray_text or area < min_area:
            continue
        location = 1.15 - min(abs(cx / w - 0.40), 0.65)
        score = area * 0.35 * location + color_area * 7.5 + bh * 1.8
        candidates.append((score, label, x, y, bw, bh, color_area))

    if not candidates:
        label = int(np.argmax(areas) + 1)
        keep[labels == label] = True
        return cv2.dilate(keep.astype(np.uint8), kernel_close).astype(bool)

    primary_pool = [c for c in candidates if c[2] + c[4] * 0.5 < w * 0.72]
    if not primary_pool:
        primary_pool = candidates
    primary_pool.sort(reverse=True)
    _, primary_label, px, py, pw, ph, _ = primary_pool[0]
    primary_area = int(stats[primary_label, cv2.CC_STAT_AREA])
    ex0 = max(0, px - int(w * 0.09))
    ey0 = max(0, py - int(h * 0.11))
    ex1 = min(w, px + pw + int(w * 0.09))
    ey1 = min(h, py + ph + int(h * 0.11))

    for _, label, x, y, bw, bh, color_area in candidates:
        area = int(stats[label, cv2.CC_STAT_AREA])
        big_enough = area >= min_area or area >= primary_area * 0.035
        plausible_shape = bw > w * 0.025 and bh > h * 0.025
        cx = x + bw * 0.5
        cy = y + bh * 0.5
        center_near_primary = ex0 <= cx <= ex1 and ey0 <= cy <= ey1
        close_large_neighbor = (
            area >= primary_area * 0.12
            and cx < w * 0.58
            and ey0 - h * 0.05 <= cy <= ey1 + h * 0.05
        )
        has_color_or_is_primary = label == primary_label or color_area >= max(10, int(area * 0.01))
        if big_enough and plausible_shape and has_color_or_is_primary and (center_near_primary or close_large_neighbor):
            keep[labels == label] = True

    if keep.sum() == 0:
        keep[labels == primary_label] = True

    return cv2.dilate(keep.astype(np.uint8), kernel_close).astype(bool)


def cleanup_alpha_by_color(alpha: np.ndarray, color_hint: np.ndarray) -> np.ndarray:
    binary = (alpha > 12).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    if n <= 1:
        return alpha

    keep = np.zeros_like(binary, dtype=bool)
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = int(areas.max()) if areas.size else 0
    min_area = max(18, int(alpha.shape[0] * alpha.shape[1] * 0.00005))

    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        bw = int(stats[label, cv2.CC_STAT_WIDTH])
        bh = int(stats[label, cv2.CC_STAT_HEIGHT])
        component = labels == label
        color_area = int(color_hint[component].sum())
        color_ratio = color_area / max(area, 1)
        text_like = bw < alpha.shape[1] * 0.20 and bh < alpha.shape[0] * 0.20 and color_ratio < 0.018
        border_like = bw < alpha.shape[1] * 0.045 and bh > alpha.shape[0] * 0.42 and color_ratio < 0.025
        has_real_color = color_area >= max(10, int(area * 0.018))
        large_structural = area >= largest * 0.18 and not border_like
        if (has_real_color or large_structural) and not text_like and not border_like:
            keep[component] = True

    if keep.sum() == 0 and largest:
        keep[labels == int(np.argmax(areas) + 1)] = True

    cleaned = alpha.copy()
    cleaned[~keep] = 0
    return cleaned


def build_alpha(roi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    diff, bg_rgb, bg_gray, bg_sat = lab_diff_from_paper(roi)
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
    sat = hsv[..., 1].astype(np.float32)

    strong = (
        (diff > 19)
        | (gray.astype(np.int16) < bg_gray - 28)
        | ((sat > bg_sat + 28) & (gray < 238))
    )
    color_hint = (
        ((sat > bg_sat + 24) & (diff > 13) & (gray < 246))
        | ((sat > bg_sat + 12) & (diff > 28) & (gray < 230))
    )
    region = keep_art_components(strong, color_hint)

    alpha_diff = np.clip((diff - 8) / 34, 0, 1) * 255
    alpha_dark = np.clip((bg_gray - gray.astype(np.float32) - 6) / 48, 0, 1) * 255
    alpha_sat = np.clip((sat - bg_sat - 6) / 72, 0, 1) * 210
    alpha = np.maximum.reduce([alpha_diff, alpha_dark, alpha_sat])
    alpha[~region] = 0

    # Text and printed borders are dark like inked glass outlines. The reliable
    # distinction is color: every drink has watercolor fill/garnish, while the
    # recipe text is nearly neutral. Use the colored pixels to gate the usable
    # horizontal art band, then keep all line art within that band.
    color_gate = cv2.morphologyEx(
        color_hint.astype(np.uint8),
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)),
    )
    color_gate = cv2.dilate(color_gate, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(color_gate, 8)
    kept_color = np.zeros_like(color_gate, dtype=bool)
    for label in range(1, n):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area >= max(24, int(roi.shape[0] * roi.shape[1] * 0.00012)):
            kept_color[labels == label] = True
    col_counts = kept_color.sum(axis=0).astype(np.float32)
    if col_counts.max() > 0:
        k = max(11, int(roi.shape[1] * 0.045) | 1)
        col_counts = cv2.GaussianBlur(col_counts.reshape(1, -1), (k, 1), 0).ravel()
        threshold = max(8.0, float(col_counts.max()) * 0.14, roi.shape[0] * 0.012)
        active_cols = col_counts >= threshold
        runs: list[tuple[float, int, int]] = []
        start = None
        for i, active in enumerate(active_cols.tolist() + [False]):
            if active and start is None:
                start = i
            elif not active and start is not None:
                end = i
                width = end - start
                if width >= max(10, int(roi.shape[1] * 0.035)):
                    score = float(col_counts[start:end].sum()) * (1.25 - min(abs((start + end) / 2 / roi.shape[1] - 0.40), 0.7))
                    runs.append((score, start, end))
                start = None
        if runs:
            _, c0, c1 = max(runs)
        else:
            active_x = np.where(active_cols)[0]
            c0, c1 = (int(active_x.min()), int(active_x.max()) + 1) if len(active_x) else (0, roi.shape[1])
        pad_x = max(52, int(roi.shape[1] * 0.16))
        left = max(0, int(c0) - pad_x)
        right = min(roi.shape[1], int(c1) + pad_x)
        band = np.zeros_like(alpha, dtype=bool)
        band[:, left:right] = True
        alpha[~band] = 0

    spatial = rembg_spatial_alpha(roi)
    if spatial is not None:
        alpha *= spatial.astype(np.float32) / 255.0

    alpha = cleanup_alpha_by_color(alpha, color_hint)
    alpha = cv2.GaussianBlur(alpha.astype(np.float32), (0, 0), 0.65)
    alpha[alpha < 8] = 0

    # Unmatte against the kraft paper so semi-transparent watercolor edges do
    # not carry a tan halo when shown on dark backgrounds.
    a = np.clip(alpha / 255.0, 0.02, 1.0)[..., None]
    bg = bg_rgb.reshape(1, 1, 3)
    unmatte = (roi.astype(np.float32) - bg * (1 - a)) / a
    clean_rgb = np.where(alpha[..., None] > 12, np.clip(unmatte, 0, 255), roi)
    clean_rgb = (0.62 * clean_rgb + 0.38 * roi.astype(np.float32)).clip(0, 255)
    return clean_rgb.astype(np.uint8), alpha.astype(np.uint8)


def illustration_roi_box(name: str, card_box: tuple[int, int, int, int], shape: tuple[int, int, int]) -> tuple[int, int, int, int]:
    h, w = shape[:2]
    if name in ART_WINDOWS:
        x0, y0, x1, y1 = ART_WINDOWS[name]
        return (
            max(0, int(w * x0)),
            max(0, int(h * y0)),
            min(w, int(w * x1)),
            min(h, int(h * y1)),
        )
    left, top, right, bottom = card_box
    return (
        max(left, int(w * 0.075)),
        max(top, int(h * 0.135)),
        min(int(w * 0.565), right),
        min(int(h * 0.885), bottom),
    )


def trim_alpha(alpha: np.ndarray, pad: int = 22) -> tuple[int, int, int, int]:
    ys, xs = np.where(alpha > 10)
    if not len(xs):
        h, w = alpha.shape
        return 0, 0, w, h
    x0, x1 = xs.min(), xs.max() + 1
    y0, y1 = ys.min(), ys.max() + 1
    return (
        max(0, x0 - pad),
        max(0, y0 - pad),
        min(alpha.shape[1], x1 + pad),
        min(alpha.shape[0], y1 + pad),
    )


def place_on_canvas(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    x0, y0, x1, y1 = trim_alpha(alpha)
    rgba = np.dstack([rgb[y0:y1, x0:x1], alpha[y0:y1, x0:x1]])
    art = Image.fromarray(rgba, "RGBA")

    max_w = int(ILLU_SIZE[0] * 0.84)
    max_h = int(ILLU_SIZE[1] * 0.84)
    scale = min(max_w / art.width, max_h / art.height)
    art = art.resize(
        (max(1, int(round(art.width * scale))), max(1, int(round(art.height * scale)))),
        Image.Resampling.LANCZOS,
    )

    # Sharpen only the color channels; keep the feathered alpha untouched.
    r, g, b, a = art.split()
    rgb_im = Image.merge("RGB", (r, g, b)).filter(
        ImageFilter.UnsharpMask(radius=0.7, percent=75, threshold=2)
    )
    art = Image.merge("RGBA", (*rgb_im.split(), a))

    canvas = Image.new("RGBA", ILLU_SIZE, (0, 0, 0, 0))
    canvas.alpha_composite(art, ((ILLU_SIZE[0] - art.width) // 2, (ILLU_SIZE[1] - art.height) // 2))
    return canvas


def save_kraft_fallback(path: Path, art: Image.Image) -> None:
    bg = Image.new("RGB", ILLU_SIZE, tuple(int(v) for v in PAPER_TARGET))
    bg.paste(art.convert("RGBA"), mask=art.getchannel("A"))
    bg.save(path, quality=90, optimize=True)


def process(path: Path) -> ProcessedItem:
    name = path.stem
    raw = read_rgb(path)
    rgb, _ = normalize_paper(raw)
    card_box = detect_inner_card_box(rgb)

    card_crop = rgb[card_box[1] : card_box[3], card_box[0] : card_box[2]]
    card = resize_on_paper(card_crop, CARD_SIZE)
    card_path = WEB_CARDS / f"{name}.jpg"
    card.save(card_path, quality=88, optimize=True)

    art_box = illustration_roi_box(name, card_box, rgb.shape)
    roi = rgb[art_box[1] : art_box[3], art_box[0] : art_box[2]]
    clean_rgb, alpha = build_alpha(roi)
    art = place_on_canvas(clean_rgb, alpha)
    png_path = ILLU / f"{name}.png"
    jpg_path = ILLU / f"{name}.jpg"
    art.save(png_path, optimize=True)
    save_kraft_fallback(jpg_path, art)

    print(
        f"{name}: card_box={card_box} art_box={art_box} "
        f"alpha={int((np.array(art.getchannel('A')) > 0).sum())}"
    )
    return ProcessedItem(name, card_path, png_path, jpg_path, art_box, card_box)


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    draw.text(xy, text, fill=(234, 222, 196))


def illustration_sheet(items: list[ProcessedItem]) -> None:
    cols, tile_w, tile_h, label_h = 5, 280, 350, 28
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile_w, rows * (tile_h + label_h)), LABEL_BG)
    draw = ImageDraw.Draw(sheet)
    for i, item in enumerate(items):
        x, y = (i % cols) * tile_w, (i // cols) * (tile_h + label_h)
        bg = Image.new("RGB", (tile_w, tile_h), (47, 47, 45))
        art = Image.open(item.png_path).convert("RGBA")
        art.thumbnail((tile_w - 18, tile_h - 22), Image.Resampling.LANCZOS)
        bg.paste(art, ((tile_w - art.width) // 2, (tile_h - art.height) // 2), art)
        sheet.paste(bg, (x, y))
        label(draw, (x + 8, y + tile_h + 7), item.name)
    sheet.save(DEBUG / "refined_illustrations_sheet.jpg", quality=92)


def card_sheet(items: list[ProcessedItem]) -> None:
    cols, tile_w, tile_h, label_h = 5, 220, 315, 28
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile_w, rows * (tile_h + label_h)), LABEL_BG)
    draw = ImageDraw.Draw(sheet)
    for i, item in enumerate(items):
        x, y = (i % cols) * tile_w, (i // cols) * (tile_h + label_h)
        card = Image.open(item.card_path).convert("RGB")
        card.thumbnail((tile_w - 14, tile_h - 12), Image.Resampling.LANCZOS)
        sheet.paste(card, (x + (tile_w - card.width) // 2, y + 6))
        label(draw, (x + 8, y + tile_h + 7), item.name)
    sheet.save(DEBUG / "refined_cards_sheet.jpg", quality=92)


def main() -> None:
    ensure_dirs()
    items = [process(path) for path in sorted(CARDS.glob("*.jpg"))]
    illustration_sheet(items)
    card_sheet(items)
    print("contact sheets written")


if __name__ == "__main__":
    main()
