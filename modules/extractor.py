import fnmatch
import re
from enum import Enum
from pathlib import Path
from shlex import quote

import toml
from colorama import init
from more_itertools import chunked

from .connectors import Connector
from .logger import Logger
from .model import (
    CapabilitiesTomlKeys,
    CronJob,
    FactsContainer,
    MicronixDirectory,
    MicronixExecutable,
    MicronixFile,
    SystemdService,
)

init(autoreset=True)  # Automatically reset color after each print

POI_BINARIES_DIRS = [
    "/bin",
    "/sbin",
    "/usr/bin",
    "/usr/sbin",
    "/usr/local/sbin",
    "/usr/local/bin",
    "/opt",
    "/home",
]

# TODO Incorporate timeout in all other commands

TIMEOUT = 2

CVE_CAPABILITIES_TOML_FILE = "CVE_capabilities.toml"

PACKAGE_MANAGERS = ["apt", "yum", "dnf", "zypper"]


class CommandEnum(Enum):
    FIND_EXECUTABLES = (
        lambda dir: f"find {dir} -xdev -type f -executable -exec readlink -f {{}} \; 2>/dev/null"
    )
    DUMP_SO_DEPS = lambda exes: f"ldd {' '.join(exes)} 2>/dev/null"
    RESOLVE_PATHS = lambda paths: f"readlink -m {' '.join(paths)} 2>&1"
    VULN_WRITABLE_DIRECTORIES = (
        lambda dir: f"find {dir} -xdev -type d -writable -not -user $(whoami) -exec readlink -f {{}} \; 2>/dev/null"
    )
    VULN_WRITABLE_FILES = (
        lambda dir: f"find {dir} -xdev -type f -writable -not -user $(whoami) -exec readlink -f {{}} \; 2>/dev/null"
    )
    VULN_SETUGID_FILES = (
        lambda dir: f"find {dir} -xdev \( -perm -4000 -o -perm -2000 \) -exec readlink -f {{}} \; 2>/dev/null"
    )
    LIST_USERS = lambda: "cat /etc/passwd | cut -d : -f1 2>/dev/null"
    LIST_GROUPS = lambda: "cat /etc/group 2>/dev/null"
    READ_CRONTAB = lambda: "cat /etc/crontab 2>/dev/null"
    STAT_FILE = lambda files: f"stat {files} -c '%F:%n:%a:%U:%G' 2>/dev/null"
    FILE_FILE = lambda files: f"file {files} 2>/dev/null"
    FIND_FILE = (
        lambda root, files: f"find {root} -xdev -type f {files} -exec readlink -f {{}} \; 2>/dev/null"
    )
    CAT_FILE = lambda file: f"cat {file}"
    LIST_SYSTEMD_SERVICES = (
        lambda: 'find /etc/systemd -iname "*.service" -exec readlink -f {} \; 2>/dev/null'
    )

    # CVE
    EXECUTABLE_VERSION = (
        lambda executable, version_command: f"timeout {TIMEOUT}s {executable} {version_command}"
    )

    # If the condition has sudo it can ask for password, timeout
    EXECUTE_COND = lambda cmd: f"{cmd}"

    WHICH_CMD = lambda bin: f"which {bin}"

    PM_INFO = (
        lambda pm, bin: f"{pm} info {bin} | awk '/Version/ {{ version = $3 }} /Release/ {{ release = $3 }} END {{ printf \"%s-%s\",version,release}}'"
    )

    APT_INFO = lambda bin: f"apt-cache policy {bin} | awk '/Installed:/ {{ print $2 }}'"

    def __call__(self, *args):
        self.value(*args)


