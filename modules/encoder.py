import re
import functools
import toml
import operator

from pathlib import Path
from stat import *
from typing import Optional, Union
from pddl import parse_domain
from pddl.core import Constant, Predicate, Problem
from pddl.logic import constants

from .extractor import FactsContainer
from .logger import Logger
from .model import (
    CapabilitiesTomlKeys,
    MicronixExecutable,
    MicronixFile,
    MicronixFileType,
)

CAPABILITIES_TOML_FILE = "capabilities.toml"


class Encoder:
    def __build_objects(
        self, sym: Union[str, list[str]], sym_type: str
    ) -> Optional[list[Constant]]:
        res: list[Constant] = []

        if isinstance(sym, list):
            sym = [self.normalize_string(x) for x in sym]
            res = constants(" ".join(sym), [sym_type])
        elif isinstance(sym, str):
            sym = self.normalize_string(sym)
            res = [Constant(sym, [sym_type])]
        else:
            self._logger.error(
                f"Could not build constant for {sym}. Unknown type {type(sym)}."
            )
            return None

        return res

    def __build_and_add_objects(
        self, sym: Union[str, list[str]], sym_type: str
    ) -> Optional[list[Constant]]:
        res = self.__build_objects(sym, sym_type)

        self.add_objects(res)

        return res

    def __init__(self, facts: FactsContainer):
        self._logger: Logger = Logger(self.__class__.__name__)
        self._facts: FactsContainer = facts
        self._generated_predicates: set[Predicate] = set()
        self._generated_objects: set[Constant] = set()

        # populate generic objects
        self.__build_and_add_objects("process", "process")
        self.__build_and_add_objects("data", "data")
        self.__build_and_add_objects("local", "local")

        # load capabilities TOML file
        script_path: Path = Path(__file__)
        script_workdir: Path = script_path.parent
        config_path: Path = script_workdir / "resources" / CAPABILITIES_TOML_FILE

        if not config_path.exists():
            self._logger.error("Capabilities file does not exist!")
            exit(-1)

        self.capabilities_data = toml.load(config_path)

    def __build_and_add_predicate(
        self, predicate_name: str, consts: Union[Constant, list[Constant]]
    ) -> Optional[Predicate]:
        res = None

        predicate_name = self.normalize_string(predicate_name)

        if isinstance(consts, list):
            res = Predicate(predicate_name, *consts)
        elif isinstance(consts, Constant):
            res = Predicate(predicate_name, consts)
        else:
            self._logger.error(
                f"Could not build predicate with {consts}. Unknown type {type(consts)}."
            )

        self.add_predicates(res)

        return res

    # given a PDDL predicate, this function looks for all the
    # binaries defined in the TOML file associated to such predicate
    def __get_binaries_from_capability(
        self, pddl_capability_predicate: str
    ) -> list[str]:
        res: list[str] = []

        for cap, cap_details in self.capabilities_data[
            CapabilitiesTomlKeys.CAPABILITY_GROUP.value
        ].items():
            for predicate in cap_details[
                CapabilitiesTomlKeys.PDDL_PREDICATES_LIST.value
            ]:
                if predicate != pddl_capability_predicate:
                    continue

            for binary in cap_details[CapabilitiesTomlKeys.BINARIES_LIST.value]:
                binary_name = binary[CapabilitiesTomlKeys.BINARY_NAME.value]
                res.append(binary_name)

        return res

    # generates executable predicates from MicronixFile by parsing
    # the capabilities TOML file.
    # this assumes the capabilities .toml file is in the same directory
    # of this script
    def __generate_capabilities_predicates(self, binary: MicronixExecutable):
        # we do not know what user executables do
        if binary.mn_filetype is MicronixFileType.USER_EXECUTABLE:
            return

        for capability, c_details in self.capabilities_data[
            CapabilitiesTomlKeys.CAPABILITY_GROUP.value
        ].items():
            for b in c_details[CapabilitiesTomlKeys.BINARIES_LIST.value]:
                name = self.normalize_string(b[CapabilitiesTomlKeys.BINARY_NAME.value])
                b_name = self.normalize_string(binary.path.split("/")[-1])

                if not name == b_name:
                    continue

                binary_const = self.__build_and_add_objects(
                    binary.path, binary.pddl_type
                )

                # create predicates
                for predicate in c_details[
                    CapabilitiesTomlKeys.PDDL_PREDICATES_LIST.value
                ]:
                    self.__build_and_add_predicate(predicate, binary_const)
                    self._logger.debug(
                        f"{binary} capability: {capability} ({predicate})"
                    )

    # retrieves the capabilities for a micronixfile binary
    # it returns a map `capability:predicate`
    def __get_binary_capabilities(self, binary: MicronixExecutable) -> dict[str, str]:
        res: dict[str, str] = {}

        # we do not know what user executables do
        if binary.mn_filetype is MicronixFileType.USER_EXECUTABLE:
            return res

        for capability, c_details in self.capabilities_data[
            CapabilitiesTomlKeys.CAPABILITY_GROUP.value
        ].items():
            for b in c_details[CapabilitiesTomlKeys.BINARIES_LIST.value]:
                toml_binary_name = self.normalize_string(
                    b[CapabilitiesTomlKeys.BINARY_NAME.value]
                )
                binary_name = self.normalize_string(binary.path.split("/")[-1])

                if not toml_binary_name == binary_name:
                    continue

                for predicate in c_details[
                    CapabilitiesTomlKeys.PDDL_PREDICATES_LIST.value
                ]:
                    res[capability] = predicate

        return res

    def __process_users_and_groups(self):
        self._logger.info("Processing users and groups...")

        # generate objects for each user.
        # each user has their own group
        for user in self._facts.system_users:
            user_str = f"{user}_u"
            group_str = f"{user}_g"

            const_user = self.__build_and_add_objects(user_str, "user")[0]
            const_group = self.__build_and_add_objects(group_str, "group")[0]

            self.__build_and_add_predicate("user_group", [const_user, const_group])

            if user == "root":
                self.__build_and_add_predicate("user_is_admin", [const_user])
                self.__build_and_add_predicate("group_is_admin", [const_group])

        # controlled user
        ctrl_user = f"{self._facts.current_user}_u"
        const_ctrl_user = self.__build_and_add_objects(ctrl_user, "user")[0]
        self.__build_and_add_predicate("controlled_user", [const_ctrl_user])

        # user - group associations
        for g, users_list in self._facts.system_groups.items():
            # skip if a group does not have extra users
            if not users_list:
                continue

            for u in users_list:
                user = f"{u}_u"
                group = f"{g}_g"

                const_user = self.__build_and_add_objects(user, "user")[0]
                const_group = self.__build_and_add_objects(group, "group")[0]
                self.__build_and_add_predicate("user_group", [const_user, const_group])

    def __process_executables(self):
        self._logger.info("Processing system executables...")

        for s in self._facts.executables:
            self.process_micronix_file(s)

    def __process_user_shells(self):
        self._logger.info("Processing user shells...")

        for user, shell in self._facts.users_shell.items():
            norm_user = self.normalize_string(f"{user}_u")
            norm_shell = self.normalize_string(shell)

            const_user = self.__build_and_add_objects(norm_user, "user")[0]
            const_shell = self.__build_and_add_objects(norm_shell, "executable")[0]
            self.__build_and_add_predicate(
                "executable_systematically_called_by", [const_shell, const_user]
            )

    def __process_cronjobs(self):
        # the regex matches for executables with an absolute
        # path. e.g. /usr/bin/ls
        binary_regex = re.compile(r"(\/[\w\.]+)+")
        self._logger.info("Processing cron jobs...")

        for s in self._facts.cronjobs:
            # TODO: we do NOT handle binaries with arguments!
            # e.g.: /bin/bash /opt/doom.exe
            match = binary_regex.fullmatch(s.cmd)

            if not match:
                continue

            executable_name = self.normalize_string(match.string)
            user = self.normalize_string(f"{s.user}_u")

            executable_const = self.__build_and_add_objects(
                executable_name, "executable"
            )[0]
            user_const = self.__build_and_add_objects(user, "user")[0]

            self.__build_and_add_predicate(
                "executable_systematically_called_by", [executable_const, user_const]
            )

    def __process_systemd_services(self):
        self._logger.info("Processing systemd services...")

        # TODO: missing ExecStart directive parsing
        for s in self._facts.systemd_services:
            mn_file: MicronixFile = s.mn_file

            self.process_micronix_file(mn_file)

            # build daemon_file predicate
            const = self.__build_objects(mn_file.path, "file")[0]
            self.__build_and_add_predicate("daemon_file", const)

            for command in s.cmds:
                executable_name = self.normalize_string(command)
                executable_const = self.__build_and_add_objects(
                    executable_name, "executable"
                )[0]

                # TODO: here we assume that every systemd service is executed as root!
                self.__build_and_add_predicate(
                    "executable_systematically_called_by", [executable_const, "root_u"]
                )

    def __process_writable_files(self):
        self._logger.info("Processing writable files...")

        for f in self._facts.writable_files:
            self.process_micronix_file(f)

    def __process_setugid_files(self):
        self._logger.info("Processing SUID / SGID files...")

        for f in self._facts.setugid_files:
            self.process_micronix_file(f)

    # map each rcfile to a shell binary present on the system
    def __process_rc_files(self):
        # RE to extract the owner of the RC file
        home_user_re = re.compile(r"\/home\/(?P<username>[\w\d]+)")

        self._logger.info("Processing RC files...")

        self.__get_binaries_from_capability("CAP_shell")

        for file, file_shells in self._facts.rcfiles.items():
            rc_owner = ""

            self.process_micronix_file(file)

            # file constant
            const_file = self.__build_and_add_objects(file.path, file.pddl_type)[0]

            # if the RC file is bound to a user home...
            match = home_user_re.match(file.path)
            if match:
                rc_owner = match.group("username")
                const_owner = self.__build_and_add_objects(f"{rc_owner}_u", "user")[0]

            for exec in self._facts.executables:
                exec_name = exec.path.split("/")[-1]

                if exec_name not in file_shells:
                    continue

                # exec constant
                const_exec = self.__build_and_add_objects(exec.path, exec.pddl_type)[0]

                if match:
                    self.__build_and_add_predicate(
                        "executable_loads_user_specific_file",
                        [const_exec, const_owner, const_file],
                    )

    def generate_predicates(self):
        self.__process_users_and_groups()
        self.__process_executables()
        self.__process_writable_files()
        self.__process_setugid_files()
        self.__process_cronjobs()
        self.__process_systemd_services()
        self.__process_rc_files()
        self.__process_user_shells()

    def add_predicates(self, pred: Union[Predicate, list[Predicate]]):
        if isinstance(pred, list):
            self._generated_predicates = self._generated_predicates.union(pred)
        elif isinstance(pred, Predicate):
            self._generated_predicates.add(pred)
        else:
            self._logger.error(
                f"Could not add predicate(s) {pred}. Unknown type {type(pred)}."
            )

    def add_objects(self, const: Union[Constant, list[Constant]]):
        if isinstance(const, list):
            self._generated_objects = self._generated_objects.union(const)
        elif isinstance(const, Constant):
            self._generated_objects.add(const)
        else:
            self._logger.error(
                f"Could not add object(s) {const}. Unknown type {type(const)}."
            )

    @staticmethod
    # This is needed to pass the regex used by the pddl library
    # for symbol names
    def normalize_string(string: str) -> str:
        res: str = string
        forbidden_chars: list[str] = [
            ".",
            "/",
            "[",
            "]",
            "+",
            "*",
            "'",
            " ",
            "(",
            ")",
            "{",
            "}",
            "@",
            "~",
        ]

        for c in forbidden_chars:
            res = res.replace(c, "_")

        if res.startswith("_"):
            res = res[1:]

        return res.lower()

    def __file_should_be_added(self, file: MicronixFile) -> bool:
        if (
            file.mn_filetype == MicronixFileType.SYSTEM_EXECUTABLE
            and not self.__get_binary_capabilities(file)
        ):
            if (
                file.mn_filetype == MicronixFileType.SYSTEM_EXECUTABLE
                and len(file.CVE_capabilities) <= 0
            ):
                return False

        return True

    # Take a MicronixFile as input and generate
    # facts inherent to them
    def process_micronix_file(self, file: MicronixFile):
        if not self.__file_should_be_added(file):
            return

        # user constant
        const_user = self.__build_and_add_objects(f"{file.user}_u", "user")[0]
        # group constant
        const_group = self.__build_and_add_objects(f"{file.group}_g", "group")[0]
        # file constant
        const_file = self.__build_and_add_objects(file.path, file.pddl_type)[0]

        # ownership and location
        if file.mn_filetype == MicronixFileType.DIRECTORY:
            self.__build_and_add_predicate(
                "directory_owner", [const_file, const_user, const_group]
            )
            return

        # location constant
        const_location = self.__build_objects("local", "local")[0]

        # setting file location to "local"
        self.__build_and_add_predicate(
            "file_present_at_location", [const_file, const_location]
        )

        self.__build_and_add_predicate(
            "file_owner", [const_file, const_user, const_group]
        )

        if file.mn_filetype in [
            MicronixFileType.SYSTEM_EXECUTABLE,
            MicronixFileType.USER_EXECUTABLE,
            MicronixFileType.SHARED_OBJECT
        ]:
            self.__generate_capabilities_predicates(file)

            if file.mn_filetype is MicronixFileType.SYSTEM_EXECUTABLE:
                self.__build_and_add_predicate("system_executable", [const_file])
            elif file.mn_filetype is MicronixFileType.USER_EXECUTABLE:
                self.__build_and_add_predicate("user_executable", [const_file])

            # is SUID
            if file.octal_perms & S_ISUID:
                self.__build_and_add_predicate("suid_executable", [const_file])

            if file.so_deps:
                const_so_deps = self.__build_and_add_objects(
                    [x.path for x in file.so_deps], "executable"
                )
                for const_so_dep in const_so_deps:
                    self.__build_and_add_predicate(
                        "executable_always_loads_file", [const_file, const_so_dep]
                    )

        # group permissions
        if file.octal_perms & S_IRGRP:
            self.__build_and_add_predicate(
                "group_file_permission", [const_group, const_file, "FS_READ"]
            )
        if file.octal_perms & S_IWGRP:
            self.__build_and_add_predicate(
                "group_file_permission", [const_group, const_file, "FS_WRITE"]
            )
        if file.octal_perms & S_IXGRP:
            self.__build_and_add_predicate(
                "group_file_permission", [const_group, const_file, "FS_EXEC"]
            )

        # rest of the users permissions
        if file.octal_perms & S_IROTH:
            self.__build_and_add_predicate(
                "default_file_permission", [const_file, "FS_READ"]
            )
        if file.octal_perms & S_IWOTH:
            self.__build_and_add_predicate(
                "default_file_permission", [const_file, "FS_WRITE"]
            )
        if file.octal_perms & S_IXOTH:
            self.__build_and_add_predicate(
                "default_file_permission", [const_file, "FS_EXEC"]
            )

        # special files
        if file.path == "/etc/passwd":
            self.__build_and_add_predicate("file_contents", [const_file, "SYSFILE_PASSWD"])

        # CVE Processing
        if isinstance(file, MicronixExecutable):
            if file.CVE_capabilities:
                for pred in file.CVE_capabilities:
                    self.__build_and_add_predicate(pred, [const_file])

    def total_predicates(self) -> int:
        return len(self._generated_predicates)

    def total_objects(self) -> int:
        return len(self._generated_objects)

    def generate_problems(self, domain_path: Path) -> dict[str, Problem]:
        res: dict[str, Problem] = {}
        # all the goal Predicates, used later to generate a problem file that ORs all the goals together
        goals: list[Predicate] = []
        domain: Domain = parse_domain(domain_path)

        self.generate_predicates()

        # take all users, remove the controlled user.
        # these are going to be the users we will try
        # to impersonate
        users_to_control = list(
            filter(
                lambda x: x != self._facts.current_user,
                self._facts.system_users,
            )
        )

        for u in users_to_control:
            self._logger.info(f"Generating problem to control {u}...")

            problem_name = f"micronix-problem-{u}"
            problem_file = f"{problem_name}.pddl"
            goal = Predicate(
                "controlled_user", Constant(f"{self.normalize_string(u)}_u", "user")
            )
            goals.append(goal)

            problem = Problem(
                problem_name,
                domain=domain,
                init=self._generated_predicates,
                objects=self._generated_objects,
                goal=goal,
            )

            res[problem_name] = problem

        # generate problem to control any user
        goal_any_user = functools.reduce(operator.or_, goals)
        any_user_problem = Problem(
            problem_name,
            domain=domain,
            init=self._generated_predicates,
            objects=self._generated_objects,
            goal=goal_any_user,
        )
        res["micronix-problem-any_user"] = any_user_problem

        self._logger.info("Done!")

        return res

