import io
import json
import os
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess
import tempfile

from django.core.files.base import ContentFile
from PIL import ExifTags, Image
import pillow_heif
import rawpy

# Register HEIF/AVIF support in Pillow (handles both .heic and .avif)
pillow_heif.register_heif_opener()

RAW_EXTENSIONS = {".nef", ".cr2", ".cr3", ".dng", ".arw", ".orf", ".raf", ".rw2"}
MAX_DIMENSION = 1920
EXIF_DISPLAY_FIELDS = (
    ("Make", "Camera Make"),
    ("Model", "Camera Model"),
    ("LensModel", "Lens"),
    ("DateTimeOriginal", "Captured"),
    ("ExposureTime", "Shutter"),
    ("FNumber", "Aperture"),
    ("ISOSpeedRatings", "ISO"),
    ("FocalLength", "Focal Length"),
    ("FocalLengthIn35mmFilm", "35mm Equivalent"),
    ("ImageWidth", "Width"),
    ("ImageLength", "Height"),
)
EXIF_TAG_IDS = {name: tag_id for tag_id, name in ExifTags.TAGS.items()}
EXIFTOOL_BIN = shutil.which("exiftool")


def downscale_if_needed(img: Image.Image) -> Image.Image:
    w, h = img.size
    if w <= MAX_DIMENSION and h <= MAX_DIMENSION:
        return img
    scale = MAX_DIMENSION / max(w, h)
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def _thumbnail_format_and_extension(name: str) -> tuple[str, str]:
    lower = name.lower()
    if lower.endswith(".png"):
        return "PNG", ".png"
    if lower.endswith(".webp"):
        return "WEBP", ".webp"
    if lower.endswith(".avif"):
        return "AVIF", ".avif"
    return "JPEG", ".jpg"


def _extract_exif_bytes(file_bytes: bytes) -> bytes:
    try:
        temp_img = Image.open(io.BytesIO(file_bytes))
        return temp_img.info.get("exif", b"")
    except Exception:
        return b""


def _extract_exiftool_summary(file_bytes: bytes) -> dict[str, str]:
    if not EXIFTOOL_BIN:
        return {}

    with tempfile.NamedTemporaryFile(suffix=".nef", delete=True) as tmp:
        tmp.write(file_bytes)
        tmp.flush()
        try:
            result = subprocess.run(
                [EXIFTOOL_BIN, "-j", "-n", tmp.name],
                capture_output=True,
                text=True,
                check=True,
            )
        except Exception:
            return {}

    try:
        payload = json.loads(result.stdout)[0]
    except Exception:
        return {}

    summary: dict[str, str] = {}
    mappings = [
        ("Make", "Camera Make", payload.get("Make")),
        ("Model", "Camera Model", payload.get("Model")),
        ("Lens", "Lens", payload.get("Lens") or payload.get("LensID") or payload.get("LensSpec")),
        ("DateTimeOriginal", "Captured", payload.get("DateTimeOriginal")),
        ("ExposureTime", "Shutter", payload.get("ExposureTime") or payload.get("ShutterSpeed")),
        ("FNumber", "Aperture", payload.get("FNumber") or payload.get("Aperture")),
        ("ISO", "ISO", payload.get("ISO")),
        ("FocalLength", "Focal Length", payload.get("FocalLength")),
        ("FocalLengthIn35mmFormat", "35mm Equivalent", payload.get("FocalLengthIn35mmFormat")),
        ("ImageWidth", "Width", payload.get("ImageWidth")),
        ("ImageHeight", "Height", payload.get("ImageHeight")),
    ]
    for tag_name, label, value in mappings:
        if value in (None, ""):
            continue
        summary[label] = _format_exif_value(tag_name, value)

    if payload.get("GPSVersionID") or payload.get("GPSLatitude") or payload.get("GPSLongitude"):
        summary["GPS"] = "Available"
    return summary


def _format_rational(value) -> str:
    try:
        if isinstance(value, (tuple, list)) and len(value) == 2:
            fraction = Fraction(value[0], value[1])
        else:
            fraction = Fraction(value).limit_denominator()
    except Exception:
        return str(value)
    if fraction.denominator == 1:
        return str(fraction.numerator)
    if abs(float(fraction)) >= 1:
        return f"{float(fraction):.1f}".rstrip("0").rstrip(".")
    return f"{fraction.numerator}/{fraction.denominator}"


