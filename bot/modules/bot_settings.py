from io import BytesIO
from os import getcwd, environ
from time import time
from asyncio import (
    sleep,
    gather,
    create_subprocess_exec,
    create_subprocess_shell,
)
from functools import partial

from dotenv import load_dotenv
from aiofiles import open as aiopen
from aioshutil import rmtree
from aiofiles.os import path as aiopath
from aiofiles.os import remove, rename
from pyrogram.filters import regex, create, command
from pyrogram.handlers import MessageHandler, CallbackQueryHandler

from bot import (
    LOGGER,
    MAX_SPLIT_SIZE,
    IS_PREMIUM_USER,
    bot,
    aria2,
    intervals,
    task_dict,
    user_data,
    drives_ids,
    index_urls,
    config_dict,
    drives_names,
    aria2_options,
    global_extension_filter,
)
from bot.helper.ext_utils.bot_utils import SetInterval, new_task, sync_to_async
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.task_manager import start_from_queued
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    send_file,
    edit_message,
    send_message,
    delete_message,
    update_status_message,
)
from bot.helper.mirror_leech_utils.rclone_utils.serve import rclone_serve_booter

from .rss import add_job
from .torrent_search import initiate_search_tools

start = 0
state = "view"
handler_dict = {}
DEFAULT_VALUES = {
    "DOWNLOAD_DIR": "/usr/src/app/downloads/",
    "LEECH_SPLIT_SIZE": MAX_SPLIT_SIZE,
    "RSS_DELAY": 600,
    "STATUS_UPDATE_INTERVAL": 15,
    "SEARCH_LIMIT": 0,
    "UPSTREAM_BRANCH": "master",
    "DEFAULT_UPLOAD": "gd",
}


async def get_buttons(key=None, edit_type=None):
    buttons = ButtonMaker()
    if key is None:
        buttons.data_button("Config Variables", "botset var")
        buttons.data_button("Private Files", "botset private")
        buttons.data_button("Close", "botset close")
        msg = "Bot Settings:"
    elif edit_type is not None:
        if edit_type == "botvar":
            msg = ""
            buttons.data_button("Back", "botset var")
            if key not in ["TELEGRAM_HASH", "TELEGRAM_API", "OWNER_ID", "BOT_TOKEN"]:
                buttons.data_button("Default", f"botset resetvar {key}")
            buttons.data_button("Close", "botset close")
            if key in [
                "SUDO_USERS",
                "CMD_SUFFIX",
                "OWNER_ID",
                "USER_SESSION_STRING",
                "TELEGRAM_HASH",
                "TELEGRAM_API",
                "AUTHORIZED_CHATS",
                "BOT_TOKEN",
                "DOWNLOAD_DIR",
            ]:
                msg += "Restart required for this edit to take effect!\n\n"
            msg += f"Send a valid value for {key}. Current value is '{config_dict[key]}'. Timeout: 60 sec"
    elif key == "var":
        for k in list(config_dict.keys())[start : 10 + start]:
            buttons.data_button(k, f"botset botvar {k}")
        if state == "view":
            buttons.data_button("Edit", "botset edit var")
        else:
            buttons.data_button("View", "botset view var")
        buttons.data_button("Back", "botset back")
        buttons.data_button("Close", "botset close")
        for x in range(0, len(config_dict), 10):
            buttons.data_button(
                f"{int(x / 10)}", f"botset start var {x}", position="footer"
            )
        msg = f"Config Variables | Page: {int(start / 10)} | State: {state}"
    elif key == "private":
        buttons.data_button("Back", "botset back")
        buttons.data_button("Close", "botset close")
        msg = """Send private file: config.env, token.pickle, rclone.conf, accounts.zip, list_drives.txt, cookies.txt, .netrc or any other private file!
To delete private file send only the file name as text message.
Note: Changing .netrc will not take effect for aria2c until restart.
Timeout: 60 sec"""
    elif key == "aria":
        for k in list(aria2_options.keys())[start : 10 + start]:
            buttons.data_button(k, f"botset ariavar {k}")
        if state == "view":
            buttons.data_button("Edit", "botset edit aria")
        else:
            buttons.data_button("View", "botset view aria")
        buttons.data_button("Add new key", "botset ariavar newkey")
        buttons.data_button("Back", "botset back")
        buttons.data_button("Close", "botset close")
        for x in range(0, len(aria2_options), 10):
            buttons.data_button(
                f"{int(x / 10)}", f"botset start aria {x}", position="footer"
            )
        msg = f"Aria2c Options | Page: {int(start / 10)} | State: {state}"

    button = buttons.build_menu(1) if key is None else buttons.build_menu(2)
    return msg, button


