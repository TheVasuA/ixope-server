"""
Cleanup helpers — remove capture files and their derived artifacts
(thumbnails, transcode cache) from disk.

Used when deleting a single capture or when cascade-deleting everything that
belongs to a device.
"""
import os


def _safe_remove(path: str) -> None:
    """Remove a file if it exists, ignoring errors."""
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def remove_capture_files(file_path: str, thumbnail_path: str = "", capture_id=None) -> None:
    """Delete a capture's main file, thumbnail, and any transcode-cache files.

    The video routes cache faststart/h264 variants under a ``.cache`` folder
    next to the original file, named ``<id>_faststart.mp4`` / ``<id>_h264.mp4``.
    """
    _safe_remove(file_path)
    _safe_remove(thumbnail_path)

    if file_path and capture_id is not None:
        cache_dir = os.path.join(os.path.dirname(file_path), ".cache")
        for suffix in ("faststart", "h264"):
            _safe_remove(os.path.join(cache_dir, f"{capture_id}_{suffix}.mp4"))
