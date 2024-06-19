import re

from enum import Enum
from typing import Optional, NamedTuple


# TODO: add symbolic links
class MicronixFileType(Enum):
    FILE = 1
    DIRECTORY = 2
    SYSTEM_EXECUTABLE = 3
    USER_EXECUTABLE = 4
    SHARED_OBJECT = 5


class MicronixFile:
    def __init__(
        self, path: str, octal_perms: int, user: str, group: str, raw_type: str
    ):
        self.path: str = path.lower()
        self.octal_perms: int = octal_perms
        self.user: str = user
        self.group: str = group
        self.mn_filetype = MicronixFileType.FILE
        self.pddl_type = "file"
        # output of `file` for the file
        self.raw_type: str = raw_type.lower()

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        match self.mn_filetype:
            case MicronixFileType.DIRECTORY:
                prefix = "Directory"
            case MicronixFileType.SYSTEM_EXECUTABLE:
                prefix = "SysExec"
            case MicronixFileType.USER_EXECUTABLE:
                prefix = "UsrExec"
            case MicronixFileType.SHARED_OBJECT:
                prefix = "Shared Object"
            case _:
                prefix = "File"

        return f"{prefix} {self.path}, {self.user}:{self.group} ({self.octal_perms})"


class MicronixDirectory(MicronixFile):
    def __init__(
        self, path: str, octal_perms: int, user: str, group: str, raw_type: str
    ):
        super().__init__(path, octal_perms, user, group, raw_type)

        self.mn_filetype = MicronixFileType.DIRECTORY
        self.pddl_type = "directory"


class MicronixExecutable(MicronixFile):
    def __init__(
        self, path: str, octal_perms: int, user: str, group: str, raw_type: str
    ):
        super().__init__(path, octal_perms, user, group, raw_type)

        self.raw_type = raw_type
        self.pddl_type = "executable"
        self.CVE_capabilities: list[str] = []
        # shared object xrefs
        self.so_deps: list[MicronixExecutable] = []

        if "shared object" in self.raw_type:
            self.mn_filetype = MicronixFileType.SHARED_OBJECT
            return

        for user_exec_path in ["/home", "/opt"]:
            if user_exec_path in self.path:
                self.mn_filetype = MicronixFileType.USER_EXECUTABLE
                return

        self.mn_filetype = MicronixFileType.SYSTEM_EXECUTABLE

    def __append_CVE_capabilities__(self, CVE_capabilities_p: str) -> None:
        self.CVE_capabilities.append(CVE_capabilities_p)


class CronJob:
    def __init__(
        self,
        user: str,
        cmd: str,
        minute: str,
        hour: str,
        day_month: str,
        month: str,
        day_week: str,
    ):
        self.user: str = user
        self.cmd: str = cmd
        self.minute: str = minute
        self.hour: str = hour
        self.day_month: str = day_month
        self.month: str = month
        self.day_week: str = day_week

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self):
        return f"CronJob: {self.user}, {self.cmd}"

    @staticmethod
    def from_str(cron_string: str) -> Optional["CronJob"]:
        cron_regex = re.compile(
            r"^\s*(?P<minute>[*0-9\/]+)\s+(?P<hour>[*0-9]+)\s+(?P<day_month>[*0-9]+)\s+(?P<month>[*0-9\w]+)\s+(?P<day_week>[*0-9\w]+)\s+(?P<user>[\w0-9_-]+)\s+(?P<cmd>.*)"
        )

        match = cron_regex.match(cron_string)

        if not match:
            return None

        user = match.group("user")
        cmd = match.group("cmd")
        minute = match.group("minute")
        hour = match.group("hour")
        day_month = match.group("day_month")
        month = match.group("month")
        day_week = match.group("day_week")

        return CronJob(user, cmd, minute, hour, day_month, month, day_week)


class CapabilitiesTomlKeys(Enum):
    # groups
    CAPABILITY_GROUP = "capabilities"
    LIMITATIONS_GROUP = "limitations"

    # general
    BINARIES_LIST = "binaries"
    BINARY_NAME = "name"

    # capabilities
    PDDL_PREDICATES_LIST = "predicates"

    # limitations
    LIMITATION_DESCRIPTION = "description"


class SystemdService(NamedTuple):
    mn_file: MicronixFile
    cmds: list[str]


class FactsContainer:
    def __init__(self):
        # the user we are logged in as
        self.current_user: str = None
        # the group we are logged in as
        self.current_group: str = None
        self.system_users: set[str] = set()
        self.users_shell: dict[str, str] = {}
        # group : members
        self.system_groups: dict[str, str] = {}
        # executables on the system
        self.executables: list[MicronixExecutable] = []
        # files that can be written by the current user but that are not owned
        # these are interesting as they might be used to escalate
        self.writable_files: list[MicronixFile] = []
        # directories that can be written by the current user but that are not owned
        # these are interesting as they might be used to escalate
        self.writable_directories: list[MicronixDirectory] = []
        # SUID / SGID files on the system
        self.setugid_files: list[MicronixFile] = []
        # cron jobs on the system
        self.cronjobs: list[CronJob] = []
        # rc files on the system (e.g. bashrc, zshrc, profile, etc.)
        self.rcfiles: dict[MicronixFile, list[str]] = {}
        # cve
        self.binaries_with_cve: list[dict] = []
        # systemd services (in /etc - which we assume are enabled)
        self.systemd_services: list[SystemdService] = []
