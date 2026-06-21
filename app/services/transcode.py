"""
Video transcoding service — ensures uploaded videos are browser-compatible (H.264/AAC in MP4).

Uses ffprobe to check codec and ffmpeg to transcode if needed.
Falls back gracefully if ffmpeg is not installed.
"""
import asyncio
import os
import shutil
import logging

logger = logging.getLogger(__name__)


async def ensure_browser_compatible(video_path: str) -> str:
    """
    Check if video uses a browser-compatible codec (H.264).
    If not, transcode to H.264. Returns path to the playable file.

    Returns the original path if already compatible or if ffmpeg is unavailable.
    """
    if not os.path.exists(video_path):
        return video_path

    # Check if ffmpeg/ffprobe are available
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        logger.warning("ffmpeg/ffprobe not found — skipping transcode")
        return video_path

    # Check current codec
    codec = await _get_video_codec(video_path)
    if codec is None:
        return video_path

    # H.264 codec names in ffprobe output
    browser_compatible_codecs = {"h264", "h265", "hevc", "vp8", "vp9", "av1"}

    if codec.lower() in browser_compatible_codecs:
        logger.info(f"Video already browser-compatible ({codec}): {video_path}")
        return video_path

    # Transcode to H.264
    logger.info(f"Transcoding {codec} → H.264: {video_path}")
    return await _transcode_to_h264(video_path)


async def _get_video_codec(video_path: str) -> str | None:
    """Get the video codec name using ffprobe."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_name",
            "-of", "csv=p=0",
            video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        codec = stdout.decode().strip()
        return codec if codec else None
    except Exception as e:
        logger.error(f"ffprobe failed: {e}")
        return None


async def _transcode_to_h264(video_path: str) -> str:
    """Transcode video to H.264/AAC in MP4 container. Replaces original file."""
    base, ext = os.path.splitext(video_path)
    temp_output = f"{base}_h264.mp4"

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-i", video_path,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-movflags", "+faststart",  # Enable progressive download
            temp_output,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode != 0:
            logger.error(f"ffmpeg transcode failed: {stderr.decode()[:500]}")
            # Clean up failed output
            if os.path.exists(temp_output):
                os.remove(temp_output)
            return video_path

        # Replace original with transcoded version
        os.remove(video_path)
        final_path = f"{base}.mp4"
        os.rename(temp_output, final_path)
        logger.info(f"Transcoded successfully: {final_path}")
        return final_path

    except asyncio.TimeoutError:
        logger.error("ffmpeg transcode timed out (120s)")
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return video_path
    except Exception as e:
        logger.error(f"Transcode error: {e}")
        if os.path.exists(temp_output):
            os.remove(temp_output)
        return video_path
