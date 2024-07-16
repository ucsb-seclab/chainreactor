#!/usr/bin/env python3

import argparse
import subprocess
import time

from pathlib import Path
from tempfile import mkdtemp

from modules.aws import (
    AWSWrapper,
    OptInRequired,
    AuthFailure,
    RequestLimitExceeded,
    UnsupportedOperation,
    InvalidAMIIDNotFound,
    InvalidAMIMalformed,
)
from modules.digital_ocean import DigitalOceanWrapper
from modules.logger import Logger, StatDB

# Get the absolute path to the directory containing current script
SCRIPT_DIR = Path(__file__).resolve().parent
# to be set later
STAT_DB: StatDB = None
STAT_DB_PATH: Path = Path(SCRIPT_DIR / "stats.sqlite")
LOGGER = Logger(__name__, stat_db_path=STAT_DB_PATH, log_to_file=True)


def init_statdb(ami, fc):
    STAT_DB = StatDB(STAT_DB_PATH, ami, fc)
    
def spawn_process(
    cmd, stream_stdout: bool = True, working_directory: Path = None
) -> tuple[list[str], list[str]]:
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, cwd=working_directory)

    stdout = []

    while True:
        output = process.stdout.readline()

        if output == b"" and process.poll() is not None:
            break

        if output:
            stdout.append(output.strip().decode())

            if stream_stdout:
                print(output.strip().decode())

    return stdout


# spawn the instance
# collect facts and generate <many, many...> problems


def extract_facts_aws(ami: str, working_directory: Path) -> bool:
    # the users are ordered. Prefer less privileged first
    default_ssh_users = ["ec2-user", "bitnami", "ubuntu", "admin"]
    facts_extractor: Path = SCRIPT_DIR / "facts_extractor.py"
    domain: Path = SCRIPT_DIR / "domain.pddl"
    pickle_file: Path = SCRIPT_DIR / f"extractor_data_{ami}.pkl"

    if pickle_file.exists():
        LOGGER.info(f"Pickle file for {ami} already exists")
        return False

    try:
        with AWSWrapper(ami, stat_db=STAT_DB) as aw:
            if aw.stat_db:
                aw.stat_db.update_run_state(StatDB.RunState.SPAWNING)
            aw.wait_for_instance()
            if aw.stat_db:
                aw.stat_db.update_run_state(StatDB.RunState.INSTANCE_SPAWNED)

            LOGGER.info("Connecting via SSH...")

            ssh_user: str = None
            for user in default_ssh_users:
                try:
                    LOGGER.info(f"Trying to connect to instance as {user}...")
                    aw.connect_ssh(user)

                    LOGGER.info("Connected to the instance.")
                    ssh_user = user

                    if aw.stat_db:
                        aw.stat_db.update_run_state(StatDB.RunState.SSH_CONNECTED)

                    break
                except Exception as e:
                    LOGGER.error(f"Could not connect: {e}")

                    if aw.stat_db:
                        aw.stat_db.update_run_state(StatDB.RunState.SSH_FAILED)

                    ssh_user: str = None

                    continue

            if not ssh_user:
                LOGGER.error("Could not login as any user to this instance. Abort.")

                if aw.stat_db:
                    aw.stat_db.update_run_state(StatDB.RunState.SSH_FAILED)

                return False

            instance = aw.instance

            start_time: float = time.time()

            if args.fc:
                spawn_process(
                    [
                        facts_extractor,
                        "-d",
                        domain,
                        "-p",
                        "22",
                        "-s",
                        "-t",
                        instance.public_dns_name,
                        "-u",
                        ssh_user,
                        "-k",
                        aw.ssh_private_key,
                        "-n",
                        ami,
                        "-fc",
                    ],
                    working_directory=working_directory,
                )

            else:
                spawn_process(
                    [
                        facts_extractor,
                        "-d",
                        domain,
                        "-p",
                        "22",
                        "-s",
                        "-t",
                        instance.public_dns_name,
                        "-u",
                        ssh_user,
                        "-k",
                        aw.ssh_private_key,
                        "-n",
                        ami,
                    ],
                    working_directory=working_directory,
                )

            # add problem generation time to StatDB
            end_time: float = time.time()
            elapsed_time: float = end_time - start_time

            if STAT_DB:
                STAT_DB.update_problem_generation_time(elapsed_time)

            # check if the facts extractor generated the problems
            # if so, log it in the StatDB
            if not Path(Path(working_directory) / f"generated_problems_{ami}").exists():
                LOGGER.error("Could not extract facts.")

                if aw.stat_db:
                    aw.stat_db.update_run_state(StatDB.RunState.FACTS_FAILED)

                return False

            LOGGER.info("Facts extracted!")

            if aw.stat_db:
                aw.stat_db.update_run_state(StatDB.RunState.FACTS_EXTRACTED)
    except OptInRequired as e:
        LOGGER.error(f"Caught OptInRequired exception: {e}")
        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.OPTIN_REQUIRED)

        raise e
    except AuthFailure as e:
        LOGGER.error(f"Caught AuthFailure exception: {e}")
        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.AUTH_FAILURE)

        raise e
    except RequestLimitExceeded as e:
        LOGGER.error(f"Caught RequestLimitExceeded exception: {e}")
        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.REQUEST_LIMIT_EXCEEDED)

        raise e
    except UnsupportedOperation as e:
        LOGGER.error(f"Caught UnsupportedOperation exception: {e}")
        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.UNSUPPORTED_OPERATION)

        raise e
    except InvalidAMIIDNotFound as e:
        LOGGER.error(f"Caught InvalidAMIIDNotFound exception: {e}")
        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.AMI_NOT_FOUND)

        raise e
    except InvalidAMIMalformed as e:
        LOGGER.error(f"Caught InvalidAMIMalformed exception: {e}")
        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.AMI_MALFORMED)

        raise e
    except Exception as e:
        LOGGER.error(f"Caught general exception while spawning instance: {e}")
        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.PRE_SPAWN_FAILURE)

        raise e

    return True


