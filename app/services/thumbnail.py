"""
Thumbnail generation service.
Creates optimized thumbnails for images and video poster frames.
"""
import os
from PIL import Image

THUMB_SIZE = (300, 300)
THUMB_QUALITY = 80


def generate_image_thumbnail(source_path: str, upload_dir: str) -> str | None:
    """Generate a thumbnail for an uploaded image. Returns thumbnail path."""
    try:
        thumb_dir = os.path.join(upload_dir, "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)

        filename = os.path.basename(source_path)
        name, _ = os.path.splitext(filename)
        thumb_filename = f"thumb_{name}.jpg"
        thumb_path = os.path.join(thumb_dir, thumb_filename)

        with Image.open(source_path) as img:
            # Convert to RGB if needed (handles PNG with alpha)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Create thumbnail maintaining aspect ratio
            img.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)
            img.save(thumb_path, "JPEG", quality=THUMB_QUALITY, optimize=True)

        return thumb_path
    except Exception as e:
        print(f"Thumbnail generation failed: {e}")
        return None


def generate_video_thumbnail(source_path: str, upload_dir: str) -> str | None:
    """
    Generate a poster frame thumbnail from a video.
    Requires ffmpeg or falls back to a placeholder.
    """
    try:
        import subprocess

        thumb_dir = os.path.join(upload_dir, "thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)

        filename = os.path.basename(source_path)
        name, _ = os.path.splitext(filename)
        thumb_filename = f"thumb_{name}.jpg"
        thumb_path = os.path.join(thumb_dir, thumb_filename)

        # Extract frame at 1 second using ffmpeg
        result = subprocess.run(
            [
                "ffmpeg", "-i", source_path,
                "-ss", "00:00:01",
                "-vframes", "1",
                "-vf", f"scale={THUMB_SIZE[0]}:-1",
                "-q:v", "3",
                "-y", thumb_path,
            ],
            capture_output=True,
            timeout=10,
        )

        if result.returncode == 0 and os.path.exists(thumb_path):
            return thumb_path

        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # ffmpeg not available
        return None
    except Exception as e:
        print(f"Video thumbnail failed: {e}")
        return None
