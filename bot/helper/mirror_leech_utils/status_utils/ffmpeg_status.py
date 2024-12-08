from time import time

from bot import LOGGER, subprocess_lock
from bot.helper.ext_utils.bot_utils import async_to_sync
from bot.helper.ext_utils.files_utils import get_path_size
from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class FFmpegStatus:
    def __init__(self, listener, gid, status="", obj=None):
        self.listener = listener
        self._gid = gid
        self._size = self.listener.size
        self.cstatus = status
        self._obj = obj
        self._time = time()

    def elapsed(self):
        return get_readable_time(time() - self._time)

    def processed_bytes(self):
        return get_readable_file_size(self._obj.processed_bytes)

    def gid(self):
        return self._gid

    def progress(self):
        try:
            return self._obj.percentage
        except Exception:
            try:
                progress_raw = self._obj.processed_bytes / self._obj.size * 100
            except:
                progress_raw = 0
            return f"{round(progress_raw, 2)}%"

    def speed(self):
        return f"{get_readable_file_size(self._obj.speed)}/s"

    def name(self):
        return self._obj.name if self._obj else self.listener.name

    def size(self):
        size = (
            self._obj.size
            if self._obj
            else async_to_sync(get_path_size, self.listener.dir)
        )
        return get_readable_file_size(size)

    def timeout(self):
        return get_readable_time(180 - (time() - self._time))

    def eta(self):
        try:
            return get_readable_time(self._obj.eta)
        except Exception:
            try:
                return get_readable_time(
                    (self._obj.size - self._obj.processed_bytes) / self._obj.speed,
                )
            except:
                return "-"

    def status(self):
        if self.cstatus == "Convert":
            return MirrorStatus.STATUS_CONVERT
        if self.cstatus == "Split":
            return MirrorStatus.STATUS_SPLIT
        if self.cstatus == "Sample Video":
            return MirrorStatus.STATUS_SAMVID
        return MirrorStatus.STATUS_FFMPEG

    def task(self):
        return self

    async def cancel_task(self):
        LOGGER.info(f"Cancelling {self.cstatus}: {self.listener.name}")
        self.listener.is_cancelled = True
        async with subprocess_lock:
            if (
                self.listener.subproc is not None
                and self.listener.subproc.returncode is None
            ):
                self.listener.subproc.kill()
        await self.listener.on_upload_error(f"{self.cstatus} stopped by user!")
