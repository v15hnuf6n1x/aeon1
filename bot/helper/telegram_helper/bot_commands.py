from bot.core.config_manager import Config

class BotCommands:
    StartCommand = f"start{Config.CMD_SUFFIX}"
    MirrorCommand = [f"mirror{Config.CMD_SUFFIX}", f"m{Config.CMD_SUFFIX}"]
    YtdlCommand = [f"ytdl{Config.CMD_SUFFIX}", f"y{Config.CMD_SUFFIX}"]
    LeechCommand = [f"leech{Config.CMD_SUFFIX}", f"l{Config.CMD_SUFFIX}"]
    YtdlLeechCommand = [
        f"ytdlleech{Config.CMD_SUFFIX}",
        f"yl{Config.CMD_SUFFIX}",
    ]
    CloneCommand = f"clone{Config.CMD_SUFFIX}"
    MediaInfoCommand = f"mediainfo{Config.CMD_SUFFIX}"
    CountCommand = f"count{Config.CMD_SUFFIX}"
    DeleteCommand = f"del{Config.CMD_SUFFIX}"
    CancelAllCommand = f"cancelall{Config.CMD_SUFFIX}"
    ForceStartCommand = [
        f"forcestart{Config.CMD_SUFFIX}",
        f"fs{Config.CMD_SUFFIX}",
    ]
    ListCommand = f"list{Config.CMD_SUFFIX}"
    SearchCommand = f"search{Config.CMD_SUFFIX}"
    StatusCommand = f"status{Config.CMD_SUFFIX}"
    UsersCommand = f"users{Config.CMD_SUFFIX}"
    AuthorizeCommand = f"authorize{Config.CMD_SUFFIX}"
    UnAuthorizeCommand = f"unauthorize{Config.CMD_SUFFIX}"
    AddSudoCommand = f"addsudo{Config.CMD_SUFFIX}"
    RmSudoCommand = f"rmsudo{Config.CMD_SUFFIX}"
    PingCommand = f"ping{Config.CMD_SUFFIX}"
    RestartCommand = f"restart{Config.CMD_SUFFIX}"
    RestartSessionsCommand = f"restartses{Config.CMD_SUFFIX}"
    StatsCommand = f"stats{Config.CMD_SUFFIX}"
    HelpCommand = f"help{Config.CMD_SUFFIX}"
    LogCommand = f"log{Config.CMD_SUFFIX}"
    ShellCommand = f"shell{Config.CMD_SUFFIX}"
    AExecCommand = f"aexec{Config.CMD_SUFFIX}"
    ExecCommand = f"exec{Config.CMD_SUFFIX}"
    ClearLocalsCommand = f"clearlocals{Config.CMD_SUFFIX}"
    BotSetCommand = f"botsettings{Config.CMD_SUFFIX}"
    UserSetCommand = f"settings{Config.CMD_SUFFIX}"
    SpeedTest = f"speedtest{Config.CMD_SUFFIX}"
    BroadcastCommand = [f"broadcast{Config.CMD_SUFFIX}", "broadcastall"]
    SelectCommand = f"sel{Config.CMD_SUFFIX}"
    RssCommand = f"rss{Config.CMD_SUFFIX}"