async def update_buttons(message, key=None, edit_type=None):
    msg, button = await get_buttons(key, edit_type)
    await edit_message(message, msg, button)


@new_task
async def edit_variable(_, message, pre_message, key):
    handler_dict[message.chat.id] = False
    value = message.text
    if value.lower() == "true":
        value = True
    elif value.lower() == "false":
        value = False
        if key == "INCOMPLETE_TASK_NOTIFIER" and config_dict["DATABASE_URL"]:
            await database.trunc_table("tasks")
    elif key == "DOWNLOAD_DIR":
        if not value.endswith("/"):
            value += "/"
    elif key == "STATUS_UPDATE_INTERVAL":
        value = int(value)
        if len(task_dict) != 0 and (st := intervals["status"]):
            for cid, intvl in list(st.items()):
                intvl.cancel()
                intervals["status"][cid] = SetInterval(
                    value, update_status_message, cid
                )
    elif key == "TORRENT_TIMEOUT":
        value = int(value)
        downloads = await sync_to_async(aria2.get_downloads)
        for download in downloads:
            if not download.is_complete:
                try:
                    await sync_to_async(
                        aria2.client.change_option,
                        download.gid,
                        {"bt-stop-timeout": f"{value}"},
                    )
                except Exception as e:
                    LOGGER.error(e)
        aria2_options["bt-stop-timeout"] = f"{value}"
    elif key == "LEECH_SPLIT_SIZE":
        value = min(int(value), MAX_SPLIT_SIZE)
    elif key == "BASE_URL_PORT":
        value = int(value)
        if config_dict["BASE_URL"]:
            await (
                await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
            ).wait()
            await create_subprocess_shell(
                f"gunicorn web.wserver:app --bind 0.0.0.0:{value} --worker-class gevent"
            )
    elif key == "EXTENSION_FILTER":
        fx = value.split()
        global_extension_filter.clear()
        global_extension_filter.extend(["aria2", "!qB"])
        for x in fx:
            x = x.lstrip(".")
            global_extension_filter.append(x.strip().lower())
    elif key == "GDRIVE_ID":
        if drives_names and drives_names[0] == "Main":
            drives_ids[0] = value
        else:
            drives_ids.insert(0, value)
    elif key == "INDEX_URL":
        if drives_names and drives_names[0] == "Main":
            index_urls[0] = value
        else:
            index_urls.insert(0, value)
    elif value.isdigit():
        value = int(value)
    elif value.startswith("[") and value.endswith("]"):
        value = eval(value)
    config_dict[key] = value
    await update_buttons(pre_message, "var")
    await delete_message(message)
    if key == "DATABASE_URL":
        await database.connect()
    if config_dict["DATABASE_URL"]:
        await database.update_config({key: value})
    if key in ["SEARCH_PLUGINS", "SEARCH_API_LINK"]:
        await initiate_search_tools()
    elif key in ["QUEUE_ALL", "QUEUE_DOWNLOAD", "QUEUE_UPLOAD"]:
        await start_from_queued()
    elif key in [
        "RCLONE_SERVE_URL",
        "RCLONE_SERVE_PORT",
        "RCLONE_SERVE_USER",
        "RCLONE_SERVE_PASS",
    ]:
        await rclone_serve_booter()
    elif key == "RSS_DELAY":
        add_job()


