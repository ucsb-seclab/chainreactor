import re
import Levenshtein
import paramiko

from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass
from paramiko import SSHClient
from pwnlib.tubes.listen import listen
from pwnlib.tubes.remote import remote

from .logger import Logger
from typing import Optional

class SSHException(Exception):
    """Raised when a generic SSH error is encountered"""


@dataclass
class CommandResult:
    """
    A data class that represents the result of a command.

    Attributes:
        stdout (list[str]): The standard output of the command as a list of strings.
        stderr (list[str]): The standard error of the command as a list of strings.
        return_code (int): The return code of the command.

    Methods:
        __iter__: Allows the class instance to be iterable.
        __getitem__: Allows the class instance to be indexed.
    """

    stdout: list[str]
    stderr: list[str]
    return_code: int

    def __iter__(self):
        """
        Allows the class instance to be iterable.

        Returns:
            iterator: An iterator over the standard output.
        """
        return iter(self.stdout)

    def __getitem__(self, item):
        """
        Allows the class instance to be indexed.

        Args:
            item: The index to access.

        Returns:
            str: The line at the given index in the standard output.
        """
        return self.stdout[item]


class Connector(ABC):
    """
    Abstract base class for different types of connectors. This class should be subclassed and not used directly.
    """

    LEVENSHTEIN_RATIO_THRESHOLD = 0.87
    END_COMMAND_DELIMITER = "PeppinoAndTruffolinoWereHere"

    def __init__(self):
        """
        Initializes the connector, setting up the logger and preparing the communication tube.
        """

        self.tube = None
        # shell prompt, need to be stripped from returned lines
        self.prompt: str = None
        self._logger: Logger = Logger(self.__class__.__name__)

    def __receive_all_lines__(self) -> list[str]:
        """
        Private method to receive all lines from the communication tube until the end command delimiter is found.

        Returns:
            list[str]: List of received lines, with color codes stripped from the output.
        """

        data = ""

        while True:
            try:
                line = self.tube.recvlineS()
                # strip colored output
                # taken from https://stackoverflow.com/questions/30425105/filter-special-chars-such-as-color-codes-from-shell-output
                re.sub(r"\x1b(\[.*?[@-~]|\].*?(\x07|\x1b\\))", "", line)

                if not line or line.strip() == self.END_COMMAND_DELIMITER:
                    break

                data += str(line)
            except:
                break

        return data.split("\n")

    @abstractmethod
    def initialize(self):
        """
        Abstract method to initialize a connector. This method should be overridden in subclasses.
        """

        pass

    @abstractmethod
    def terminate(self):
        """
        Abstract method to terminate a connector. This method should be overridden in subclasses.
        """

        pass

    def interactive(self):
        """
        Switches the communication tube to interactive mode, allowing direct user interaction.
        """

        self.tube.interactive()

    def send_command(self, cmd: str) -> CommandResult:
        """
        Sends a command to the communication tube and receives the output.

        Args:
            cmd (str): The command to send.

        Returns:
            list[str]: The output of the command as a list of lines, with the shell prompt and common sh MOTD stripped from the output.
        """

        full_cmd = f"{cmd}; echo {self.END_COMMAND_DELIMITER}"
        self._logger.info(f">> {full_cmd}")

        self.tube.sendline(bytes(full_cmd, encoding="utf-8"))

        # find index of the line that contains the command.
        # let's ignore the line with the command, returning only
        # the command's output
        lines = self.__receive_all_lines__()

        # find index of prompt and ignore line
        try:
            index = next(
                i for i, s in enumerate(lines) if self.prompt and self.prompt in s
            )
            lines = lines[index + 1 :]
        # if the command is not found in the output, just return everything
        except StopIteration:
            pass

        # look for common sh MOTD on connection
        try:
            index = next(
                i
                for i, s in enumerate(lines)
                if "can't access tty; job control turned off" in s
            )
            lines = lines[index + 1 :]
        # if the command is not found in the output, just return everything
        except StopIteration:
            pass

        # look for command in output
        try:
            # use string similarity to check whether the command is in the output
            index = next(
                i
                for i, s in enumerate(lines)
                if Levenshtein.ratio(full_cmd, s[-len(full_cmd) :])
                > Connector.LEVENSHTEIN_RATIO_THRESHOLD
            )
            lines = lines[index + 1 :]
        # if the command is not found in the output, just return everything
        except StopIteration:
            pass

        # if no output is returned, return None
        if not len(lines) or (len(lines) == 1 and lines[0] == ""):
            return CommandResult(stdout=[], stderr=[], return_code=-1)
            # return None

        # strip default PS1s from first line, if any
        for p in ["$ ", "# "]:
            if not lines[0].startswith(p):
                continue
            lines[0] = lines[0].removeprefix(p)

        # strip empty lines before returning output
        stdout = [x for x in lines if x]

        # TODO: NO STDERR OR RETURN CODE ARE RETURNED
        return CommandResult(stdout=stdout, stderr=[], return_code=0)

    def __enter__(self):
        """
        Context management protocol method to initialize a connector when entering a context.

        Returns:
            Connector: The initialized connector.
        """

        self.initialize()

        return self

    def __exit__(self):
        """
        Context management protocol method to terminate a connector when exiting a context.
        """

        self.terminate()


