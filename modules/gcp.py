from os import getenv
from typing import Optional

from google.cloud.compute_v1 import AttachedDisk, Instance, InstancesClient, AttachedDiskInitializeParams, \
    NetworkInterface, AccessConfig, GetInstanceRequest, DeleteInstanceRequest

from .cloud_provider import CloudProviderWrapper
from .logger import StatDB


class GCPWrapper(CloudProviderWrapper):
    """
    1. Install gcloud CLI: https://cloud.google.com/sdk/docs/install
    2. `gcloud init`
    3. `gcloud auth application-default login`
    4. Add an SSH key with username `chainreactor`: https://console.cloud.google.com/compute/metadata?tab=sshkeys
    """

    DEFAULT_REGION = "us-west2-a"
    DEFAULT_SIZE = "e2-standard-2"
    DEFAULT_USER = "chainreactor"

    ENV_KEY_PATH = "GCP_KEY_PATH"
    ENV_PROJECT_ID = "GCP_PROJECT_ID"

    def __init__(
            self,
            image: str,
            region: str = DEFAULT_REGION,
            size: str = DEFAULT_SIZE,
            stat_db: StatDB = None
    ):
        """
        Initializes the GCPWrapper

        :param image: The preconfigured distro to use
        :param region: The region in which the instance will be created. Defaults to DEFAULT_REGION
        :param size: The machine hardware configuration to use. Defaults to DEFAULT_SIZE
        """

        super().__init__(image, region, size, stat_db)

        self._check_env_vars([self.ENV_KEY_PATH, self.ENV_PROJECT_ID])
        self._check_ssh_key(getenv(self.ENV_KEY_PATH))

        self._instance_client = InstancesClient()
        self._instance: Optional[Instance] = None

    def _spawn_instance(self):
        name = self._build_name()
        self._instance_client.insert(
            instance_resource=Instance(
                machine_type=f"zones/{self.region}/machineTypes/{self.size}",
                name=name,
                disks=[
                    AttachedDisk(
                        boot=True,
                        auto_delete=True,
                        initialize_params=AttachedDiskInitializeParams(
                            source_image=self.image
                        )
                    )
                ],
                network_interfaces=[
                    NetworkInterface(
                        network="global/networks/default",
                        access_configs=[
                            AccessConfig(
                                type_="ONE_TO_ONE_NAT",
                                name="external-nat"
                            )
                        ]
                    )
                ]
            ),
            project=getenv(self.ENV_PROJECT_ID),
            zone=self.region
        ).result()  # returns None

        self._instance = self._instance_client.get(
            request=GetInstanceRequest(
                instance=name,
                project=getenv(self.ENV_PROJECT_ID),
                zone=self.region
            ),
        )

    def _terminate_instance(self):
        if self._instance:
            self._instance_client.delete(
                request=DeleteInstanceRequest(
                    instance=self._instance.name,
                    project=getenv(self.ENV_PROJECT_ID),
                    zone=self.region
                ),
            ).result()
            self._instance = None

    def is_instance_up(self) -> bool:
        if self._instance:
            self._instance = self._instance_client.get(
                request=GetInstanceRequest(
                    instance=self._instance.name,
                    project=getenv(self.ENV_PROJECT_ID),
                    zone=self.region
                ),
            )
            return self._instance.status == "RUNNING"
        return False

    @property
    def ssh_private_key(self) -> str:
        return getenv(self.ENV_KEY_PATH)

    @property
    def ip_address(self) -> str:
        return self._instance.network_interfaces[0].access_configs[0].nat_i_p

    def connect_ssh(
            self,
            user: str = DEFAULT_USER,
            ssh_key_path: str = getenv(ENV_KEY_PATH)
    ) -> bool:
        return CloudProviderWrapper.connect_ssh(self, user, ssh_key_path)