@new_task
async def update_private_file(_, message, pre_message):
    handler_dict[message.chat.id] = False
    if not message.media and (file_name := message.text):
        fn = file_name.rsplit(".zip", 1)[0]
        if await aiopath.isfile(fn) and file_name != "config.env":
            await remove(fn)
        if fn == "accounts":
            if await aiopath.exists("accounts"):
                await rmtree("accounts", ignore_errors=True)
            if await aiopath.exists("rclone_sa"):
                await rmtree("rclone_sa", ignore_errors=True)
            config_dict["USE_SERVICE_ACCOUNTS"] = False
            if config_dict["DATABASE_URL"]:
                await database.update_config({"USE_SERVICE_ACCOUNTS": False})
        elif file_name in [".netrc", "netrc"]:
            await (await create_subprocess_exec("touch", ".netrc")).wait()
            await (await create_subprocess_exec("chmod", "600", ".netrc")).wait()
            await (
                await create_subprocess_exec("cp", ".netrc", "/root/.netrc")
            ).wait()
        await delete_message(message)
    elif doc := message.document:
        file_name = doc.file_name
        await message.download(file_name=f"{getcwd()}/{file_name}")
        if file_name == "accounts.zip":
            if await aiopath.exists("accounts"):
                await rmtree("accounts", ignore_errors=True)
            if await aiopath.exists("rclone_sa"):
                await rmtree("rclone_sa", ignore_errors=True)
            await (
                await create_subprocess_exec(
                    "7z", "x", "-o.", "-aoa", "accounts.zip", "accounts/*.json"
                )
            ).wait()
            await (
                await create_subprocess_exec("chmod", "-R", "777", "accounts")
            ).wait()
        elif file_name == "list_drives.txt":
            drives_ids.clear()
            drives_names.clear()
            index_urls.clear()
            if GDRIVE_ID := config_dict["GDRIVE_ID"]:
                drives_names.append("Main")
                drives_ids.append(GDRIVE_ID)
                index_urls.append(config_dict["INDEX_URL"])
            async with aiopen("list_drives.txt", "r+") as f:
                lines = await f.readlines()
                for line in lines:
                    temp = line.strip().split()
                    drives_ids.append(temp[1])
                    drives_names.append(temp[0].replace("_", " "))
                    if len(temp) > 2:
                        index_urls.append(temp[2])
                    else:
                        index_urls.append("")
        elif file_name in [".netrc", "netrc"]:
            if file_name == "netrc":
                await rename("netrc", ".netrc")
                file_name = ".netrc"
            await (await create_subprocess_exec("chmod", "600", ".netrc")).wait()
            await (
                await create_subprocess_exec("cp", ".netrc", "/root/.netrc")
            ).wait()
        elif file_name == "config.env":
            load_dotenv("config.env", override=True)
            await load_config()
        if "@github.com" in config_dict["UPSTREAM_REPO"]:
            buttons = ButtonMaker()
            msg = "Push to UPSTREAM_REPO ?"
            buttons.data_button("Yes!", f"botset push {file_name}")
            buttons.data_button("No", "botset close")
            await send_message(message, msg, buttons.build_menu(2))
        else:
            await delete_message(message)
    if file_name == "rclone.conf":
        await rclone_serve_booter()
    await update_buttons(pre_message)
    if config_dict["DATABASE_URL"]:
        await database.update_private_file(file_name)
    if await aiopath.exists("accounts.zip"):
        await remove("accounts.zip")


async def event_handler(client, query, pfunc, rfunc, document=False):
    chat_id = query.message.chat.id
    handler_dict[chat_id] = True
    start_time = time()

    async def event_filter(_, __, event):
        user = event.from_user or event.sender_chat
        return bool(
            user.id == query.from_user.id
            and event.chat.id == chat_id
            and (event.text or (event.document and document))
        )

    handler = client.add_handler(
        MessageHandler(pfunc, filters=create(event_filter)), group=-1
    )
    while handler_dict[chat_id]:
        await sleep(0.5)
        if time() - start_time > 60:
            handler_dict[chat_id] = False
            await rfunc()
    client.remove_handler(*handler)


