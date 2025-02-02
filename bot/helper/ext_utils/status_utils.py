import contextlib
from asyncio import iscoroutinefunction
from html import escape
from time import time

from psutil import cpu_percent, disk_usage, virtual_memory

from bot import bot_start_time, status_dict, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.helper.telegram_helper.button_build import ButtonMaker

from .bot_utils import sync_to_async

SIZE_UNITS = ["B", "KB", "MB", "GB", "TB", "PB"]


class MirrorStatus:
    STATUS_UPLOAD = "Upload"
    STATUS_DOWNLOAD = "Download"
    STATUS_CLONE = "Clone"
    STATUS_QUEUEDL = "QueueDl"
    STATUS_QUEUEUP = "QueueUp"
    STATUS_PAUSED = "Pause"
    STATUS_ARCHIVE = "Archive"
    STATUS_EXTRACT = "Extract"
    STATUS_SPLIT = "Split"
    STATUS_CHECK = "CheckUp"
    STATUS_SEED = "Seed"
    STATUS_SAMVID = "SamVid"
    STATUS_CONVERT = "Convert"
    STATUS_FFMPEG = "FFmpeg"
    STATUS_METADATA = "Metadata"
    STATUS_WATERMARK = "Watermark"
    STATUS_ETHUMB = "Embed Thumb"


STATUSES = {
    "ALL": "All",
    "DL": MirrorStatus.STATUS_DOWNLOAD,
    "UP": MirrorStatus.STATUS_UPLOAD,
    "QD": MirrorStatus.STATUS_QUEUEDL,
    "QU": MirrorStatus.STATUS_QUEUEUP,
    "AR": MirrorStatus.STATUS_ARCHIVE,
    "EX": MirrorStatus.STATUS_EXTRACT,
    "SD": MirrorStatus.STATUS_SEED,
    "CL": MirrorStatus.STATUS_CLONE,
    "CM": MirrorStatus.STATUS_CONVERT,
    "SP": MirrorStatus.STATUS_SPLIT,
    "SV": MirrorStatus.STATUS_SAMVID,
    "FF": MirrorStatus.STATUS_FFMPEG,
    "PA": MirrorStatus.STATUS_PAUSED,
    "CK": MirrorStatus.STATUS_CHECK,
}


async def get_task_by_gid(gid: str):
    async with task_dict_lock:
        for task in task_dict.values():
            if hasattr(task, "seeding"):
                await sync_to_async(task.update)
            if task.gid().startswith(gid):
                return task
        return None


def get_specific_tasks(status, user_id):
    if status == "All":
        if user_id:
            return [
                tk for tk in task_dict.values() if tk.listener.user_id == user_id
            ]
        return list(task_dict.values())
    if user_id:
        return [
            tk
            for tk in task_dict.values()
            if tk.listener.user_id == user_id
            and (
                ((st := tk.status()) and st == status)
                or (
                    status == MirrorStatus.STATUS_DOWNLOAD
                    and st not in STATUSES.values()
                )
            )
        ]
    return [
        tk
        for tk in task_dict.values()
        if ((st := tk.status()) and st == status)
        or (status == MirrorStatus.STATUS_DOWNLOAD and st not in STATUSES.values())
    ]


async def get_all_tasks(req_status: str, user_id):
    async with task_dict_lock:
        return await sync_to_async(get_specific_tasks, req_status, user_id)


def get_readable_file_size(size_in_bytes):
    if not size_in_bytes:
        return "0B"

    index = 0
    while size_in_bytes >= 1024 and index < len(SIZE_UNITS) - 1:
        size_in_bytes /= 1024
        index += 1

    return f"{size_in_bytes:.2f}{SIZE_UNITS[index]}"


def get_readable_time(seconds, full_time=False):
    periods = [
        ("millennium", 31536000000),
        ("century", 3153600000),
        ("decade", 315360000),
        ("year", 31536000),
        ("month", 2592000),
        ("week", 604800),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
    ]
    result = ""
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            plural_suffix = "s" if period_value > 1 else ""
            result += f"{int(period_value)} {period_name}{plural_suffix} "
            if not full_time:
                break
    return result.strip()


def time_to_seconds(time_duration):
    try:
        parts = time_duration.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(float, parts)
        elif len(parts) == 2:
            hours = 0
            minutes, seconds = map(float, parts)
        elif len(parts) == 1:
            hours = 0
            minutes = 0
            seconds = float(parts[0])
        else:
            return 0
        return hours * 3600 + minutes * 60 + seconds
    except Exception:
        return 0


def speed_string_to_bytes(size_text: str):
    size = 0
    size_text = size_text.lower()
    if "k" in size_text:
        size += float(size_text.split("k")[0]) * 1024
    elif "m" in size_text:
        size += float(size_text.split("m")[0]) * 1048576
    elif "g" in size_text:
        size += float(size_text.split("g")[0]) * 1073741824
    elif "t" in size_text:
        size += float(size_text.split("t")[0]) * 1099511627776
    elif "b" in size_text:
        size += float(size_text.split("b")[0])
    return size


