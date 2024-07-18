import boto3

from os import getenv

from .cloud_provider import CloudProviderWrapper
from .logger import StatDB


class UnsupportedOperation(Exception):
    """Raised when the AMI ID does not support the default configuration"""


class InvalidAMIIDNotFound(Exception):
    """Raised when the AMI ID is not found"""


class InvalidAMIMalformed(Exception):
    """Raised when the AMI ID is malformed"""


class OptInRequired(Exception):
    """Raised when opt-in is required"""


class AuthFailure(Exception):
    """Raised when there is an authentication failure"""


class RequestLimitExceeded(Exception):
    pass


class AWSWrapper(CloudProviderWrapper):
    """
    AWSWrapper is a class that abstracts the interaction with AWS EC2 instances.
    It provides methods to spawn, connect via SSH, send commands, upload and download files to/from instances.
    It also supports managing instance lifecycle within a context manager.
    """

    DEFAULT_REGION = "us-west-1"
    DEFAULT_INSTANCE_TYPE = "t2.micro"
    DEFAULT_USERS = ["ec2-user", "bitnami", "ubuntu", "admin", "root"]

    ENV_KEY_PATH = "AWS_KEY_PATH"
    ENV_KEY_NAME = "AWS_KEYNAME"

    def __init__(
        self,
        image: str,
        region: str = DEFAULT_REGION,
        size: str = DEFAULT_INSTANCE_TYPE,
        stat_db: StatDB = None
    ):
        """
        Initializes the AWSWrapper with the provided AMI, region, instance type, and StatDB.

        :param image: The Amazon Machine Image ID (AMI) to use for the instance
        :param region: The AWS region where the instance will be created. Defaults to DEFAULT_REGION
        :param size: The type of instance to create. Defaults to DEFAULT_INSTANCE_TYPE
        :param stat_db: The database to log instance metadata and statistics. Defaults to None
        """

        super().__init__(image, region, size, stat_db)

        self._check_env_vars([self.ENV_KEY_PATH, self.ENV_KEY_NAME])
        self._check_ssh_key(getenv(self.ENV_KEY_PATH))

        self._ec2 = boto3.resource("ec2", region_name=self.region)
        self._client = boto3.client("ec2", region_name=self.region)
        self.instance = None

    def _spawn_instance(self):
        if self.instance:
            return

        # Try to find the security group
        response = self._client.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": ["ssh_access"]}]
        )

        # Check if the security group exists
        # otherwise, create it
        if len(response["SecurityGroups"]) > 0:
            security_group = self._ec2.SecurityGroup(
                response["SecurityGroups"][0]["GroupId"]
            )
        else:
            security_group = self._ec2.create_security_group(
                GroupName="ssh_access", Description="Security group for SSH access"
            )

            # Authorize inbound SSH traffic
            security_group.authorize_ingress(
                IpProtocol="tcp",
                FromPort=22,
                ToPort=22,
                CidrIp="0.0.0.0/0",
            )

        self._logger.info("Spawning instance...")

        try:
            instances = self._ec2.create_instances(
                ImageId=self.image,
                MinCount=1,
                MaxCount=1,
                InstanceType=self.size,
                KeyName=getenv(self.ENV_KEY_NAME),
                SecurityGroupIds=[security_group.id],
            )
        except Exception as e:
            exception_msg = str(e)

            if "OptInRequired" in exception_msg:
                raise OptInRequired(f"Opt-in is required for {self.image}")
            elif "InvalidAMIID.NotFound" in exception_msg:
                raise InvalidAMIIDNotFound(f"AMI ID {self.image} does not exist")
            elif "InvalidAMIID.Malformed" in exception_msg:
                raise InvalidAMIMalformed(f"AMI ID {self.image} is malformed")
            elif "AuthFailure" in exception_msg:
                raise AuthFailure(f"Authentication failure on AMI {self.image}")
            elif "RequestLimitExceeded" in exception_msg:
                raise RequestLimitExceeded("Reached request limit")
            elif "UnsupportedOperation" in exception_msg:
                raise UnsupportedOperation(
                    f"Unsupported operation for AMI {self.image}: {str(e)}"
                )
            else:
                raise

        self.instance = instances[0]

    def is_instance_up(self) -> bool:
        
        if not self.instance:
            return False

        status_checks = self._ec2.meta.client.describe_instance_status(
            InstanceIds=[self.instance.id]
        )

        if len(status_checks["InstanceStatuses"]) < 1:
            return False
        self.instance = self._ec2.Instance(self.instance.id)

        return (
                status_checks["InstanceStatuses"][0]["InstanceState"]["Name"] == "running"
                and status_checks["InstanceStatuses"][0]["InstanceStatus"]["Status"] == "ok"
        )

    def _terminate_instance(self):
        if self.instance:
            self.instance.terminate()

    @property
    def ssh_private_key(self) -> str:
        return getenv(self.ENV_KEY_PATH)

    @property
    def ip_address(self) -> str:
        return self.instance.public_dns_name

    def connect_ssh(
        self,
        user: str = None,
        ssh_key: str = getenv(ENV_KEY_PATH)
    ) -> bool:
        """
        Establishes an SSH connection to the spawned instance.

        :param user: The username to use for the SSH connection. Defaults to None (i.e. try default users)
        :param ssh_key: The path to the SSH private key to use for the connection. Defaults to the value of the
        AWS_KEY_PATH environment variable.
        :return: True if the connection is successfully established, False otherwise.

        :raise Exception: If the SSH connection initialization fails.
        """

        if user:
            return CloudProviderWrapper.connect_ssh(self, user, ssh_key)
        else:
            # try EC2 users if no user is provided explicitly
            for u in self.DEFAULT_USERS:
                try:
                    if CloudProviderWrapper.connect_ssh(self, u, ssh_key):
                        return True
                    break
                except Exception:
                    self._logger.error(f"Failed to connect via SSH as {u}")

            return False