@new_task
async def edit_bot_settings(client, query):
    data = query.data.split()
    message = query.message
    handler_dict[message.chat.id] = False
    if data[1] == "close":
        await query.answer()
        await delete_message(message.reply_to_message)
        await delete_message(message)
    elif data[1] == "back":
        await query.answer()
        globals()["start"] = 0
        await update_buttons(message, None)
    elif data[1] in ["var"]:
        await query.answer()
        await update_buttons(message, data[1])
    elif data[1] == "resetvar":
        await query.answer()
        value = ""
        if data[2] in DEFAULT_VALUES:
            value = DEFAULT_VALUES[data[2]]
            if (
                data[2] == "STATUS_UPDATE_INTERVAL"
                and len(task_dict) != 0
                and (st := intervals["status"])
            ):
                for key, intvl in list(st.items()):
                    intvl.cancel()
                    intervals["status"][key] = SetInterval(
                        value, update_status_message, key
                    )
        elif data[2] == "EXTENSION_FILTER":
            global_extension_filter.clear()
            global_extension_filter.extend(["aria2", "!qB"])
        elif data[2] == "TORRENT_TIMEOUT":
            downloads = await sync_to_async(aria2.get_downloads)
            for download in downloads:
                if not download.is_complete:
                    try:
                        await sync_to_async(
                            aria2.client.change_option,
                            download.gid,
                            {"bt-stop-timeout": "0"},
                        )
                    except Exception as e:
                        LOGGER.error(e)
            aria2_options["bt-stop-timeout"] = "0"
            if config_dict["DATABASE_URL"]:
                await database.update_aria2("bt-stop-timeout", "0")
        elif data[2] == "BASE_URL":
            await (
                await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
            ).wait()
        elif data[2] == "BASE_URL_PORT":
            value = 80
            if config_dict["BASE_URL"]:
                await (
                    await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")
                ).wait()
                await create_subprocess_shell(
                    "gunicorn web.wserver:app --bind 0.0.0.0:80 --worker-class gevent"
                )
        elif data[2] == "GDRIVE_ID":
            if drives_names and drives_names[0] == "Main":
                drives_names.pop(0)
                drives_ids.pop(0)
                index_urls.pop(0)
        elif data[2] == "INDEX_URL":
            if drives_names and drives_names[0] == "Main":
                index_urls[0] = ""
        elif data[2] == "INCOMPLETE_TASK_NOTIFIER" and config_dict["DATABASE_URL"]:
            await database.trunc_table("tasks")
        config_dict[data[2]] = value
        await update_buttons(message, "var")
        if data[2] == "DATABASE_URL":
            await database.disconnect()
        if config_dict["DATABASE_URL"]:
            await database.update_config({data[2]: value})
        if data[2] in ["SEARCH_PLUGINS", "SEARCH_API_LINK"]:
            await initiate_search_tools()
        elif data[2] in ["QUEUE_ALL", "QUEUE_DOWNLOAD", "QUEUE_UPLOAD"]:
            await start_from_queued()
        elif data[2] in [
            "RCLONE_SERVE_URL",
            "RCLONE_SERVE_PORT",
            "RCLONE_SERVE_USER",
            "RCLONE_SERVE_PASS",
        ]:
            await rclone_serve_booter()
    elif data[1] == "private":
        await query.answer()
        await update_buttons(message, data[1])
        pfunc = partial(update_private_file, pre_message=message)
        rfunc = partial(update_buttons, message)
        await event_handler(client, query, pfunc, rfunc, True)
    elif data[1] == "botvar" and state == "edit":
        await query.answer()
        await update_buttons(message, data[2], data[1])
        pfunc = partial(edit_variable, pre_message=message, key=data[2])
        rfunc = partial(update_buttons, message, "var")
        await event_handler(client, query, pfunc, rfunc)
    elif data[1] == "botvar" and state == "view":
        value = f"{config_dict[data[2]]}"
        if len(value) > 200:
            await query.answer()
            with BytesIO(str.encode(value)) as out_file:
                out_file.name = f"{data[2]}.txt"
                await send_file(message, out_file)
            return
        if value == "":
            value = None
        await query.answer(f"{value}", show_alert=True)
    elif data[1] == "edit":
        await query.answer()
        globals()["state"] = "edit"
        await update_buttons(message, data[2])
    elif data[1] == "view":
        await query.answer()
        globals()["state"] = "view"
        await update_buttons(message, data[2])
    elif data[1] == "start":
        await query.answer()
        if start != int(data[3]):
            globals()["start"] = int(data[3])
            await update_buttons(message, data[2])
    elif data[1] == "push":
        await query.answer()
        filename = data[2].rsplit(".zip", 1)[0]
        if await aiopath.exists(filename):
            await (
                await create_subprocess_shell(
                    f"git add -f {filename} \
                                                    && git commit -sm botsettings -q \
                                                    && git push origin {config_dict['UPSTREAM_BRANCH']} -qf"
                )
            ).wait()
        else:
            await (
                await create_subprocess_shell(
                    f"git rm -r --cached {filename} \
                                                    && git commit -sm botsettings -q \
                                                    && git push origin {config_dict['UPSTREAM_BRANCH']} -qf"
                )
            ).wait()
        await delete_message(message.reply_to_message)
        await delete_message(message)


@new_task
async def bot_settings(_, message):
    handler_dict[message.chat.id] = False
    msg, button = await get_buttons()
    globals()["start"] = 0
    await send_message(message, msg, button)


