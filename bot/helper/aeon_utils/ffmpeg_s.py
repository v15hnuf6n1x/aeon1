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
    except Exception as e:
        LOGGER.error("Get Media Info: %s. Mostly File not found!", e)
        return 0, None, None
    fields = literal_eval(result[0]).get("format")
    if fields is None:
        LOGGER.error("Get_media_info: %s", result)
        return 0, None, None
    duration = round(float(fields.get("duration", 0)))
    tags = fields.get("tags", {})
    artist = tags.get("artist") or tags.get("ARTIST") or tags.get("Artist")
    title = tags.get("title") or tags.get("TITLE") or tags.get("Title")
    return duration, artist, title


class FFProgress:
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
        """Efficiently read lines from a stream."""
        buffer = bytearray()
        while not stream.at_eof():
            chunk = await stream.read(1024)
            if not chunk:
                break
            buffer.extend(chunk)
            *lines, buffer = buffer.split(b"\n")
            for line in lines:
                yield line.strip()

    async def progress(self, status: str = ""):
        start_time = time()
        async for line in self.readlines(self.listener.subproc.stderr):
            if (
                self.is_cancel
                or self.listener.subproc == "cancelled"
                or self.listener.subproc.returncode is not None
            ):
                return
            if status == "direct":
                self._processed_bytes = await get_path_size(self.outfile)
                await sleep(0.5)
                continue
            try:
                progress = dict(
                    re.findall(
                        r"(frame|fps|size|time|bitrate|speed)\s*=\s*(\S+)",
                        line.decode("utf-8"),
                    ),
                )
            except Exception:
                continue

            if not self._duration:
                self._duration = (await get_media_info(self.path))[0]

            time_data = progress.get("time", "0:0:0").split(":")
            hh, mm, ss = map(float, time_data) if len(time_data) == 3 else (0, 0, 0)

            time_to_second = hh * 3600 + mm * 60 + ss
            self._processed_bytes = (
                int(progress.get("size", "0kB").strip("kB")) * 1024
            )
            self._percentage = f"{(time_to_second / self._duration) * 100:.2f}%"
            with contextlib.suppress(Exception):
                self._eta = (
                    self._duration / float(progress.get("speed", "1x").strip("x"))
                ) - (time() - start_time)


class SampleVideo(FFProgress):
    def __init__(self, listener, duration, part_duration, gid):
        self.listener = listener
        self.path = ""
        self.name = ""
        self.outfile = ""
        self.size = 0
        self._duration = duration
        self._part_duration = part_duration
        self._gid = gid
        self._start_time = time()
        super().__init__()

    async def create(self, video_file: str, on_file: bool = False):
        filter_complex = ""
        self.path = video_file
        dir, name = video_file.rsplit("/", 1)
        self.outfile = ospath.join(dir, f"SAMPLE.{name}")
        duration = (await get_media_info(video_file))[0]

        # Create segment timings dynamically
        segments = [(0, self._part_duration)]
        remaining_duration = duration - (self._part_duration * 2)
        parts = max((remaining_duration // self._part_duration), 1)
        time_interval = remaining_duration // parts
        next_segment = time_interval

        for _ in range(parts):
            segments.append((next_segment, next_segment + self._part_duration))
            next_segment += time_interval
        segments.append((duration - self._part_duration, duration))

        for i, (start, end) in enumerate(segments):
            filter_complex += (
                f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]; "
                f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]; "
            )
        filter_complex += "".join(f"[v{i}][a{i}]" for i in range(len(segments)))
        filter_complex += f"concat=n={len(segments)}:v=1:a=1[vout][aout]"

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
            f"{cpu_count() // 2}",
            self.outfile,
        ]

        if self.listener.subproc == "cancelled":
            return False

        self.name, self.size = (
            ospath.basename(video_file),
            await get_path_size(video_file),
        )
        self.listener.subproc = await create_subprocess_exec(*cmd, stderr=PIPE)
        _, code = await gather(self.progress(), self.listener.subproc.wait())

        if code == -9:
            return False
        if code == 0:
            if on_file:
                new_dir, _ = ospath.splitext(video_file)
                await makedirs(new_dir, exist_ok=True)
                await gather(
                    move(video_file, ospath.join(new_dir, name)),
                    move(self.outfile, ospath.join(new_dir, f"SAMPLE.{name}")),
                )
                return new_dir
            return True

        LOGGER.error(
            "%s. Something went wrong while creating sample video, mostly file is corrupted. Path: %s",
            (await self.listener.subproc.stderr.read()).decode().strip(),
            video_file,
        )
        return video_file
