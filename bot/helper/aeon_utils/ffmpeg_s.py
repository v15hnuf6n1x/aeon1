import asyncio
import contextlib
import logging
import re
from ast import literal_eval
from dataclasses import dataclass, field
from os import cpu_count
from os import path as ospath
from time import time

import aioshutil
from aiofiles.os import makedirs

from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.files_utils import get_path_size

LOGGER = logging.getLogger(__name__)


class MediaInfoError(Exception):
    """Custom exception for media info extraction errors."""


async def extract_media_info(path: str) -> tuple[int, str | None, str | None]:
    """
    Extract media information using ffprobe.

    Args:
        path (str): Path to the media file.

    Returns:
        Tuple containing duration, artist, and title.

    Raises:
        MediaInfoError: If media info cannot be extracted.
    """
    try:
        result = await cmd_exec(
            [
                "ffprobe",
                "-hide_banner",
                "-loglevel",
                "error",
                "-print_format",
                "json",
                "-show_format",
                path,
            ]
        )

        if result[1]:
            LOGGER.warning(f"Get Media Info: {result[1]}")

        media_data = literal_eval(result[0])
        media_format = media_data.get("format")

        if media_format is None:
            raise MediaInfoError(f"No format information found: {result}")

        duration = round(float(media_format.get("duration", 0)))
        tags = media_format.get("tags", {})

        artist = next(
            (
                tags.get(key)
                for key in ["artist", "ARTIST", "Artist"]
                if tags.get(key)
            ),
            None,
        )
        title = next(
            (tags.get(key) for key in ["title", "TITLE", "Title"] if tags.get(key)),
            None,
        )

        return duration, artist, title

    except Exception as e:
        LOGGER.error(f"Get Media Info Error: {e}")
        raise MediaInfoError(f"Failed to extract media info: {e}")


@dataclass
class ProgressTracker:
    """
    Track progress of media processing with various metrics.
    """

    _duration: int = 0
    _start_time: float = field(default_factory=time)
    _eta: float = 0
    _percentage: str = "0%"
    _processed_bytes: int = 0
    is_cancelled: bool = False

    @property
    def processed_bytes(self) -> int:
        return self._processed_bytes

    @property
    def percentage(self) -> str:
        return self._percentage

    @property
    def eta(self) -> float:
        return self._eta

    @property
    def speed(self) -> float:
        return self._processed_bytes / (time() - self._start_time)

    async def track_progress(
        self,
        stream,
        path: str,
        subproc,
        start_time: float,
    ) -> None:
        """
        Asynchronously track processing progress.

        Args:
            stream: Subprocess stderr stream
            path (str): Path to the media file
            subproc: Subprocess object
            start_time (float): Processing start time
        """
        data = bytearray()
        while not stream.at_eof():
            if (
                self.is_cancelled
                or subproc == "cancelled"
                or subproc.returncode is not None
            ):
                return

            lines = re.split(rb"[\r\n]+", data)
            data[:] = lines.pop(-1)

            for line in lines:
                progress = dict(
                    re.findall(
                        r"(size|time|speed)\s*\=\s*(\S+)",
                        line.decode("utf-8"),
                    ),
                )

                if progress:
                    await self._update_progress(
                        progress,
                        path,
                        start_time,
                    )

            data.extend(await stream.read(1024))

    async def _update_progress(
        self,
        progress: dict,
        path: str,
        start_time: float,
    ) -> None:
        """
        Update progress metrics.

        Args:
            progress (dict): Processing progress metrics
            path (str): Path to the media file
            start_time (float): Processing start time
        """
        # Lazy load duration if not set
        if not self._duration:
            self._duration = (await extract_media_info(path))[0]

        # Parse time components
        try:
            hh, mm, sms = progress.get("time", "0:0:0").split(":")
            time_to_second = (int(hh) * 3600) + (int(mm) * 60) + float(sms)
        except ValueError:
            time_to_second = 0

        # Update processed bytes
        try:
            self._processed_bytes = (
                int(progress.get("size", "0").rstrip("kB")) * 1024
            )
        except ValueError:
            self._processed_bytes = 0

        # Calculate percentage
        try:
            self._percentage = (
                f"{round((time_to_second / self._duration) * 100, 2)}%"
            )
        except (ValueError, ZeroDivisionError):
            self._percentage = "0%"

        # Calculate ETA
        with contextlib.suppress(Exception):
            speed = float(progress.get("speed", "1").strip("x"))
            self._eta = (self._duration / speed) - (time() - start_time)