class FactsExtractor:
    def __init__(self, connector: Connector):
        self._logger: Logger = Logger(self.__class__.__name__)
        self.connector: Connector = connector
        self.container: FactsContainer = FactsContainer()

    # parses the output of stat with format '%F:%n:%a:%U:%G'
    # and returns a dictionary with the according fields
    def __parse_stat_output(self, stat_output: str) -> dict[str, str]:
        stat_re = re.compile(
            r"(?P<type>.*):(?P<path>.*):(?P<perm>.*):(?P<user>.*):(?P<group>.*)"
        )

        match = stat_re.match(stat_output)

        if not match:
            self._logger.error(f"Could not parse stat output for {stat_output}!")
            exit(-1)

        return {
            "type": match.group("type"),
            "path": match.group("path"),
            "perm": match.group("perm"),
            "user": match.group("user"),
            "group": match.group("group"),
        }

    # returns a dictionary with more information on the file, using `file`
    # executable name : executable type (file output)
    # NOTE: ignores files with spaces and quotes
    def __get_files_type(self, files: list[str]) -> dict[str, str]:
        file_output_re = re.compile(r"(?P<executable>.*):\s*(?P<type>.*)")
        res: dict[str, str] = {}

        escaped_files = [quote(x) for x in files if "'" not in x and " " not in x]
        file_files = self.connector.send_command(
            CommandEnum.FILE_FILE(" ".join(escaped_files))
        ).stdout

        # if output is empty (or empty strings)
        if not file_files or all([x == "" for x in file_files]):
            self._logger.error("Could not retrieve files' type!")
            exit(-1)

        for f in file_files:
            match = file_output_re.match(f)

            if not match:
                self._logger.error(f"No match for {f}")
                continue

            executable = match.group("executable")
            executable_type = match.group("type")

            res[executable] = executable_type

        return res

    def __retrieve_current_user(self):
        user_re = re.compile("uid=[0-9]+\((?P<user>[a-zA-Z0-9_-]+)\)")
        group_re = re.compile("gid=[0-9]+\((?P<group>[a-zA-Z0-9_-]+)\)")

        output = self.connector.send_command("id").stdout[0]

        if not output:
            self._logger.error("Could not retrieve the current user and group!")
            exit(-1)

        self.container.current_user = user_re.findall(output)[0]
        self.container.current_group = group_re.findall(output)[0]

    def __retrieve_users(self):
        output = self.connector.send_command(CommandEnum.LIST_USERS()).stdout
        if not output:
            self._logger.error("Could not retrieve system's users!")
            exit(-1)

        self.container.system_users.update(output)

        # get shells for each user
        output = self.connector.send_command(CommandEnum.CAT_FILE("/etc/passwd")).stdout
        if not output:
            self._logger.error("Could not retrieve users' shells!")
            return

        for l in output:
            splitted_line = l.split(":")

            user = splitted_line[0]
            shell = splitted_line[-1]

            self.container.users_shell[user] = shell

    def __retrieve_groups(self):
        output = self.connector.send_command(CommandEnum.LIST_GROUPS()).stdout

        if not output:
            self._logger.error("Could not retrieve system's groups!")
            exit(-1)

        groups = {}
        for x in output:
            group = x.split(":")[0]
            members = x.split(":")[-1]

            groups[group] = []

            if not members:
                continue

            for m in members.split(","):
                groups[group].append(m)

        self.container.system_groups = groups

    # uses the connector to run stat and file to then build a MicronixFile
    # per filename
    def __construct_micronixobjects_from_names__(
        self, filenames: list[str]
    ) -> list[MicronixFile]:
        res: list[MicronixFile] = []

        # split the load in chunks to avoid failures
        for batch in chunked(filenames, 100):
            # run `file` and get back dict mapping file and type
            file_types = self.__get_files_type(batch)

            if not file_types:
                self._logger.error("Could not file files!")
                exit(-1)

            # get more information on the executables (permissions, owner, etc.)
            escaped_file_types = [quote(x) for x in file_types.keys()]
            stat_files = self.connector.send_command(
                CommandEnum.STAT_FILE(" ".join(escaped_file_types))
            ).stdout

            if not stat_files:
                self._logger.error("Could not stat files!")
                exit(-1)

            # zip together the information gathered up to now
            # creating a MicronixFile
            for x in stat_files:
                parsed_stat_output = self.__parse_stat_output(x)

                path = parsed_stat_output["path"]
                type = file_types[path]
                octal_perms = int(parsed_stat_output["perm"], 8)
                user = parsed_stat_output["user"]
                group = parsed_stat_output["group"]

                if "directory" in type:
                    res.append(MicronixDirectory(path, octal_perms, user, group, type))
                    continue

                if "executable" in type or "shared object" in type:
                    res.append(MicronixExecutable(path, octal_perms, user, group, type))
                    continue

                res.append(MicronixFile(path, octal_perms, user, group, type))

        return res

    # generate MicronixExecutable objects for shared objects that aren't already registered
    def __gen_and_link_so_files(
        self, exe_deps: dict[MicronixExecutable, list[str]], all_deps: set[str]
    ):
        gen_deps = all_deps.difference(x.path for x in self.container.executables)
        new_micronix_deps = self.__construct_micronixobjects_from_names__(
            list(gen_deps)
        )
        self.container.executables += new_micronix_deps

        micronix_deps: dict[str, MicronixExecutable] = {}
        for dep in all_deps:
            micronix_dep = next(
                (x for x in self.container.executables if x.path == dep.lower()), None
            )
            if micronix_dep:
                micronix_deps[dep] = micronix_dep

        for exe, deps in exe_deps.items():
            exe.so_deps = []
            for dep in deps:
                micronix_dep = micronix_deps.get(dep)
                if micronix_dep:
                    exe.so_deps.append(micronix_dep)

    # some ldd output is relative, so try to resolve those paths
    def __resolve_so_paths(
        self, exe_deps: dict[MicronixExecutable, list[str]], all_deps: set[str]
    ):
        deps_list = list(all_deps)  # keep order

        resolve_so_deps_output = self.connector.send_command(
            CommandEnum.RESOLVE_PATHS([quote(x) for x in deps_list])
        ).stdout

        if not resolve_so_deps_output:
            self._logger.warn(
                "Could not resolve executables' shared object dependencies!"
            )
            return

        resolved_deps: dict[str, str] = {}
        for relative, resolved in zip(deps_list, resolve_so_deps_output):
            resolved_deps[relative] = resolved

        for exe, deps in exe_deps.items():
            exe_deps[exe] = [resolved_deps[x] for x in deps]

        self.__gen_and_link_so_files(exe_deps, set(resolved_deps.values()))

    # list all shared object dependencies for a list of executables
    def __dump_so_deps(self, executables: list[MicronixExecutable]):
        # Todo: Compile regex expressions below
        def parse_exe_line(exe_line: str) -> tuple[bool, str | None]:
            # dependency not found
            # ex:     some-android-thing.so => not found
            cap = re.match(r"^\s+.* => not found$", exe_line)
            if cap:
                return False, None

            # a script was included in the executable list
            # this is stdout on old distros, stderr on newer distros
            # ex:     not a dynamic executable
            cap = re.match(r"^\s+not a dynamic executable$", exe_line)
            if cap:
                return False, None

            # dependency lives in memory, not on disk
            # ex:     linux-vdso.so.1 (0x00007ffeaafb8000)
            cap = re.match(r"^\s+((linux-vdso\.so)|(linux-gate\.so)).*$", exe_line)
            if cap:
                return False, None

            # dependency found
            # ex:     libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x00007f22634aa000)
            cap = re.match(r"^\s+.*? => (.*?) .*$", exe_line)
            if cap:
                return False, cap.group(1)

            # dependency found
            # ex:     /lib64/ld-linux-x86-64.so.2 (0x00007f2263870000)
            cap = re.match(r"^\s+(.*?) .*$", exe_line)
            if cap:
                return False, cap.group(1)

            # new executable section
            # ex: /bin/bash:
            cap = re.match(r"^(.*):$", exe_line)
            if cap:
                return True, cap.group(1)

            return False, None

        output = []
        for chunked_execs in chunked(executables, 1000):
            output += self.connector.send_command(
                CommandEnum.DUMP_SO_DEPS([quote(x.path) for x in chunked_execs])
            ).stdout

        if not output:
            self._logger.warn("Could not dump executables' shared object dependencies!")
            return

        exe_deps: dict[MicronixExecutable, list[str]] = {}
        all_deps: set[str] = set()

        # break up the ldd output by executable sections; then parse each shared object entry
        current_exe: MicronixExecutable | None = None
        for line in output:
            is_new_exe, item = parse_exe_line(line)
            if is_new_exe:
                current_exe = next(
                    x for x in self.container.executables if x.path == item
                )
                exe_deps[current_exe] = []
            elif item:
                exe_deps[current_exe].append(item)
                all_deps.add(item)

        self.__resolve_so_paths(exe_deps, all_deps)

    def __retrieve_executables(self):
        # executable name : executable type (file output)
        executables_list: list[str] = []

        # retrieving the executables on the system
        for dir in POI_BINARIES_DIRS:
            output = self.connector.send_command(
                CommandEnum.FIND_EXECUTABLES(dir)
            ).stdout

            if not output:
                continue

            executables_list += output

        if not executables_list:
            self._logger.error("Could not retrieve system's executables!")
            exit(-1)

        micronix_executables = self.__construct_micronixobjects_from_names__(
            executables_list
        )
        self.container.executables += micronix_executables

        self.__dump_so_deps(micronix_executables)

    def __retrieve_writable_files(self):
        writable_files_list: list[str] = []

        output = self.connector.send_command(
            CommandEnum.VULN_WRITABLE_FILES("/")
        ).stdout

        if not output:
            self._logger.error("Could not retrieve any writable file!")
            return

        if output:
            writable_files_list = output

        self.container.writable_files += self.__construct_micronixobjects_from_names__(
            writable_files_list
        )

    def __retrieve_writable_directories(self) -> bool:
        writable_directories: list[str] = []

        output = self.connector.send_command(
            CommandEnum.VULN_WRITABLE_DIRECTORIES("/")
        ).stdout

        if not output:
            self._logger.error("Could not retrieve any writable directory!")
            return

        writable_directories = output

        self.container.writable_directories += (
            self.__construct_micronixobjects_from_names__(writable_directories)
        )

    def __retrieve_setugid(self):
        setugid_files: list[str] = []

        output = self.connector.send_command(CommandEnum.VULN_SETUGID_FILES("/")).stdout

        if not output:
            self._logger.error("Could not retrieve any SUID / SGID file!")
            return

        setugid_files = output

        self.container.setugid_files += self.__construct_micronixobjects_from_names__(
            setugid_files
        )

    def __retrieve_cronjobs(self):
        cronjobs: list[CronJob] = []

        output = self.connector.send_command(CommandEnum.READ_CRONTAB()).stdout

        if not output:
            self._logger.error("Could not retrieve any cron job!")
            return

        for l in output:
            cronjob = CronJob.from_str(l)

            if not cronjob:
                continue

            cronjobs.append(cronjob)

        self.container.cronjobs = cronjobs

    def __retrieve_systemd_services(self):
        executed_cmd_re = re.compile(r"Exec[\w]*=[-!@]*(?P<cmd>[a-zA-Z0-9_\/\.-]+)")
        systemd_services_mn_files: list[MicronixFile] = []
        res: list[SystemdService] = []

        output = self.connector.send_command(CommandEnum.LIST_SYSTEMD_SERVICES()).stdout

        if not output:
            self._logger.warn("Could not retrieve any systemd service!")
            return

        systemd_services_mn_files = self.__construct_micronixobjects_from_names__(
            output
        )

        # retrieve the commands executed by the service
        # to finally construct a SystemdService object
        for s in systemd_services_mn_files:
            # TODO: this can be optimized (and should be)
            # we are calling cat for EACH file...
            file_contents = self.connector.send_command(
                CommandEnum.CAT_FILE(s.path)
            ).stdout

            if not file_contents:
                self._logger.warn(
                    "Ignoring systemd service {s.path} as no contents were retrieved."
                )
                continue

            commands = executed_cmd_re.findall("\n".join(file_contents))

            res.append(SystemdService(s, commands))

        self.container.systemd_services = res

    def __retrieve_rcfiles(self):
        res: dict[MicronixFile, list[str]] = {}

        rcfiles_map: dict[str, list[str]] = {
            ".bashrc": ["bash"],
            ".bash_profile": ["bash"],
            ".bash_login": ["bash"],
            ".profile": ["bash", "zsh", "fish", "ksh", "csh", "tcsh"],
            ".zshrc": ["zsh"],
            ".zprofile": ["zsh"],
            ".zlogin": ["zsh"],
            ".zshenv": ["zsh"],
            ".cshrc": ["csh"],
            ".tcshrc": ["tcsh"],
            ".kshrc": ["ksh"],
            ".login_conf": ["bash", "zsh", "fish", "ksh", "csh", "tcsh"],
            ".bash_logout": ["bash"],
            ".zlogout": ["zsh"],
        }

        # Use .join() to create the string
        command_parts = [
            "-iname '{}' -or".format(filename) for filename in rcfiles_map.keys()
        ]

        # Join all the parts together
        command = " ".join(command_parts)
        # Remove the trailing -or
        command = command[:-3]

        output = self.connector.send_command(
            CommandEnum.FIND_FILE("/home", command)
        ).stdout

        if not output:
            self._logger.error("Could not retrieve any RC files!")
            return

        rc_filenames = output

        # assign each micronixfile to the respective shell
        rcfiles = self.__construct_micronixobjects_from_names__(rc_filenames)

        for f in rcfiles:
            filename: str = f.path.split("/")[-1]

            associated_shells = rcfiles_map[filename]
            res[f] = associated_shells

        self.container.rcfiles = res

    # CVE ADDITION

    # Read the TOML file and creates a list of the binaries that have a CVE defined in it
    def __get_binaries_with_cve(self):
        script_path: Path = Path(__file__)
        script_workdir: Path = script_path.parent
        config_path: Path = script_workdir / "resources" / CVE_CAPABILITIES_TOML_FILE

        if not config_path.exists():
            self._logger.error("CVE Capabilities file does not exist!")
            exit(-1)

        self.capabilities_data = toml.load(config_path)

        for capability, c_details in self.capabilities_data[
            CapabilitiesTomlKeys.CAPABILITY_GROUP.value
        ].items():
            for b in c_details[CapabilitiesTomlKeys.BINARIES_LIST.value]:
                # Mapping cve predicate for future usage
                b["CVE_predicate"] = c_details.get("predicates")[0]
                self.container.binaries_with_cve.append(b)

                # TODO Would be nice to use a dictionary instead of a list of dictionaries
                """
				[{name = emacs, dep=[]},
				{name = gnulibc, dep=[]}]

				{"emacs" : {"dependencies": [...]}
				
				"""

    def __dependencies_checker(self, dependencies_dict: dict) -> bool:
        # File dependencies
        file_dependencies = dependencies_dict.get("files")

        for fd in file_dependencies:
            output = self.connector.send_command(CommandEnum.FIND_FILE("/", fd)).stdout

            if not output:
                dependencies_not_satisfied = True
                return False

        # Executable dependencies
        executable_dependencies = dependencies_dict.get("executables")

        for e in executable_dependencies:
            found = False
            for executable in self.container.executables:
                if executable.pddl_type == "executable" and e in executable.path:
                    found = True
            if found == False:
                return False

        # conditions

        conditions_dependencies = dependencies_dict.get("conditions")
        for cond in conditions_dependencies:
            type_condition = cond.get("type")

            # TODO maybe an enum(?)
            if type_condition == "not_empty":
                op1 = cond.get("op1")
                output = self.connector.send_command(
                    CommandEnum.EXECUTE_COND(op1)
                ).stdout
                if not output:
                    return False

            if type_condition == "user_can_create_file":
                output = self.connector.send_command(
                    CommandEnum.EXECUTE_COND("touch NLZEnKsM2k.txt")
                ).stdout

                if output:
                    return False

        return True

    # Checking the package manager used by the linux distro we are running on

    def __which_pacman__(self):
        for pm in PACKAGE_MANAGERS:
            output = self.connector.send_command(CommandEnum.WHICH_CMD(pm)).stdout
            if output:
                return pm

        return None

    def __recover_version_pm__(self, pm, executable):
        if pm == "apt":
            output = self.connector.send_command(
                CommandEnum.APT_INFO(executable)
            ).stdout

        else:
            output = self.connector.send_command(
                CommandEnum.PM_INFO(pm, executable)
            ).stdout

        return output

    def __recover_version__(self, executable, version_command):
        output = self.connector.send_command(
            CommandEnum.EXECUTABLE_VERSION(executable, version_command)
        ).stdout

        if not output:
            return None

        # TODO in some particular cases like '$ aspell --version' it returns:
        # '@(#) International Ispell Version 3.1.20 (but really Aspell 0.60.8)'
        # the regex matches the version as 3.1.20 and not as 0.60.9
        pattern = r"(\d+(\.\d+)+)"
        version = re.search(pattern, str(output))

        if not version:
            return

        version = version.group(1)

        return version

    def __is_version_vulnerable__(self, bin_version, version_list):
        version_is_vulnerable = False

        for v in version_list:
            if fnmatch.fnmatch(bin_version, v):
                return True

        return False

    def __retrieve_cves__(self, fake_cve):
        self.__get_binaries_with_cve()
        # Recover the package manager used
        # machine_pm = self.__which_pacman__()

        # if not machine_pm:
        # 	self._logger.error("Unable to recover package manager, skipping CVEs")

        for executable in self.container.executables:
            if not executable.pddl_type == "executable":
                continue

            for vuln_dict in self.container.binaries_with_cve:
                dependencies_not_satisfied = False

                if not executable.path.split("/")[-1] == vuln_dict.get("name"):
                    continue

                binary = vuln_dict.get("name")

                bin_version = self.__recover_version__(
                    binary, vuln_dict.get("version_command")
                )[0]

                if not bin_version:
                    continue

                if not self.__is_version_vulnerable__(
                    bin_version, vuln_dict.get("version")
                ):
                    continue

                # Start checking for dependencies
                dependencies_dict = vuln_dict.get("dependencies")

                # Arrived here the CVE conditions are satisfied
                if not self.__dependencies_checker(dependencies_dict):
                    continue

                executable.__append_CVE_capabilities__(vuln_dict.get("CVE_predicate"))

    def extract(self, fake_cve=False):
        self._logger.info("Retrieving current user and group...")
        self.__retrieve_current_user()
        self._logger.info(
            f"Logged in as {self.container.current_user} ({self.container.current_group})"
        )

        self._logger.info("Retrieving system users...")
        self.__retrieve_users()
        self._logger.info("Done!")

        self._logger.info("Retrieving system groups...")
        self.__retrieve_groups()
        self._logger.info("Done!")

        self._logger.info("Retrieving system executables...")
        self.__retrieve_executables()
        self._logger.info("Done!")

        self._logger.info("Retrieving writable files...")
        self.__retrieve_writable_files()
        self._logger.info("Done!")

        self._logger.info("Retrieving writable directories...")
        self.__retrieve_writable_directories()
        self._logger.info("Done!")

        self._logger.info("Retrieving SUID / SGID files...")
        self.__retrieve_setugid()
        self._logger.info("Done!")

        self._logger.info("Retrieving CronJobs...")
        self.__retrieve_cronjobs()
        self._logger.info("Done!")

        self._logger.info("Retrieving systemd services...")
        self.__retrieve_systemd_services()
        self._logger.info("Done!")

        self._logger.info("Retrieving RC files...")
        self.__retrieve_rcfiles()
        self._logger.info("Done!")

        if fake_cve:
            self._logger.info(
                "Retrieving executables affected by CVEs without checking the patches..."
            )
            self.__retrieve_cves__(fake_cve)
            self._logger.info("Done!")