def solve_problem(problem: Path, working_directory: Path):
    # solver should be in the repo root
    solver: Path = SCRIPT_DIR.parent.parent / "solve_problem.py"
    domain: Path = SCRIPT_DIR / "domain.pddl"

    if not problem.exists():
        LOGGER.error("Problem not found. Cannot continue solving.")

        if stat_db:
            stat_db.update_run_state(statdb.runstate.problems_failed)

        exit(-1)

    if not solver.exists():
        LOGGER.error(f'Cannot find solver at "{solver}". Cannot continue solving.')

        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.SOLVER_ERROR)

        exit(-1)

    start_time: float = time.time()

    spawn_process(
        [solver, "-d", domain, "-p", problem], working_directory=working_directory
    )

    # add solve time to StatDB
    end_time: float = time.time()
    elapsed_time: float = end_time - start_time

    if STAT_DB:
        STAT_DB.update_solve_time(elapsed_time)

    # check if the planner generated a solution
    # if so, log it in the StatDB
    if list(Path(working_directory).glob("plan*")):
        LOGGER.info("Solution found!")

        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.SOLUTION_FOUND)
    else:
        LOGGER.info("Solution not found.")

        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.SOLUTION_NOT_FOUND)


def extract_facts_do(ami: str, working_directory: Path) -> bool:
    # the users are ordered. Prefer less privileged first
    default_ssh_users = [DigitalOceanWrapper.DEFAULT_USER]
    facts_extractor: Path = SCRIPT_DIR / "facts_extractor.py"
    domain: Path = SCRIPT_DIR / "domain.pddl"
    pickle_file: Path = SCRIPT_DIR / f"extractor_data_{ami}.pkl"

    if pickle_file.exists():
        LOGGER.info(f"Pickle file for {ami} already exists")
        return False

    try:
        with DigitalOceanWrapper(ami, stat_db=STAT_DB) as aw:
            if aw.stat_db:
                aw.stat_db.update_run_state(StatDB.RunState.SPAWNING)
            aw.wait_for_instance()
            if aw.stat_db:
                aw.stat_db.update_run_state(StatDB.RunState.INSTANCE_SPAWNED)

            LOGGER.info("Connecting via SSH...")

            ssh_user: str = None
            for user in default_ssh_users:
                try:
                    LOGGER.info(f"Trying to connect to instance as {user}...")
                    aw.connect_ssh(user)

                    LOGGER.info("Connected to the instance.")
                    ssh_user = user

                    if aw.stat_db:
                        aw.stat_db.update_run_state(StatDB.RunState.SSH_CONNECTED)

                    break
                except Exception as e:
                    LOGGER.error(f"Could not connect: {e}")

                    if aw.stat_db:
                        aw.stat_db.update_run_state(StatDB.RunState.SSH_FAILED)

                    ssh_user: str = None

                    continue

            if not ssh_user:
                LOGGER.error("Could not login as any user to this instance. Abort.")

                if aw.stat_db:
                    aw.stat_db.update_run_state(StatDB.RunState.SSH_FAILED)

                return False

            instance = aw.instance

            start_time: float = time.time()

            if args.fc:
                spawn_process(
                    [
                        facts_extractor,
                        "-d",
                        domain,
                        "-p",
                        "22",
                        "-s",
                        "-t",
                        instance.public_dns_name,
                        "-u",
                        ssh_user,
                        "-k",
                        aw.ssh_private_key,
                        "-n",
                        ami,
                        "-fc",
                    ],
                    working_directory=working_directory,
                )

            else:
                spawn_process(
                    [
                        facts_extractor,
                        "-d",
                        domain,
                        "-p",
                        "22",
                        "-s",
                        "-t",
                        instance.public_dns_name,
                        "-u",
                        ssh_user,
                        "-k",
                        DigitalOceanWrapper.ENV_KEY_PATH,
                        "-n",
                        ami,
                    ],
                    working_directory=working_directory,
                )

            # add problem generation time to StatDB
            end_time: float = time.time()
            elapsed_time: float = end_time - start_time

            if STAT_DB:
                STAT_DB.update_problem_generation_time(elapsed_time)

            # check if the facts extractor generated the problems
            # if so, log it in the StatDB
            if not Path(Path(working_directory) / f"generated_problems_{ami}").exists():
                LOGGER.error("Could not extract facts.")

                if aw.stat_db:
                    aw.stat_db.update_run_state(StatDB.RunState.FACTS_FAILED)

                return False

            LOGGER.info("Facts extracted!")

            if aw.stat_db:
                aw.stat_db.update_run_state(StatDB.RunState.FACTS_EXTRACTED)
    except Exception as e:
        LOGGER.error(f"Caught general exception while spawning instance: {e}")
        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.PRE_SPAWN_FAILURE)

        raise e

    return True