class SampleVideoCreator:
    """
    Create sample videos with configurable parameters.
    """

    def __init__(
        self,
        listener,
        duration: int,
        part_duration: int,
        gid: str,
    ):
        self.listener = listener
        self.path = ""
        self.name = ""
        self.outfile = ""
        self.size = 0
        self._duration = duration
        self._part_duration = part_duration
        self._gid = gid
        self._progress_tracker = ProgressTracker()

    async def create_sample(
        self,
        video_file: str,
        on_file: bool = False,
    ) -> str | bool:
        """
        Create a sample video from the input file.

        Args:
            video_file (str): Path to the source video
            on_file (bool, optional): Whether to process in-place. Defaults to False.

        Returns:
            Union[str, bool]: New directory path or success status
        """
        self.path = video_file
        dir_path, name = video_file.rsplit("/", 1)
        self.outfile = ospath.join(dir_path, f"SAMPLE.{name}")

        # Compute video segments
        segments = await self._compute_segments(video_file)

        # Build complex filter for video processing
        filter_complex = self._build_filter_complex(segments)

        cmd = [
            "xtra",
            "-hide_banner",
            "-i",
            video_file,
            "-filter_complex",
            filter_complex,
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-threads",
            str(cpu_count() // 2),
            self.outfile,
        ]

        # Early cancellation check
        if self.listener.subproc == "cancelled":
            return False

        # Prepare metadata
        self.name = ospath.basename(video_file)
        self.size = await get_path_size(video_file)

        # Execute processing
        self.listener.subproc = await asyncio.create_subprocess_exec(
            *cmd, stderr=asyncio.subprocess.PIPE
        )

        _, code = await asyncio.gather(
            self._progress_tracker.track_progress(
                self.listener.subproc.stderr,
                self.path,
                self.listener.subproc,
                time(),
            ),
            self.listener.subproc.wait(),
        )

        # Process results
        return await self._handle_result(code, video_file, name, on_file)

    async def _compute_segments(self, video_file: str) -> list[tuple[float, float]]:
        """
        Compute video segments for sampling.

        Args:
            video_file (str): Path to the source video

        Returns:
            List of segment tuples (start_time, end_time)
        """
        # Correctly await and extract duration
        duration, _, _ = await extract_media_info(video_file)
        segments = [(0, self._part_duration)]

        remaining_duration = duration - (self._part_duration * 2)
        parts = (self._duration - (self._part_duration * 2)) // self._part_duration
        time_interval = remaining_duration // parts

        next_segment = time_interval
        for _ in range(parts):
            segments.append((next_segment, next_segment + self._part_duration))
            next_segment += time_interval

        segments.append((duration - self._part_duration, duration))
        return segments

    def _build_filter_complex(self, segments: list[tuple[float, float]]) -> str:
        """
        Build complex filter for ffmpeg processing.

        Args:
            segments (List[Tuple[float, float]]): Video segments

        Returns:
            str: Complex filter string
        """
        filter_complex = ""
        for i, (start, end) in enumerate(segments):
            filter_complex += (
                f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]; "
                f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]; "
            )

        filter_complex += "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
        filter_complex += f"concat=n={len(segments)}:v=1:a=1[vout][aout]"

        return filter_complex

    async def _handle_result(
        self,
        code: int,
        video_file: str,
        name: str,
        on_file: bool,
    ) -> str | bool:
        """
        Handle processing result.

        Args:
            code (int): Processing return code
            video_file (str): Path to source video
            name (str): Video file name
            on_file (bool): Whether processing was in-place

        Returns:
            Union[str, bool]: New directory or success status
        """
        if code == -9:
            return False

        if code == 0:
            if on_file:
                new_dir, _ = ospath.splitext(video_file)
                await makedirs(new_dir, exist_ok=True)
                await asyncio.gather(
                    aioshutil.move(video_file, ospath.join(new_dir, name)),
                    aioshutil.move(
                        self.outfile,
                        ospath.join(new_dir, f"SAMPLE.{name}"),
                    ),
                )
                return new_dir
            return True

        LOGGER.error(
            f"Sample video creation failed. "
            f"Error: {await self.listener.subproc.stderr.read().decode().strip()}. "
            f"Path: {video_file}",
        )
        return video_file
