import time
from abc import ABC, abstractmethod
from os import getenv
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .connectors import SSHConnector, CommandResult
from .logger import Logger, StatDB

load_dotenv()


class CloudProviderWrapper(ABC):
    def __init__(self, image: str, region: str, size: str, stat_db: StatDB):
        self._logger = Logger(self.__class__.__name__)

        self.image: str = image
        self.region: str = region
        self.size: str = size

        self.stat_db: StatDB = stat_db
        self._ssh: Optional[SSHConnector] = None

    @abstractmethod
    def _spawn_instance(self):
        pass

    @abstractmethod
    def _terminate_instance(self):
        pass

    @abstractmethod
    def is_instance_up(self) -> bool:
        pass

    @property
    @abstractmethod
    def ssh_private_key(self) -> str:
        pass

    @property
    @abstractmethod
    def ip_address(self) -> str:
        pass

    def spawn_instance(self):
        if self.is_instance_up():
            return

        self._logger.info("Spawning instance...")
        self._spawn_instance()

    def terminate_instance(self):
        self._logger.info("Terminating instance...")

        if self.is_ssh_connected():
            self._logger.debug("Terminating SSH connection...")
            self._ssh.terminate()

        self._terminate_instance()

    def wait_for_instance(self):
        self._logger.info("Waiting for instance to be running...")

        while not self.is_instance_up():
            time.sleep(1)

        self._logger.info(f"Instance up and running at: {self.ip_address}")
        time.sleep(30) # Todo wait for ssh azure please remove me later

    @staticmethod
    def _check_env_vars(env_vars: list[str]):
        for env_var in env_vars:
            if not getenv(env_var):
                raise EnvironmentError(f"Environment variable {env_var} not set. Please export it or set it in .env")

    @staticmethod
    def _check_ssh_key(key_path: str):
        key_path = Path(key_path)
        if not key_path.exists():
            raise EnvironmentError(f"SSH key {key_path} does not exist.")

    def _build_name(self) -> str:
        # GCP has a max name length of ~60 chars
        truncated_image = self.image if len(self.image) <= 35 else self.image[-35:]
        truncated_image = (
            truncated_image
            .replace("/", "-")
            .replace(":", "-")
            .replace("_", "-")
        )
        return f"chainreactor-{int(time.time())}-{truncated_image}"

    def is_ssh_connected(self) -> bool:
        if not self._ssh:
            return False

        return self._ssh.is_connected()

    def connect_ssh(self, user: str, ssh_key_path: str) -> bool:
        if self.is_ssh_connected():
            self._logger.warn("Attempting to connect to an already established connection.")

            return True

        self._ssh = SSHConnector(self.ip_address, user, Path(ssh_key_path))

        try:
            self._ssh.initialize()
        except Exception:
            self._ssh = None
            raise

        return True

    def send_command(self, cmd: str) -> Optional[CommandResult]:
        if not self._ssh.is_connected():
            return None

        return self._ssh.send_command(cmd)

    def upload_file(self, src: Path, dst: Optional[str] = None) -> bool:
        if not self.is_ssh_connected():
            return False

        if not src.exists():
            self._logger.error(f"Local file {src} does not exist!")
            return False

        if not dst:
            dst = src.name

        self._ssh.upload_file(src, dst)

        return True

    def download_file(self, remote: str, local: Optional[Path] = None) -> bool:
        if not self.is_ssh_connected():
            return False

        if not local:
            local = Path(Path(remote).stem)

        if local.exists():
            self._logger.error(f"Local file {local} exists. Overwriting.")

        self._ssh.download_file(remote, local)

        return True

    def __enter__(self):
        """
        Context manager enter method. Spawns a new instance and logs the run if a StatDB is provided.

        :return: this CloudProvider
        """

        if self.stat_db:
            self.stat_db.start_run()

        self.spawn_instance()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit method. Terminates the current instance.

        :param exc_type: The type of the exception that caused the context to be exited, if any.
        :param exc_val: The instance of the exception that caused the context to be exited, if any.
        :param exc_tb: The traceback of the exception that caused the context to be exited, if any.
        """

        self.terminate_instance()