def upload_and_run_script(cls, ami: str, script: Path):
    if not script.exists():
        LOGGER.error(f"{script} does not exist.")
        return

    with cls(ami) as aw:
        aw.wait_for_instance()

        try:
            aw.connect_ssh()
        except Exception as e:
            LOGGER.error(f"Caught exception when connecting via SSH: {e}")
            return

        LOGGER.info("Connected.")

        if not aw.is_ssh_connected():
            LOGGER.error("Could not connect. Exiting.")
            exit(-1)

        LOGGER.info(f"Uploading {script}...")

        if not aw.upload_file(script):
            LOGGER.error(f"Could not upload {script}")
            return

        aw.send_command(f"chmod +x {script.name}")
        print("\n".join(aw.send_command(f"./{script.name}").stdout))

    LOGGER.info("Done")


def handle_do(args):
    ami: str = args.ami

    init_statdb(ami, args.fc)

    # if a script is provided
    # upload to remote and execute
    if args.s:
        upload_and_run_script(DigitalOceanWrapper, ami, Path(args.s))
        return

    temp_dir = Path(mkdtemp(prefix=f"bfg_{ami}_"))

    LOGGER.info(f"Using temporary directory {temp_dir}")
    LOGGER.info("Extracting facts...")

    try:
        facts_extracted = extract_facts_do(ami, temp_dir)
    except Exception as e:
        LOGGER.error(f"Caught exception: {e}")

        exit(-1)

    if not facts_extracted:
        exit(-1)

    root_problem: Path = Path(
        temp_dir
        / Path(f"generated_problems_{ami}")
        / Path("micronix-problem-root.pddl")
    )

    LOGGER.info("Solving root problem...")

    try:
        solve_problem(root_problem, temp_dir)
    except Exception as e:
        LOGGER.error(f"Caught exception: {e}")