async def load_config():
    BOT_TOKEN = environ.get("BOT_TOKEN", "")
    if len(BOT_TOKEN) == 0:
        BOT_TOKEN = config_dict["BOT_TOKEN"]

    TELEGRAM_API = environ.get("TELEGRAM_API", "")
    if len(TELEGRAM_API) == 0:
        TELEGRAM_API = config_dict["TELEGRAM_API"]
    else:
        TELEGRAM_API = int(TELEGRAM_API)

    TELEGRAM_HASH = environ.get("TELEGRAM_HASH", "")
    if len(TELEGRAM_HASH) == 0:
        TELEGRAM_HASH = config_dict["TELEGRAM_HASH"]

    OWNER_ID = environ.get("OWNER_ID", "")
    OWNER_ID = config_dict["OWNER_ID"] if len(OWNER_ID) == 0 else int(OWNER_ID)

    DATABASE_URL = environ.get("DATABASE_URL", "")
    if len(DATABASE_URL) == 0:
        DATABASE_URL = ""

    DOWNLOAD_DIR = environ.get("DOWNLOAD_DIR", "")
    if len(DOWNLOAD_DIR) == 0:
        DOWNLOAD_DIR = "/usr/src/app/downloads/"
    elif not DOWNLOAD_DIR.endswith("/"):
        DOWNLOAD_DIR = f"{DOWNLOAD_DIR}/"

    GDRIVE_ID = environ.get("GDRIVE_ID", "")
    if len(GDRIVE_ID) == 0:
        GDRIVE_ID = ""

    RCLONE_PATH = environ.get("RCLONE_PATH", "")
    if len(RCLONE_PATH) == 0:
        RCLONE_PATH = ""

    DEFAULT_UPLOAD = environ.get("DEFAULT_UPLOAD", "")
    if DEFAULT_UPLOAD != "gd":
        DEFAULT_UPLOAD = "rc"

    RCLONE_FLAGS = environ.get("RCLONE_FLAGS", "")
    if len(RCLONE_FLAGS) == 0:
        RCLONE_FLAGS = ""

    AUTHORIZED_CHATS = environ.get("AUTHORIZED_CHATS", "")
    if len(AUTHORIZED_CHATS) != 0:
        aid = AUTHORIZED_CHATS.split()
        for id_ in aid:
            chat_id, *thread_ids = id_.split("|")
            chat_id = int(chat_id.strip())
            if thread_ids:
                thread_ids = [int(x.strip()) for x in thread_ids]
                user_data[chat_id] = {"is_auth": True, "thread_ids": thread_ids}
            else:
                user_data[chat_id] = {"is_auth": True}

    SUDO_USERS = environ.get("SUDO_USERS", "")
    if len(SUDO_USERS) != 0:
        aid = SUDO_USERS.split()
        for id_ in aid:
            user_data[int(id_.strip())] = {"is_sudo": True}

    EXTENSION_FILTER = environ.get("EXTENSION_FILTER", "")
    if len(EXTENSION_FILTER) > 0:
        fx = EXTENSION_FILTER.split()
        global_extension_filter.clear()
        global_extension_filter.extend(["aria2", "!qB"])
        for x in fx:
            if x.strip().startswith("."):
                x = x.lstrip(".")
            global_extension_filter.append(x.strip().lower())

    FILELION_API = environ.get("FILELION_API", "")
    if len(FILELION_API) == 0:
        FILELION_API = ""

    STREAMWISH_API = environ.get("STREAMWISH_API", "")
    if len(STREAMWISH_API) == 0:
        STREAMWISH_API = ""

    INDEX_URL = environ.get("INDEX_URL", "").rstrip("/")
    if len(INDEX_URL) == 0:
        INDEX_URL = ""

    SEARCH_API_LINK = environ.get("SEARCH_API_LINK", "").rstrip("/")
    if len(SEARCH_API_LINK) == 0:
        SEARCH_API_LINK = ""

    LEECH_FILENAME_PREFIX = environ.get("LEECH_FILENAME_PREFIX", "")
    if len(LEECH_FILENAME_PREFIX) == 0:
        LEECH_FILENAME_PREFIX = ""

    SEARCH_PLUGINS = environ.get("SEARCH_PLUGINS", "")
    if len(SEARCH_PLUGINS) == 0:
        SEARCH_PLUGINS = ""
    else:
        try:
            SEARCH_PLUGINS = eval(SEARCH_PLUGINS)
        except:
            LOGGER.error(f"Wrong SEARCH_PLUGINS fornat {SEARCH_PLUGINS}")
            SEARCH_PLUGINS = ""

    MAX_SPLIT_SIZE = 4194304000 if IS_PREMIUM_USER else 2097152000

    LEECH_SPLIT_SIZE = environ.get("LEECH_SPLIT_SIZE", "")
    if len(LEECH_SPLIT_SIZE) == 0 or int(LEECH_SPLIT_SIZE) > MAX_SPLIT_SIZE:
        LEECH_SPLIT_SIZE = MAX_SPLIT_SIZE
    else:
        LEECH_SPLIT_SIZE = int(LEECH_SPLIT_SIZE)

    STATUS_UPDATE_INTERVAL = environ.get("STATUS_UPDATE_INTERVAL", "")
    if len(STATUS_UPDATE_INTERVAL) == 0:
        STATUS_UPDATE_INTERVAL = 15
    else:
        STATUS_UPDATE_INTERVAL = int(STATUS_UPDATE_INTERVAL)
    if len(task_dict) != 0 and (st := intervals["status"]):
        for key, intvl in list(st.items()):
            intvl.cancel()
            intervals["status"][key] = SetInterval(
                STATUS_UPDATE_INTERVAL, update_status_message, key
            )

    YT_DLP_OPTIONS = environ.get("YT_DLP_OPTIONS", "")
    if len(YT_DLP_OPTIONS) == 0:
        YT_DLP_OPTIONS = ""

    SEARCH_LIMIT = environ.get("SEARCH_LIMIT", "")
    SEARCH_LIMIT = 0 if len(SEARCH_LIMIT) == 0 else int(SEARCH_LIMIT)

    LEECH_DUMP_CHAT = environ.get("LEECH_DUMP_CHAT", "")
    LEECH_DUMP_CHAT = "" if len(LEECH_DUMP_CHAT) == 0 else LEECH_DUMP_CHAT

    STATUS_LIMIT = environ.get("STATUS_LIMIT", "")
    STATUS_LIMIT = 4 if len(STATUS_LIMIT) == 0 else int(STATUS_LIMIT)

    RSS_CHAT = environ.get("RSS_CHAT", "")
    RSS_CHAT = "" if len(RSS_CHAT) == 0 else RSS_CHAT

    RSS_DELAY = environ.get("RSS_DELAY", "")
    RSS_DELAY = 600 if len(RSS_DELAY) == 0 else int(RSS_DELAY)

    CMD_SUFFIX = environ.get("CMD_SUFFIX", "")

    USER_SESSION_STRING = environ.get("USER_SESSION_STRING", "")

    TORRENT_TIMEOUT = environ.get("TORRENT_TIMEOUT", "")
    downloads = aria2.get_downloads()
    if len(TORRENT_TIMEOUT) == 0:
        for download in downloads:
            if not download.is_complete:
                try:
                    await sync_to_async(
                        aria2.client.change_option,
                        download.gid,
                        {"bt-stop-timeout": "0"},
                    )
                except Exception as e:
                    LOGGER.error(e)
        aria2_options["bt-stop-timeout"] = "0"
        if config_dict["DATABASE_URL"]:
            await database.update_aria2("bt-stop-timeout", "0")
        TORRENT_TIMEOUT = ""
    else:
        for download in downloads:
            if not download.is_complete:
                try:
                    await sync_to_async(
                        aria2.client.change_option,
                        download.gid,
                        {"bt-stop-timeout": TORRENT_TIMEOUT},
                    )
                except Exception as e:
                    LOGGER.error(e)
        aria2_options["bt-stop-timeout"] = TORRENT_TIMEOUT
        if config_dict["DATABASE_URL"]:
            await database.update_aria2("bt-stop-timeout", TORRENT_TIMEOUT)
        TORRENT_TIMEOUT = int(TORRENT_TIMEOUT)

    QUEUE_ALL = environ.get("QUEUE_ALL", "")
    QUEUE_ALL = "" if len(QUEUE_ALL) == 0 else int(QUEUE_ALL)

    QUEUE_DOWNLOAD = environ.get("QUEUE_DOWNLOAD", "")
    QUEUE_DOWNLOAD = "" if len(QUEUE_DOWNLOAD) == 0 else int(QUEUE_DOWNLOAD)

    QUEUE_UPLOAD = environ.get("QUEUE_UPLOAD", "")
    QUEUE_UPLOAD = "" if len(QUEUE_UPLOAD) == 0 else int(QUEUE_UPLOAD)

    INCOMPLETE_TASK_NOTIFIER = environ.get("INCOMPLETE_TASK_NOTIFIER", "")
    INCOMPLETE_TASK_NOTIFIER = INCOMPLETE_TASK_NOTIFIER.lower() == "true"
    if not INCOMPLETE_TASK_NOTIFIER and config_dict["DATABASE_URL"]:
        await database.trunc_table("tasks")

    STOP_DUPLICATE = environ.get("STOP_DUPLICATE", "")
    STOP_DUPLICATE = STOP_DUPLICATE.lower() == "true"

    IS_TEAM_DRIVE = environ.get("IS_TEAM_DRIVE", "")
    IS_TEAM_DRIVE = IS_TEAM_DRIVE.lower() == "true"

    USE_SERVICE_ACCOUNTS = environ.get("USE_SERVICE_ACCOUNTS", "")
    USE_SERVICE_ACCOUNTS = USE_SERVICE_ACCOUNTS.lower() == "true"

    WEB_PINCODE = environ.get("WEB_PINCODE", "")
    WEB_PINCODE = WEB_PINCODE.lower() == "true"

    AS_DOCUMENT = environ.get("AS_DOCUMENT", "")
    AS_DOCUMENT = AS_DOCUMENT.lower() == "true"

    EQUAL_SPLITS = environ.get("EQUAL_SPLITS", "")
    EQUAL_SPLITS = EQUAL_SPLITS.lower() == "true"

    MEDIA_GROUP = environ.get("MEDIA_GROUP", "")
    MEDIA_GROUP = MEDIA_GROUP.lower() == "true"

    USER_TRANSMISSION = environ.get("USER_TRANSMISSION", "")
    USER_TRANSMISSION = USER_TRANSMISSION.lower() == "true" and IS_PREMIUM_USER

    BASE_URL_PORT = environ.get("BASE_URL_PORT", "")
    BASE_URL_PORT = 80 if len(BASE_URL_PORT) == 0 else int(BASE_URL_PORT)

    RCLONE_SERVE_URL = environ.get("RCLONE_SERVE_URL", "")
    if len(RCLONE_SERVE_URL) == 0:
        RCLONE_SERVE_URL = ""

    RCLONE_SERVE_PORT = environ.get("RCLONE_SERVE_PORT", "")
    RCLONE_SERVE_PORT = (
        8080 if len(RCLONE_SERVE_PORT) == 0 else int(RCLONE_SERVE_PORT)
    )

    RCLONE_SERVE_USER = environ.get("RCLONE_SERVE_USER", "")
    if len(RCLONE_SERVE_USER) == 0:
        RCLONE_SERVE_USER = ""

    RCLONE_SERVE_PASS = environ.get("RCLONE_SERVE_PASS", "")
    if len(RCLONE_SERVE_PASS) == 0:
        RCLONE_SERVE_PASS = ""

    NAME_SUBSTITUTE = environ.get("NAME_SUBSTITUTE", "")
    NAME_SUBSTITUTE = "" if len(NAME_SUBSTITUTE) == 0 else NAME_SUBSTITUTE

    MIXED_LEECH = environ.get("MIXED_LEECH", "")
    MIXED_LEECH = MIXED_LEECH.lower() == "true" and IS_PREMIUM_USER

    THUMBNAIL_LAYOUT = environ.get("THUMBNAIL_LAYOUT", "")
    THUMBNAIL_LAYOUT = "" if len(THUMBNAIL_LAYOUT) == 0 else THUMBNAIL_LAYOUT

    FFMPEG_CMDS = environ.get("FFMPEG_CMDS", "")
    try:
        FFMPEG_CMDS = [] if len(FFMPEG_CMDS) == 0 else eval(FFMPEG_CMDS)
    except:
        LOGGER.error(f"Wrong FFMPEG_CMDS format: {FFMPEG_CMDS}")
        FFMPEG_CMDS = []

    await (await create_subprocess_exec("pkill", "-9", "-f", "gunicorn")).wait()
    BASE_URL = environ.get("BASE_URL", "").rstrip("/")
    if len(BASE_URL) == 0:
        BASE_URL = ""
    else:
        await create_subprocess_shell(
            f"gunicorn web.wserver:app --bind 0.0.0.0:{BASE_URL_PORT} --worker-class gevent"
        )

    UPSTREAM_REPO = environ.get("UPSTREAM_REPO", "")
    if len(UPSTREAM_REPO) == 0:
        UPSTREAM_REPO = ""

    UPSTREAM_BRANCH = environ.get("UPSTREAM_BRANCH", "")
    if len(UPSTREAM_BRANCH) == 0:
        UPSTREAM_BRANCH = "master"

    drives_ids.clear()
    drives_names.clear()
    index_urls.clear()

    if GDRIVE_ID:
        drives_names.append("Main")
        drives_ids.append(GDRIVE_ID)
        index_urls.append(INDEX_URL)

    if await aiopath.exists("list_drives.txt"):
        async with aiopen("list_drives.txt", "r+") as f:
            lines = await f.readlines()
            for line in lines:
                temp = line.strip().split()
                drives_ids.append(temp[1])
                drives_names.append(temp[0].replace("_", " "))
                if len(temp) > 2:
                    index_urls.append(temp[2])
                else:
                    index_urls.append("")

    config_dict.update(
        {
            "AS_DOCUMENT": AS_DOCUMENT,
            "AUTHORIZED_CHATS": AUTHORIZED_CHATS,
            "BASE_URL": BASE_URL,
            "BASE_URL_PORT": BASE_URL_PORT,
            "BOT_TOKEN": BOT_TOKEN,
            "CMD_SUFFIX": CMD_SUFFIX,
            "DATABASE_URL": DATABASE_URL,
            "DEFAULT_UPLOAD": DEFAULT_UPLOAD,
            "DOWNLOAD_DIR": DOWNLOAD_DIR,
            "EQUAL_SPLITS": EQUAL_SPLITS,
            "EXTENSION_FILTER": EXTENSION_FILTER,
            "FFMPEG_CMDS": FFMPEG_CMDS,
            "FILELION_API": FILELION_API,
            "GDRIVE_ID": GDRIVE_ID,
            "INCOMPLETE_TASK_NOTIFIER": INCOMPLETE_TASK_NOTIFIER,
            "INDEX_URL": INDEX_URL,
            "IS_TEAM_DRIVE": IS_TEAM_DRIVE,
            "LEECH_DUMP_CHAT": LEECH_DUMP_CHAT,
            "LEECH_FILENAME_PREFIX": LEECH_FILENAME_PREFIX,
            "LEECH_SPLIT_SIZE": LEECH_SPLIT_SIZE,
            "MEDIA_GROUP": MEDIA_GROUP,
            "MIXED_LEECH": MIXED_LEECH,
            "NAME_SUBSTITUTE": NAME_SUBSTITUTE,
            "OWNER_ID": OWNER_ID,
            "QUEUE_ALL": QUEUE_ALL,
            "QUEUE_DOWNLOAD": QUEUE_DOWNLOAD,
            "QUEUE_UPLOAD": QUEUE_UPLOAD,
            "RCLONE_FLAGS": RCLONE_FLAGS,
            "RCLONE_PATH": RCLONE_PATH,
            "RCLONE_SERVE_URL": RCLONE_SERVE_URL,
            "RCLONE_SERVE_USER": RCLONE_SERVE_USER,
            "RCLONE_SERVE_PASS": RCLONE_SERVE_PASS,
            "RCLONE_SERVE_PORT": RCLONE_SERVE_PORT,
            "RSS_CHAT": RSS_CHAT,
            "RSS_DELAY": RSS_DELAY,
            "SEARCH_API_LINK": SEARCH_API_LINK,
            "SEARCH_LIMIT": SEARCH_LIMIT,
            "SEARCH_PLUGINS": SEARCH_PLUGINS,
            "STATUS_LIMIT": STATUS_LIMIT,
            "STATUS_UPDATE_INTERVAL": STATUS_UPDATE_INTERVAL,
            "STOP_DUPLICATE": STOP_DUPLICATE,
            "STREAMWISH_API": STREAMWISH_API,
            "SUDO_USERS": SUDO_USERS,
            "TELEGRAM_API": TELEGRAM_API,
            "TELEGRAM_HASH": TELEGRAM_HASH,
            "THUMBNAIL_LAYOUT": THUMBNAIL_LAYOUT,
            "TORRENT_TIMEOUT": TORRENT_TIMEOUT,
            "USER_TRANSMISSION": USER_TRANSMISSION,
            "UPSTREAM_REPO": UPSTREAM_REPO,
            "UPSTREAM_BRANCH": UPSTREAM_BRANCH,
            "USENET_SERVERS": USENET_SERVERS,
            "USER_SESSION_STRING": USER_SESSION_STRING,
            "USE_SERVICE_ACCOUNTS": USE_SERVICE_ACCOUNTS,
            "WEB_PINCODE": WEB_PINCODE,
            "YT_DLP_OPTIONS": YT_DLP_OPTIONS,
        }
    )

    if config_dict["DATABASE_URL"]:
        await database.connect()
        await database.update_config(config_dict)
    else:
        await database.disconnect()
    await gather(initiate_search_tools(), start_from_queued(), rclone_serve_booter())
    add_job()


bot.add_handler(
    MessageHandler(
        bot_settings,
        filters=command(
            BotCommands.BotSetCommand,
        )
        & CustomFilters.sudo,
    )
)
bot.add_handler(
    CallbackQueryHandler(
        edit_bot_settings, filters=regex("^botset") & CustomFilters.sudo
    )
)
