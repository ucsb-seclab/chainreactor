from os import getenv

import digitalocean

from .cloud_provider import CloudProviderWrapper
from .logger import StatDB
from typing import Optional


class DigitalOceanWrapper(CloudProviderWrapper):
    """
    Docs: https://docs.digitalocean.com/reference/api/api-try-it-now/#/Droplets/droplets_get
    """

    DEFAULT_REGION = "sfo"
    DEFAULT_SIZE = "s-1vcpu-1gb"
    DEFAULT_USER = "chainreactor"

    ENV_ACCESS_TOKEN = "DIGITALOCEAN_ACCESS_TOKEN"
    ENV_KEY_PATH = "DIGITALOCEAN_KEY_PATH"

    def __init__(
            self,
            image: str,
            region: str = DEFAULT_REGION,
            size: str = DEFAULT_SIZE,
            stat_db: Optional[StatDB] = None
    ):
        """
        Initializes the DigitalOceanWrapper

        :param image: The preconfigured distro to use (see: https://marketplace.digitalocean.com)
        :param region: The region in which the instance will be created. Defaults to DEFAULT_REGION
        :param size: The machine hardware configuration to use. Defaults to DEFAULT_SIZE
        """

        super().__init__(image, region, size, stat_db)

        self._check_env_vars([self.ENV_ACCESS_TOKEN, self.ENV_KEY_PATH])
        self._check_ssh_key(getenv(self.ENV_KEY_PATH))

        self._manager = digitalocean.Manager(self.ENV_ACCESS_TOKEN)
        self._instance = digitalocean.Droplet(
            token=self._manager.token,
            name=self._build_name(),
            region=region,
            image=image,
            size_slug=size,
            ssh_keys=self._manager.get_all_sshkeys(),
            user_data=self.__build_user_data()
        )

    def __build_user_data(self):
        ssh_keys = "\n".join(f"      - {key.public_key}" for key in self._manager.get_all_sshkeys())
        return (
            f"#cloud-config\n"
            f"users:\n"
            f"  - name: {DigitalOceanWrapper.DEFAULT_USER}\n"
            f"    shell: /bin/bash\n"
            f"    ssh-authorized-keys:\n"
            f"{ssh_keys}\n"
        )

    def _spawn_instance(self):
        self._instance.create()

    def _terminate_instance(self):
        self._instance.destroy()

    def is_instance_up(self) -> bool:
        try:
            self._instance.load()
        except digitalocean.NotFoundError:
            return False

        return self._instance.status == "active"

    @property
    def ssh_private_key(self) -> str:
        return getenv(self.ENV_KEY_PATH)

    @property
    def ip_address(self) -> str:
        return self._instance.ip_address

    def connect_ssh(
            self,
            user: str = DEFAULT_USER,
            ssh_key_path: str = getenv(ENV_KEY_PATH)
    ) -> bool:
        return CloudProviderWrapper.connect_ssh(self, user, ssh_key_path)