def handle_aws(args):
    ami: str = args.ami

    init_statdb(ami, args.fc)

    # if a script is provided
    # upload to remote and execute
    if args.s:
        upload_and_run_script(AWSWrapper, ami, Path(args.s))
        return

    temp_dir = Path(mkdtemp(prefix=f"bfg_{ami}_"))

    LOGGER.info(f"Using temporary directory {temp_dir}")
    LOGGER.info("Extracting facts...")

    try:
        facts_extracted = extract_facts_aws(ami, temp_dir)
    except Exception as e:
        LOGGER.error(f"Caught exception: {e}")

        exit(-1)

    if not facts_extracted:
        exit(-1)

    root_problem: Path = Path(
        temp_dir
        / Path(f"generated_problems_{ami}")
        / Path("micronix-problem-root.pddl")
    )

    LOGGER.info("Solving root problem...")

    try:
        solve_problem(root_problem, temp_dir)
    except Exception as e:
        LOGGER.error(f"Caught exception: {e}")


# TODO: organize functionalities
def main(args):
    match args.command:
        case "aws":
            handle_aws(args)
        case "do":
            handle_do(args)
        case _:
            print("Unknown command")


def parse_arguments():
    # Create the top-level parser
    parser = argparse.ArgumentParser()

    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Create the parser for the "aws" command
    aws_parser = subparsers.add_parser(
        "aws", help="Spawn, extract system information, generate problems, and attempt to solve a problem in an end-to-end scenario from an AWS AMI instance."
    )

    # Create a subcommand group for AWS
    aws_group = aws_parser.add_argument_group(
        "AWS connector", "Arguments for connecting to an AWS instance"
    )
    aws_group.add_argument(
        "ami",
        type=str,
        help="The Amazon Machine Image (AMI) ID of the AWS instance to connect to."
    )
    aws_group.add_argument(
        "-s",
        type=str,
        help="The path to an executable script to be uploaded and run on the AWS instance."
    )
    aws_group.add_argument(
        "-fc",
        action="store_true",
        help="If set, the program will use CVEs related to the binary on the AWS instance without checking if they are patched or not.",
    )

    # Create the parser for the "do" command
    do_parser = subparsers.add_parser(
        "do", help="Spawn, extract system information, generate problems, and attempt to solve a problem in an end-to-end scenario from a Digital Ocean instance."
    )

    # Create a subcommand group for Digital Ocean
    do_group = do_parser.add_argument_group(
        "Digital Ocean connector", "Arguments for connecting to a Digital Ocean instance"
    )
    do_group.add_argument(
        "ami",
        type=str,
        help="The Digital Ocean instance image to connect to."
    )
    do_group.add_argument(
        "-s",
        type=str,
        help="The path to an executable script to be uploaded and run on the Digital Ocean instance."
    )
    do_group.add_argument(
        "-fc",
        action="store_true",
        help="If set, the program will use CVEs related to the binary on the Digital Ocean instance without checking if they are patched or not.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()

    try:
        main(args)
    finally:
        if STAT_DB:
            STAT_DB.end_run()
