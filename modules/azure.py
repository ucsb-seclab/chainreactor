from os import getenv
from typing import Optional

from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.v2024_07_01.models import *
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network.models import *
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.resource.resources.v2022_09_01.models import *

from .cloud_provider import CloudProviderWrapper
from .logger import StatDB


class AzureWrapper(CloudProviderWrapper):
    DEFAULT_LOCATION = "westus"
    DEFAULT_SIZE = "Standard_A1_v2"
    DEFAULT_USER = "chainreactor"

    ENV_SUBSCRIPTION_ID = "AZURE_SUBSCRIPTION_ID"
    ENV_PUB_KEY_PATH = "AZURE_PUB_KEY_PATH"
    ENV_PRIV_KEY_PATH = "AZURE_PRIV_KEY_PATH"

    def __init__(
            self,
            image: str,
            region: str = DEFAULT_LOCATION,
            size: str = DEFAULT_SIZE,
            stat_db: Optional[StatDB] = None
    ):
        """
        Initializes the AzureWrapper. Authenticate using the CLI (`az login`) first

        Aself.rgs:
            image: The image URN to use. Select one from azure_images.txt/update_images.sh
            region: The Azure location to use. Defaults to DEFAULT_LOCATION
            size: The Azure size to use. Defaults to DEFAULT_SIZE
        """

        super().__init__(image, region, size, stat_db)

        self._check_env_vars([self.ENV_SUBSCRIPTION_ID, self.ENV_PUB_KEY_PATH, self.ENV_PRIV_KEY_PATH])
        self._check_ssh_key(getenv(self.ENV_PUB_KEY_PATH, self.ENV_PRIV_KEY_PATH))

        credential = DefaultAzureCredential()
        subscription_id = getenv(self.ENV_SUBSCRIPTION_ID)

        self._resource_client = ResourceManagementClient(credential, subscription_id)
        self._network_client = NetworkManagementClient(credential, subscription_id)
        self._compute_client = ComputeManagementClient(credential, subscription_id)

        self._rg: Optional[ResourceGroup] = None
        self._ip_address: Optional[PublicIPAddress] = None
        self._vm: Optional[VirtualMachine] = None

    def _spawn_instance(self):
        self._rg: ResourceGroup = self._resource_client.resource_groups.create_or_update(
            self._build_name(),
            ResourceGroup(location=self.region)
        )

        vnet: VirtualNetwork = self._network_client.virtual_networks.begin_create_or_update(
            self._rg.name,
            "chainreactor-vnet",
            VirtualNetwork(
                location=self.region,
                address_space=AddressSpace(address_prefixes=["10.0.0.0/8"])
            ),
        ).result()
        subnet: Subnet = self._network_client.subnets.begin_create_or_update(
            self._rg.name,
            vnet.name,
            "chainreactor-subnet",
            Subnet(address_prefix="10.0.0.0/24"),
        ).result()
        self._ip_address: PublicIPAddress = self._network_client.public_ip_addresses.begin_create_or_update(
            self._rg.name,
            "chainreactor-ip",
            PublicIPAddress(
                location=self.region,
                sku=PublicIPAddressSku(name=PublicIPAddressSkuName.STANDARD),
                public_ip_allocation_method=IPAllocationMethod.STATIC,
                public_ip_address_version=IPVersion.I_PV4
            )
        ).result()
        nic: NetworkInterface = self._network_client.network_interfaces.begin_create_or_update(
            self._rg.name,
            "chainreactor-nic",
            NetworkInterface(
                location=self.region,
                ip_configurations=[
                    NetworkInterfaceIPConfiguration(
                        name="chainreactor-ip-config",
                        subnet=subnet,
                        public_ip_address=self._ip_address
                    )
                ]
            )
        ).result()

        image_urn = self.image.split(":")
        with open(getenv(self.ENV_PUB_KEY_PATH)) as f:
            pubkey = f.read()
        self._vm: VirtualMachine = self._compute_client.virtual_machines.begin_create_or_update(
            self._rg.name,
            self._build_name(),
            VirtualMachine(
                location=self.region,
                storage_profile=StorageProfile(
                    image_reference=ImageReference(
                        publisher=image_urn[0],
                        offer=image_urn[1],
                        sku=image_urn[2],
                        version=image_urn[3]
                    )
                ),
                hardware_profile=HardwareProfile(vm_size=VirtualMachineSizeTypes.STANDARD_DS1_V2),
                os_profile=OSProfile(
                    admin_username=self.DEFAULT_USER,
                    linux_configuration=LinuxConfiguration(
                        disable_password_authentication=True,
                        ssh=SshConfiguration(public_keys=[SshPublicKey(key_data=pubkey)])
                    )
                ),
                network_profile=NetworkProfile(network_interfaces=[nic])
            )
        ).result()

    def _terminate_instance(self):
        if self._rg:
            self._resource_client.resource_groups.begin_delete(self._rg.name).wait()

    def is_instance_up(self) -> bool:
        if self._vm:
            self._vm: VirtualMachine = self._compute_client.virtual_machines.get(
                self._rg.name,
                self._vm.name
            )
            for status in self._vm.instance_view.statuses:
                if status.code == "PowerState" and status.display_status == "VM running":
                    return True
        return False

    @property
    def ssh_private_key(self) -> str:
        return getenv(self.ENV_PRIV_KEY_PATH)

    @property
    def ip_address(self) -> str:
        self._ip_address: PublicIPAddress = self._network_client.public_ip_addresses.get(
            self._rg.name,
            self._ip_address.name
        )
        return self._ip_address.ip_address

    def connect_ssh(
            self,
            user: str = DEFAULT_USER,
            ssh_key_path: str = getenv(ENV_PRIV_KEY_PATH),
    ) -> bool:
        return CloudProviderWrapper.connect_ssh(self, user, ssh_key_path)