class ListenConnector(Connector):
    def __init__(self, port: int):
        super().__init__()

        self.tube: listen = listen(port)

    def __wait_for_connection__(self) -> bool:
        self._logger.info("Waiting for connections...")

        try:
            self.tube.wait_for_connection()
        except Exception as e:
            self._logger.error(f"Error while waiting for connections: {e}")

        self._logger.info("Connection established.")

        return True

    def initialize(self):
        self.__wait_for_connection__()
        self.prompt = str(self.tube.recv(timeout=1).strip(), encoding="utf-8")

    def terminate(self):
        if not self.tube:
            return

        self.tube.close()


class RemoteConnector(Connector):
    def __init__(self, remote_address: str, port: int):
        super().__init__()

        try:
            self.tube = remote(remote_address, port)
        except Exception as e:
            self._logger.error(f"Error while waiting for connections: {e}")

    def initialize(self):
        self.prompt = str(self.tube.recv(timeout=1).strip(), encoding="utf-8")

    def terminate(self):
        if not self.tube:
            return

        self.tube.close()


class SSHConnector(Connector):
    def __init__(self, remote: str, user: str, private_key: Path):
        super().__init__()

        if not private_key.exists():
            self._logger.error(f"Private key {private_key} does not exist")
            raise FileNotFoundError(f"{private_key} not found")

        self.tube: SSHClient = SSHClient()
        self.remote: str = remote
        self.user: str = user
        self.private_key: Path = private_key

    def is_connected(self) -> bool:
        if not self.tube.get_transport():
            return False

        if not self.tube.get_transport().authenticated:
            return False

        return self.tube.get_transport().is_active()

    def initialize(self):
        if self.is_connected():
            return

        self.tube.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            self._logger.info("Attempting SSH connection...")

            self.tube.connect(
                self.remote, username=self.user, key_filename=str(self.private_key)
            )
        except Exception as e:
            self.tube = SSHClient()
            self._logger.error(f"Exception: {e}")

            raise SSHException(str(e))

    def terminate(self):
        self._logger.debug("Closing SSH connection...")

        if self.is_connected():
            self.tube.close()

    # returns stdout
    def send_command(self, cmd: str) -> CommandResult:
        if not self.is_connected():
            return None

        self._logger.info(f">> {cmd}")
        try:
            _, stdout, stderr = self.tube.exec_command(cmd)
        except Exception as e:
            raise e

        return_code = stdout.channel.recv_exit_status()
        stdout = stdout.read().decode().split("\n")
        stderr = stderr.read().decode().split("\n")

        # remove empty strings from stdout and stderr
        stdout = [x for x in stdout if x]
        stderr = [x for x in stderr if x]

        return CommandResult(stdout=stdout, stderr=stderr, return_code=return_code)

    # uploads file to remote
    # if no dst is provided, the file is going to be
    # uploaded in $cwd
    def upload_file(self, src: Path, dst: Optional[str] = None) -> bool:
        if not self.is_connected():
            return False

        if not src.exists():
            self._logger.error(f"Local file {src} does not exist!")
            return False

        if not dst:
            dst = src.name

        self._logger.info(f'Uploading "{src}" to "{dst}"...')

        sftp = self.tube.open_sftp()

        try:
            sftp.put(src, dst)
        except Exception as e:
            self._logger.error(f"Could not upload file: {e}")
            sftp.close()

            raise e

        sftp.close()

        return True

    # uploads file to remote
    # if no dst is provided, the file is going to be
    # uploaded in $cwd
    def download_file(self, remote: str, local: Optional[Path] = None) -> bool:
        if not self.is_connected():
            return False

        if not local:
            local = Path(Path(remote).stem)

        if local.exists():
            self._logger.warn(f"Local file {local} exists. Overwriting.")

        self._logger.info(f'Downloading "{remote}" to "{local}"...')

        sftp = self.tube.open_sftp()

        try:
            sftp.get(remote, local)
        except Exception as e:
            self._logger.error(f"Could not download file: {e}")
            sftp.close()

            raise e

        sftp.close()

        return True
