from bot.core.config_manager import Config

i = Config.CMD_SUFFIX


class BotCommands:
    def __init__(self):
        self.StartCommand = f"start{Config.CMD_SUFFIX}"
        self.MirrorCommand = [f"mirror{Config.CMD_SUFFIX}", f"m{Config.CMD_SUFFIX}"]
        self.YtdlCommand = [f"ytdl{Config.CMD_SUFFIX}", f"y{Config.CMD_SUFFIX}"]
        self.LeechCommand = [f"leech{Config.CMD_SUFFIX}", f"l{Config.CMD_SUFFIX}"]
        self.YtdlLeechCommand = [f"ytdlleech{Config.CMD_SUFFIX}", f"yl{Config.CMD_SUFFIX}"]
        self.CloneCommand = f"clone{Config.CMD_SUFFIX}"
        self.MediaInfoCommand = f"mediainfo{Config.CMD_SUFFIX}"
        self.CountCommand = f"count{Config.CMD_SUFFIX}"
        self.DeleteCommand = f"del{Config.CMD_SUFFIX}"
        self.CancelAllCommand = f"cancelall{Config.CMD_SUFFIX}"
        self.ForceStartCommand = [f"forcestart{Config.CMD_SUFFIX}", f"fs{Config.CMD_SUFFIX}"]
        self.ListCommand = f"list{Config.CMD_SUFFIX}"
        self.SearchCommand = f"search{Config.CMD_SUFFIX}"
        self.StatusCommand = f"status{Config.CMD_SUFFIX}"
        self.UsersCommand = f"users{Config.CMD_SUFFIX}"
        self.AuthorizeCommand = f"authorize{Config.CMD_SUFFIX}"
        self.UnAuthorizeCommand = f"unauthorize{Config.CMD_SUFFIX}"
        self.AddSudoCommand = f"addsudo{Config.CMD_SUFFIX}"
        self.RmSudoCommand = f"rmsudo{Config.CMD_SUFFIX}"
        self.PingCommand = f"ping{Config.CMD_SUFFIX}"
        self.RestartCommand = f"restart{Config.CMD_SUFFIX}"
        self.RestartSessionsCommand = f"restartses{Config.CMD_SUFFIX}"
        self.StatsCommand = f"stats{Config.CMD_SUFFIX}"
        self.HelpCommand = f"help{Config.CMD_SUFFIX}"
        self.LogCommand = f"log{Config.CMD_SUFFIX}"
        self.ShellCommand = f"shell{Config.CMD_SUFFIX}"
        self.AExecCommand = f"aexec{Config.CMD_SUFFIX}"
        self.ExecCommand = f"exec{Config.CMD_SUFFIX}"
        self.ClearLocalsCommand = f"clearlocals{Config.CMD_SUFFIX}"
        self.BotSetCommand = f"botsettings{Config.CMD_SUFFIX}"
        self.UserSetCommand = f"settings{Config.CMD_SUFFIX}"
        self.SpeedTest = f"speedtest{Config.CMD_SUFFIX}"
        self.BroadcastCommand = [f"broadcast{Config.CMD_SUFFIX}", "broadcastall"]
        self.SelectCommand = f"sel{Config.CMD_SUFFIX}"
        self.RssCommand = f"rss{Config.CMD_SUFFIX}"


# BotCommands = _BotCommands()
