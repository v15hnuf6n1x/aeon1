import contextlib
import re
from ast import literal_eval
from asyncio import create_subprocess_exec, gather, sleep
from asyncio.subprocess import PIPE
from os import cpu_count
from os import path as ospath
from time import time

from aiofiles.os import makedirs
from aioshutil import move

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.files_utils import get_path_size


async def get_media_info(path):
    """Retrieve media information using ffprobe."""
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
            ],
        )
        if res := result[1]:
            LOGGER.warning("Get Media Info: %s", res)
        fields = literal_eval(result[0]).get("format")
        if fields is None:
            LOGGER.error("Get Media Info: %s", result)
            return 0, None, None

        duration = round(float(fields.get("duration", 0)))
        tags = fields.get("tags", {})
        artist = tags.get("artist") or tags.get("ARTIST") or tags.get("Artist")
        title = tags.get("title") or tags.get("TITLE") or tags.get("Title")
        return duration, artist, title

    except Exception as e:
        LOGGER.error("Get Media Info: %s. Mostly File not found!", e)
        return 0, None, None


class FFProgress:
    """Class to track progress of FFmpeg operations."""

    def __init__(self):
        self.is_cancel = False
        self._duration = 0
        self._start_time = time()
        self._eta = 0
        self._percentage = "0%"
        self._processed_bytes = 0

    @property
    def processed_bytes(self):
        return self._processed_bytes

    @property
    def percentage(self):
        return self._percentage

    @property
    def eta(self):
        return self._eta

    @property
    def speed(self):
        elapsed = time() - self._start_time
        return self._processed_bytes / elapsed if elapsed > 0 else 0

    async def readlines(self, stream):
        """Asynchronously read lines from a stream."""
        data = bytearray()
        while not stream.at_eof():
            lines = re.split(rb"[\r\n]+", data)
            data[:] = lines.pop(-1)
            for line in lines:
                yield line
            data.extend(await stream.read(1024))

    async def update_progress(self, line, status):
        """Update progress metrics from FFmpeg output."""
        progress = dict(
            re.findall(r"(frame|fps|size|time|bitrate|speed)\s*=\s*(\S+)", line),
        )
        if not progress:
            return

        if not self._duration:
            self._duration = (await get_media_info(self.path))[0]

        try:
            hh, mm, sms = progress["time"].split(":")
            time_to_second = (int(hh) * 3600) + (int(mm) * 60) + float(sms)
            self._percentage = (
                f"{round((time_to_second / self._duration) * 100, 2)}%"
            )
        except (ValueError, KeyError):
            self._percentage = "0%"

        try:
            self._processed_bytes = int(progress["size"].rstrip("kB")) * 1024
        except ValueError:
            self._processed_bytes = 0

        with contextlib.suppress(Exception):
            elapsed = time() - self._start_time
            self._eta = (
                self._duration / float(progress["speed"].strip("x")) - elapsed
            )

    async def progress(self, status=""):
        """Track FFmpeg progress."""
        async for line in self.readlines(self.listener.subproc.stderr):
            if self.is_cancel or self.listener.subproc.returncode is not None:
                return
            if status == "direct":
                self._processed_bytes = await get_path_size(self.outfile)
                await sleep(0.5)
            else:
                await self.update_progress(line.decode("utf-8"), status)


class SampleVideo(FFProgress):
    """Class to create a sample video using FFmpeg."""

    def __init__(self, listener, duration, part_duration, gid):
        super().__init__()
        self.listener = listener
        self.path = ""
        self.name = ""
        self.outfile = ""
        self.size = 0
        self._duration = duration
        self._part_duration = part_duration
        self._gid = gid

    def _generate_segments(self, duration):
        """Generate segments for sampling."""
        segments = [(0, self._part_duration)]
        remaining_duration = duration - (self._part_duration * 2)
        parts = remaining_duration // self._part_duration
        time_interval = remaining_duration // parts
        next_segment = self._part_duration

        for _ in range(parts):
            segments.append((next_segment, next_segment + self._part_duration))
            next_segment += time_interval

        segments.append((duration - self._part_duration, duration))
        return segments

    def _build_filter_complex(self, segments):
        """Build FFmpeg filter_complex string."""
        filter_complex = ""
        for i, (start, end) in enumerate(segments):
            filter_complex += (
                f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]; "
                f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]; "
            )
        filter_complex += f"concat=n={len(segments)}:v=1:a=1[vout][aout]"
        return filter_complex

    async def create(self, video_file, on_file=False):
        """Create a sample video."""
        self.path = video_file
        dir_name, file_name = ospath.split(video_file)
        self.outfile = ospath.join(dir_name, f"SAMPLE.{file_name}")
        duration = (await get_media_info(video_file))[0]
        segments = self._generate_segments(duration)
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

        if self.listener.subproc == "cancelled":
            return False

        self.name, self.size = file_name, await get_path_size(video_file)
        self.listener.subproc = await create_subprocess_exec(*cmd, stderr=PIPE)
        _, code = await gather(self.progress(), self.listener.subproc.wait())

        if code == 0:
            if on_file:
                new_dir = ospath.splitext(video_file)[0]
                await makedirs(new_dir, exist_ok=True)
                await gather(
                    move(video_file, ospath.join(new_dir, file_name)),
                    move(self.outfile, ospath.join(new_dir, f"SAMPLE.{file_name}")),
                )
                return new_dir
            return True

        LOGGER.error(
            "Error creating sample video: %s. Path: %s",
            (await self.listener.subproc.stderr.read()).decode().strip(),
            video_file,
        )
        return False
