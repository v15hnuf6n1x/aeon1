import os
from contextlib import suppress
from hashlib import md5
from aiofiles.os import path as aiopath
from langcodes import Language
import json

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.status_utils import (
    get_readable_file_size,
    get_readable_time,
)


class DefaultDict(dict):
    def __missing__(self, key):
        return "Unknown"


async def generate_caption(file, dirpath, lcaption):
    up_path = os.path.join(dirpath, file)

    try:
        result = await cmd_exec(["mediainfo", "--Output=JSON", up_path])
        if result[1]:
            LOGGER.info(f"Get Media Info: {result[1]}")

        mediainfo_result = json.loads(result[0])  # Parse JSON output
    except Exception as e:
        LOGGER.error(f"Media Info: {e}. Mostly File not found!")
        return file

    media = mediainfo_result.get("media", {})
    track = media.get("track", [])
    video_info = next((t for t in track if t["@type"] == "Video"), {})
    audio_info = [t for t in track if t["@type"] == "Audio"]
    subtitle_info = [t for t in track if t["@type"] == "Text"]

    duration = round(float(video_info.get("Duration", 0)) / 1000)
    qual = get_video_quality(video_info.get("Height"))

    lang = ", ".join(
        update_language("", audio) for audio in audio_info if audio.get("Language")
    )
    stitles = ", ".join(
        update_subtitles("", subtitle) for subtitle in subtitle_info if subtitle.get("Language")
    )

    lang = lang if lang else "Unknown"
    stitles = stitles if stitles else "Unknown"
    qual = qual if qual else "Unknown"
    md5_hex = calculate_md5(up_path)

    caption_dict = DefaultDict(
        filename=file,
        size=get_readable_file_size(await aiopath.getsize(up_path)),
        duration=get_readable_time(duration, True),
        quality=qual,
        audios=lang,
        subtitles=stitles,
        md5_hash=md5_hex,
    )

    return lcaption.format_map(caption_dict)


def get_video_quality(height):
    quality_map = {
        480: "480p",
        540: "540p",
        720: "720p",
        1080: "1080p",
        2160: "2160p",
        4320: "4320p",
        8640: "8640p",
    }
    for h, q in sorted(quality_map.items()):
        if height and int(height) <= h:
            return q
    return "Unknown"


def update_language(lang, stream):
    language_code = stream.get("Language")
    if language_code:
        with suppress(Exception):
            language_name = Language.get(language_code).display_name()
            if language_name not in lang:
                lang += f"{language_name}, "
    return lang


def update_subtitles(stitles, stream):
    subtitle_code = stream.get("Language")
    if subtitle_code:
        with suppress(Exception):
            subtitle_name = Language.get(subtitle_code).display_name()
            if subtitle_name not in stitles:
                stitles += f"{subtitle_name}, "
    return stitles


def calculate_md5(filepath):
    hash_md5 = md5()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            hash_md5.update(byte_block)
    return hash_md5.hexdigest()