#!/usr/bin/env python3

import argparse

from modules.aws import AWSWrapper
from modules.azure import AzureWrapper
from modules.digital_ocean import DigitalOceanWrapper
from modules.gcp import GCPWrapper
from modules.logger import Logger

logger = Logger(__name__)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Spawn a cloud provider instance")
    parser.add_argument(
        "provider", type=str, help="Which cloud provider to use", choices=["aws", "az", "do", "gcp"]
    )
    parser.add_argument(
        "image", type=str, help="The machine image to use"
    )
    return parser.parse_args()


def main(provider, image):
    if provider == "aws":
        cls = AWSWrapper
    elif provider == "az":
        cls = AzureWrapper
    elif provider == "do":
        cls = DigitalOceanWrapper
    elif provider == "gcp":
        cls = GCPWrapper
    else:
        raise LookupError(f"Cloud provider `{provider}` is not implemented")

    try:
        with cls(image) as instance:
            instance.wait_for_instance()
            input("Press enter to exit")
    except Exception as e:
        logger.error(f"Instance error: {e}")
        exit(-1)


if __name__ == "__main__":
    args = parse_arguments()
    main(args.provider, args.image)
