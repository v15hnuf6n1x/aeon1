from time import time
from uuid import uuid4

from bot import user_data
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.status_utils import get_readable_time
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (
    edit_message,
    send_file,
    send_message,
    delete_message,
)


@new_task
async def start(client, message):
    if len(message.command) > 1 and message.command[1] == "private":
        await delete_message(message)
    elif len(message.command) > 1 and len(message.command[1]) == 36:
        userid = message.from_user.id
        input_token = message.command[1]
        stored_token = await database.get_user_token(userid)
        if stored_token is None:
            return await send_message(
                message,
                "<b>This token is not for you!</b>\n\nPlease generate your own.",
            )
        if input_token != stored_token:
            return await send_message(
                message,
                "Invalid token.\n\nPlease generate a new one.",
            )
        if userid not in user_data:
            return await send_message(
                message,
                "This token is not yours!\n\nKindly generate your own.",
            )
        data = user_data[userid]
        if "token" not in data or data["token"] != input_token:
            return await send_message(
                message,
                "<b>This token has already been used!</b>\n\nPlease get a new one.",
            )
        token = str(uuid4())
        token_time = time()
        data["token"] = token
        data["time"] = token_time
        user_data[userid].update(data)
        await database.update_user_tdata(userid, token, token_time)
        msg = "Your token has been successfully generated!\n\n"
        msg += f"It will be valid for {get_readable_time(int(Config.TOKEN_TIMEOUT), True)}"
        return await send_message(message, msg)
    elif await CustomFilters.authorized(client, message):
        help_command = f"/{BotCommands.HelpCommand}"
        start_string = f"This bot can mirror all your links|files|torrents to Google Drive or any rclone cloud or to telegram.\n<b>Type {help_command} to get a list of available commands</b>"
        await send_message(message, start_string)
    else:
        await send_message(message, "You are not a authorized user!")
    await database.update_pm_users(message.from_user.id)
    return None


@new_task
async def ping(_, message):
    start_time = int(round(time() * 1000))
    reply = await send_message(message, "Starting Ping")
    end_time = int(round(time() * 1000))
    await edit_message(reply, f"{end_time - start_time} ms")


@new_task
async def log(_, message):
    await send_file(message, "log.txt")
