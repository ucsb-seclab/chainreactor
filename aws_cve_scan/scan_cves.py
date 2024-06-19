#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from pathlib import Path

# Get the absolute path to the directory containing current script
current_dir = Path(__file__).resolve().parent
# Add the 'modules' directory to PYTHONPATH
sys.path.append(str(current_dir / ".." / "modules"))

from aws import AWSWrapper
from logger import Logger
from model import DEFAULT_EC2_SSH_USERS

logger = Logger(__name__)


def main(args):
    ami = args.ami

    if args.debug:
        logger.addHandler(logging.FileHandler(f"{ami}.log"))
        logger.setLevel(logging.DEBUG)

    try:
        logger.info("Creating AWS wrapper...")

        with AWSWrapper(ami) as aw:
            aw.wait_for_instance()

            logger.info("Connecting via SSH...")
            for user in DEFAULT_EC2_SSH_USERS:
                try:
                    logger.info(f"Trying to connect to instance as {user}...")
                    aw.connect_ssh(user)

                    logger.info("Connected to the instance.")
                    break
                except Exception as e:
                    logger.error(f"Could not connect: {e}")
                    continue

            if not aw.is_ssh_connected():
                return

            script_dir = Path(os.path.dirname(os.path.realpath(__file__)))
            cve_bin_tool_path = script_dir / "run_cve_bin_tool.sh"
            cbt_db = script_dir / "artifacts" / "cve-bin-tool.sqlite"

            if aw.upload_file(cve_bin_tool_path) and aw.upload_file(cbt_db):
                aw.send_command(f"chmod +x ./{cve_bin_tool_path.name}")
                logger.debug(aw.send_command(f"./{cve_bin_tool_path.name} /usr/bin"))
                aw.download_file("output.json", Path(f"output_{ami}.json"))
    except Exception as e:
        logger.error(f"AWS Instance error: {e}")
        exit(-1)


def parse_arguments():
    parser = argparse.ArgumentParser(description="Connect to an AWS instance.")
    parser.add_argument(
        "ami", type=str, help="The Amazon Machine Image ID to connect to."
    )
    parser.add_argument(
        "-d",
        "--debug",
        action="store_true",
        help="Write debug output to file ({ami}.log)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    main(args)