def get_progress_bar_string(pct):
    if isinstance(pct, str):
        pct = float(pct.strip("%"))
    p = min(max(pct, 0), 100)
    c_full = int((p + 5) // 10)
    p_str = "●" * c_full
    p_str += "○" * (10 - c_full)
    return p_str


def source(self):
    return (
        sender_chat.title
        if (sender_chat := self.message.sender_chat)
        else self.message.from_user.username or self.message.from_user.id
    )


async def get_readable_message(sid, is_user, page_no=1, status="All", page_step=1):
    msg = ""
    button = None

    tasks = await sync_to_async(get_specific_tasks, status, sid if is_user else None)

    STATUS_LIMIT = 4
    tasks_no = len(tasks)
    pages = (max(tasks_no, 1) + STATUS_LIMIT - 1) // STATUS_LIMIT
    if page_no > pages:
        page_no = (page_no - 1) % pages + 1
        status_dict[sid]["page_no"] = page_no
    elif page_no < 1:
        page_no = pages - (abs(page_no) % pages)
        status_dict[sid]["page_no"] = page_no
    start_position = (page_no - 1) * STATUS_LIMIT

    for index, task in enumerate(
        tasks[start_position : STATUS_LIMIT + start_position],
        start=1,
    ):
        tstatus = await sync_to_async(task.status) if status == "All" else status
        if task.listener.is_super_chat:
            msg += f"<b>{index + start_position}. <a href='{task.listener.message.link}'>{tstatus}</a>: </b>"
        else:
            msg += f"<b>{index + start_position}. {tstatus}: </b>"
        msg += f"<code>{escape(f'{task.name()}')}</code>"
        if task.listener.subname:
            msg += f"\n<i>{task.listener.subname}</i>"
        msg += f"\n<b>by: {source(task.listener)}</b>"
        if (
            tstatus not in [MirrorStatus.STATUS_SEED, MirrorStatus.STATUS_QUEUEUP]
            and task.listener.progress
        ):
            progress = (
                await task.progress()
                if iscoroutinefunction(task.progress)
                else task.progress()
            )
            msg += f"\n{get_progress_bar_string(progress)} {progress}"
            if task.listener.subname:
                subsize = f"/{get_readable_file_size(task.listener.subsize)}"
                ac = len(task.listener.files_to_proceed)
                count = f"({task.listener.proceed_count}/{ac or '?'})"
            else:
                subsize = ""
                count = ""
            msg += f"\n<b>🧿Processed:</b> {task.processed_bytes()}{subsize} {count}"
            msg += f"\n<b>🗂Size:</b> {task.size()}"
            msg += f"\n<b>🚀Speed:</b> {task.speed()}"
            msg += f"\n<b>⌛ETA:</b> {task.eta()}"
            if hasattr(task, "seeders_num"):
                with contextlib.suppress(Exception):
                    msg += f"\n<b>🎛Seeders:</b> {task.seeders_num()} | <b>🎛Leechers:</b> {task.leechers_num()}"
        elif tstatus == MirrorStatus.STATUS_SEED:
            msg += f"\n<b>🗂Size: </b>{task.size()}"
            msg += f"\n<b>🚀Speed: </b>{task.seed_speed()}"
            msg += f" | <b>📤Uploaded: </b>{task.uploaded_bytes()}"
            msg += f"\n<b>🔧Ratio: </b>{task.ratio()}"
            msg += f" | <b>🕰Time: </b>{task.seeding_time()}"
        else:
            msg += f"\n<b>🗂Size: </b>{task.size()}"
        msg += f"\n/stop_{task.gid()[:8]}\n\n"

    if len(msg) == 0:
        if status == "All":
            return None, None
        msg = f"b>No Active {status} Tasks!</b>\n\n"
    buttons = None
    if len(tasks) > STATUS_LIMIT:
        buttons = ButtonMaker()
        msg += f"<b>Page:</b> {page_no}/{pages} | <b>Tasks:</b> {tasks_no} | <b>Step:</b> {page_step}\n"
        buttons.data_button("<<", f"status {sid} pre", position="header")
        buttons.data_button(">>", f"status {sid} nex", position="header")
        if tasks_no > 30:
            for i in [1, 2, 4, 6, 8, 10, 15]:
                buttons.data_button(i, f"status {sid} ps {i}", position="footer")
    if status != "All" or tasks_no > 20:
        for label, status_value in list(STATUSES.items()):
            if status_value != status:
                if not buttons:
                    buttons = ButtonMaker()
                buttons.data_button(label, f"status {sid} st {status_value}")
    button = buttons.build_menu(8) if buttons else None
    msg += f"<blockquote><b>CPU:</b> {cpu_percent()}% | <b>FREE:</b> {get_readable_file_size(disk_usage(Config.DOWNLOAD_DIR).free)}</blockquote>"
    msg += f"<blockquote>\n<b>RAM:</b> {virtual_memory().percent}% | <b>UPTIME:</b> {get_readable_time(time() - bot_start_time)}</blockquote>"
    return msg, button