def _format_exif_value(tag_name: str, value) -> str:
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="ignore").strip("\x00 ")
        except Exception:
            value = repr(value)
    if tag_name == "ExposureTime":
        formatted = _format_rational(value)
        return f"{formatted}s"
    if tag_name == "FNumber":
        return f"f/{_format_rational(value)}"
    if tag_name == "FocalLength":
        return f"{_format_rational(value)}mm"
    if tag_name == "FocalLengthIn35mmFormat":
        return f"{_format_rational(value)}mm"
    if tag_name in {"ImageWidth", "ImageLength"}:
        return str(value)
    if tag_name == "ISOSpeedRatings":
        if isinstance(value, (tuple, list)):
            return ", ".join(str(item) for item in value)
        return str(value)
    if tag_name == "Lens":
        if isinstance(value, (tuple, list)):
            pieces = list(value)
            if len(pieces) >= 4:
                try:
                    focal_min = float(pieces[0])
                    focal_max = float(pieces[1])
                    aperture_min = float(pieces[2])
                    aperture_max = float(pieces[3])
                    focal = f"{focal_min:g}" if focal_min == focal_max else f"{focal_min:g}-{focal_max:g}"
                    aperture = (
                        f"{aperture_min:g}"
                        if aperture_min == aperture_max
                        else f"{aperture_min:g}-{aperture_max:g}"
                    )
                    return f"{focal}mm f/{aperture}"
                except Exception:
                    pass
            return " ".join(str(item) for item in pieces)
        if isinstance(value, str):
            pieces = value.split()
            if len(pieces) >= 4 and all(part.replace(".", "", 1).isdigit() for part in pieces[:4]):
                try:
                    focal_min = float(pieces[0])
                    focal_max = float(pieces[1])
                    aperture_min = float(pieces[2])
                    aperture_max = float(pieces[3])
                    focal = f"{focal_min:g}" if focal_min == focal_max else f"{focal_min:g}-{focal_max:g}"
                    aperture = (
                        f"{aperture_min:g}"
                        if aperture_min == aperture_max
                        else f"{aperture_min:g}-{aperture_max:g}"
                    )
                    return f"{focal}mm f/{aperture}"
                except Exception:
                    pass
        return str(value)
    if isinstance(value, tuple) and len(value) == 2:
        return f"{_format_rational(value[0])}/{_format_rational(value[1])}"
    return str(value)


def extract_exif_summary(file_bytes: bytes) -> dict[str, str]:
    summary = _extract_exiftool_summary(file_bytes)
    if summary:
        return summary

    try:
        image = Image.open(io.BytesIO(file_bytes))
        exif = image.getexif()
    except Exception:
        return {}

    if not exif:
        return {}

    summary: dict[str, str] = {}
    for tag_name, label in EXIF_DISPLAY_FIELDS:
        tag_id = EXIF_TAG_IDS.get(tag_name)
        if tag_id is None:
            continue
        value = exif.get(tag_id)
        if value in (None, ""):
            continue
        summary[label] = _format_exif_value(tag_name, value)

    gps_info = exif.get(34853)
    if gps_info:
        summary["GPS"] = "Available"
    return summary


def _encode_raw_to_avif(filename: str, file_bytes: bytes) -> ContentFile:
    exif_bytes = _extract_exif_bytes(file_bytes)
    with rawpy.imread(io.BytesIO(file_bytes)) as raw:
        rgb = raw.postprocess()

    img = Image.fromarray(rgb)
    img = downscale_if_needed(img)

    out_buf = io.BytesIO()
    save_kwargs = {"format": "AVIF", "quality": 85}
    if exif_bytes:
        save_kwargs["exif"] = exif_bytes

    try:
        img.save(out_buf, **save_kwargs)
    except Exception:
        out_buf = io.BytesIO()
        img.save(out_buf, format="AVIF", quality=85)
    out_buf.seek(0)

    new_name = f"{Path(filename).stem}.avif"
    return ContentFile(out_buf.read(), name=new_name)


def _encode_regular_image(filename: str, file_bytes: bytes) -> ContentFile:
    orig = Image.open(io.BytesIO(file_bytes))
    resized = downscale_if_needed(orig)
    if resized is orig:
        return ContentFile(file_bytes, name=os.path.basename(filename))

    out_buf = io.BytesIO()
    fmt = orig.format or "JPEG"
    save_kwargs = {"format": fmt}
    if fmt == "JPEG":
        save_kwargs["quality"] = 85
    resized.save(out_buf, **save_kwargs)
    out_buf.seek(0)
    return ContentFile(out_buf.read(), name=os.path.basename(filename))


def process_uploaded_image(filename: str, file_bytes: bytes) -> ContentFile:
    ext = Path(filename).suffix.lower()
    if ext in RAW_EXTENSIONS:
        return _encode_raw_to_avif(filename, file_bytes)
    return _encode_regular_image(filename, file_bytes)


def make_image_variant(file_bytes: bytes, file_name: str, max_dim: int, photo_id: str, suffix: str) -> tuple[str, bytes]:
    """Resize an already-processed image to at most max_dim on its longest edge.

    Returns (filename, bytes) ready to be saved to a model ImageField.
    Only downscales; images smaller than max_dim are saved as-is.
    """
    img = Image.open(io.BytesIO(file_bytes))
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    fmt, ext = _thumbnail_format_and_extension(file_name)
    out_buf = io.BytesIO()
    save_kwargs: dict = {"format": fmt}
    if fmt in {"JPEG", "AVIF"}:
        save_kwargs["quality"] = 85
    img.save(out_buf, **save_kwargs)
    out_buf.seek(0)
    return f"photo_{photo_id}_{suffix}{ext}", out_buf.read()


def make_thumbnail_from_image_file(image_file, photo_id: str) -> tuple[str, bytes]:
    img = Image.open(image_file)
    img.thumbnail((400, 800), Image.LANCZOS)

    fmt, ext = _thumbnail_format_and_extension(image_file.name)
    out_buf = io.BytesIO()
    save_kwargs = {"format": fmt}
    if fmt == "JPEG":
        save_kwargs["quality"] = 80
    try:
        img.save(out_buf, **save_kwargs)
    except Exception:
        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=80)
        ext = ".jpg"
    out_buf.seek(0)
    return f"thumb_{photo_id}{ext}", out_buf.read()
