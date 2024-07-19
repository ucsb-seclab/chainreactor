#!/usr/bin/env python3

import argparse
import subprocess
import time
from pathlib import Path
from tempfile import mkdtemp

import dill
from pddl.formatter import problem_to_string

from modules.aws import (
    AuthFailure,
    AWSWrapper,
    InvalidAMIIDNotFound,
    InvalidAMIMalformed,
    OptInRequired,
    RequestLimitExceeded,
    UnsupportedOperation,
)
from modules.connectors import ListenConnector, RemoteConnector, SSHConnector
from modules.digital_ocean import DigitalOceanWrapper
from modules.encoder import Encoder
from modules.extractor import FactsExtractor
from modules.logger import Logger, StatDB

SCRIPT = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT.parent
STAT_DB: StatDB = None  # Initialized later
STAT_DB_PATH: Path = SCRIPT_DIR / "stats.sqlite"
LOGGER = Logger(__name__, stat_db_path=STAT_DB_PATH, log_to_file=True)
DOMAIN_PATH: Path = SCRIPT_DIR / "domain.pddl"


def init_statdb(args):
    global STAT_DB
    STAT_DB = StatDB(STAT_DB_PATH, args.image, args.unpatched_cves)


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


def extract_facts(args, working_directory: Path) -> bool:
    if args.provider == "aws":
        default_ssh_users = ["ec2-user", "bitnami", "ubuntu", "admin"]
    elif args.provider == "do":
        default_ssh_users = [DigitalOceanWrapper.DEFAULT_USER]

    # the users are ordered. Prefer less privileged first
    pickle_file: Path = SCRIPT_DIR / f"extractor_data_{args.image}.pkl"

    if pickle_file.exists():
        LOGGER.info(f"Pickle file for {args.image} already exists")
        return False

    try:
        with args.wrapper_cls(args.image, stat_db=STAT_DB) as wrapper:
            if wrapper.stat_db:
                wrapper.stat_db.update_run_state(StatDB.RunState.SPAWNING)
            wrapper.wait_for_instance()
            if wrapper.stat_db:
                wrapper.stat_db.update_run_state(StatDB.RunState.INSTANCE_SPAWNED)

            LOGGER.info("Connecting via SSH...")

            ssh_user: str = None
            for user in default_ssh_users:
                try:
                    LOGGER.info(f"Trying to connect to instance as {user}...")
                    wrapper.connect_ssh(user)

                    LOGGER.info("Connected to the instance.")
                    ssh_user = user

                    if wrapper.stat_db:
                        wrapper.stat_db.update_run_state(StatDB.RunState.SSH_CONNECTED)

                    break
                except Exception as e:
                    LOGGER.error(f"Could not connect: {e}")

                    if wrapper.stat_db:
                        wrapper.stat_db.update_run_state(StatDB.RunState.SSH_FAILED)

                    ssh_user: str = None

                    continue

            if not ssh_user:
                LOGGER.error("Could not login as any user to this instance. Abort.")

                if wrapper.stat_db:
                    wrapper.stat_db.update_run_state(StatDB.RunState.SSH_FAILED)

                return False

            start_time: float = time.time()

            # Recursively calling a script isn't great, but it'll suffice for one call
            extract_args = [
                SCRIPT,
                "extract",
                "--port",
                "22",
                "--target",
                wrapper.ip_address,
                "--name",
                args.image,
                "--ssh" "--user",
                ssh_user,
                "--key",
                wrapper.ssh_private_key,
            ]
            if args.unpatched_cves:
                extract_args.append("--unpatched-cves")

            spawn_process(extract_args, working_directory=working_directory)

            # add problem generation time to StatDB
            end_time: float = time.time()
            elapsed_time: float = end_time - start_time

            if STAT_DB:
                STAT_DB.update_problem_generation_time(elapsed_time)

            # check if the facts extractor generated the problems
            # if so, log it in the StatDB
            if not Path(Path(working_directory) / f"generated_problems_{args.image}").exists():
                LOGGER.error("Could not extract facts.")

                if wrapper.stat_db:
                    wrapper.stat_db.update_run_state(StatDB.RunState.FACTS_FAILED)

                return False

            LOGGER.info("Facts extracted!")

            if wrapper.stat_db:
                wrapper.stat_db.update_run_state(StatDB.RunState.FACTS_EXTRACTED)
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
    global STAT_DB

    # solver should be in the repo root
    solver: Path = SCRIPT_DIR.parent.parent / "solve_problem.py"

    if not problem.exists():
        LOGGER.error("Problem not found. Cannot continue solving.")

        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.PROBLEMS_FAILED)

        exit(-1)

    if not solver.exists():
        LOGGER.error(f'Cannot find solver at "{solver}". Cannot continue solving.')

        if STAT_DB:
            STAT_DB.update_run_state(StatDB.RunState.SOLVER_ERROR)

        exit(-1)

    start_time: float = time.time()

    spawn_process(
        [solver, "-d", DOMAIN_PATH, "-p", problem], working_directory=working_directory
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


def upload_and_run_script(args):
    if not args.script.exists():
        LOGGER.error(f"{args.script} does not exist.")
        return

    with args.wrapper_cls(args.image) as wrapper:
        wrapper.wait_for_instance()

        try:
            wrapper.connect_ssh()
        except Exception as e:
            LOGGER.error(f"Caught exception when connecting via SSH: {e}")
            return

        LOGGER.info("Connected.")

        if not wrapper.is_ssh_connected():
            LOGGER.error("Could not connect. Exiting.")
            exit(-1)

        LOGGER.info(f"Uploading {args.script}...")

        if not wrapper.upload_file(args.script):
            LOGGER.error(f"Could not upload {args.script}")
            return

        wrapper.send_command(f"chmod +x {args.script.name}")
        print("\n".join(wrapper.send_command(f"./{args.script.name}").stdout))

    LOGGER.info("Done")


def add_subparser_extract(subparsers):
    parser = subparsers.add_parser(
        "extract",
        help="Extract system information, generate problems, and attempt to solve from a custom connection",
    )

    group = parser.add_argument_group("extract")
    group.add_argument(
        "-p",
        "--port",
        type=int,
        help="Port to connect or listen on (depending on -r, -l or SSH)",
        required=True,
    )
    group.add_argument(
        "-t",
        "--target",
        type=str,
        help="Target to connect to (to be used with -r or SSH)",
    )
    group.add_argument(
        "-n",
        "--name",
        type=str,
        help="Filesystem name for the results (pickled facts and PDDL problems)",
    )
    group.add_argument(
        "-uc",
        "--unpatched-cves",
        action="store_true",
        help="If set, assume CVEs in remote binaries are unpatched",
    )

    connection_group = group.add_mutually_exclusive_group(required=True)
    connection_group.add_argument(
        "-l",
        "--listen",
        action="store_true",
        help="Listen for reverse shell connection instead of connecting to host",
    )
    connection_group.add_argument(
        "-r",
        "--reverse",
        action="store_true",
        help="Connect back to host's exposed shell",
    )
    connection_group.add_argument(
        "-s",
        "--ssh",
        action="store_true",
        help="Connect to the host via SSH",
    )

    group.add_argument(
        "-u",
        "--user",
        type=str,
        help="SSH user",
    )
    group.add_argument(
        "-k",
        "--key",
        type=str,
        help="SSH private key",
    )


def add_subparser_cloud(subparsers):
    parser = subparsers.add_parser(
        "cloud",
        help="Spawn, extract system information, generate problems, and attempt to solve a cloud-provided instance",
    )

    group = parser.add_argument_group("cloud")
    group.add_argument(
        "provider",
        choices=["aws", "do"],
        help="Which cloud provider to use (aws=Amazon, do=Digital Ocean)",
    )
    group.add_argument(
        "image",
        type=str,
        help="The provider-specific image ID to spawn",
    )
    group.add_argument(
        "-s",
        "--script",
        type=str,
        help="A local script to be executed on the remote instance",
    )
    group.add_argument(
        "-uc",
        "--unpatched-cves",
        action="store_true",
        help="If set, assume CVEs in remote binaries are unpatched",
    )


def validate_args_extract(args):
    if args.port not in range(1, 2**16):
        LOGGER.error(f"Invalid port: {args.port}")
        exit(-1)

    if args.ssh:
        if not args.target:
            LOGGER.error(
                "Please specify a target (-t/--target) when using SSH (-s/--ssh)"
            )
            exit(-1)
        if not args.user:
            LOGGER.error("Please specify a user (-u/--user) when using SSH (-s/--ssh)")
            exit(-1)
        if not args.key:
            LOGGER.error("Please specify a key (-k/--key) when using SSH (-s/--ssh)")
            exit(-1)
        args.key = Path(args.key)
        if not args.key.exists():
            LOGGER.error(f"Key file {args.key} does not exist")
            exit(-1)

    elif args.reverse:
        if not args.target:
            LOGGER.error(
                "Please specify a target (-t/--target) when using reverse shell (-r/--reverse)"
            )
            exit(-1)


def handle_extract(args):
    validate_args_extract(args)

    facts_pickle = Path("extractor_data.pkl")
    problems_dir = Path("generated_problems")
    if args.name:
        facts_pickle = facts_pickle.with_stem(f"{facts_pickle.stem}_{args.name}")
        problems_dir = problems_dir.with_stem(f"{problems_dir.stem}_{args.name}")
    problems_dir.mkdir(parents=True, exist_ok=True)

    # Use cached facts or extract them
    if facts_pickle.exists():
        LOGGER.info("Loading pickled facts...")
        with open(facts_pickle, "rb") as f:
            facts_container = dill.load(f)
    else:
        LOGGER.info("Extracting facts...")
        if args.ssh:
            connector = SSHConnector(args.target, args.user, args.key)
        elif args.listen:
            connector = ListenConnector(args.port)
        elif args.reverse:
            connector = RemoteConnector(args.target, args.port)
        connector.initialize()

        facts_extractor = FactsExtractor(connector)
        facts_extractor.extract(args.unpatched_cves)
        facts_container = facts_extractor.container

        LOGGER.info(f"Pickling facts to {facts_pickle}")
        with open(facts_pickle, "wb") as f:
            dill.dump(facts_container, f)

    # Generate problem files
    encoder = Encoder(facts_container)
    problems = encoder.generate_problems(DOMAIN_PATH)
    for name, problem in problems.items():
        problem_file = problems_dir / f"{name}.pddl"
        with open(problem_file, "w") as f:
            f.write(problem_to_string(problem))
        LOGGER.info(f"Generated problem {problem_file}")


def validate_args_cloud(args):
    if args.provider == "aws":
        args.wrapper_cls = AWSWrapper
    elif args.provider == "do":
        args.wrapper_cls = DigitalOceanWrapper

    if args.script:
        args.script = Path(args.script)
        if not args.script.exists():
            LOGGER.error(f"Script file {args.script} does not exist")
            exit(-1)


def handle_cloud(args):
    validate_args_cloud(args)

    init_statdb(args)

    if args.script:
        upload_and_run_script(args)
        return

    temp_dir = Path(mkdtemp(prefix=f"bfg_{args.image}_"))

    LOGGER.info(f"Using temporary directory {temp_dir}")
    LOGGER.info("Extracting facts...")

    try:
        facts_extracted = extract_facts(args, temp_dir)
    except Exception as e:
        LOGGER.error(f"Caught exception: {e}")

        exit(-1)

    if not facts_extracted:
        exit(-1)

    root_problem: Path = Path(
        temp_dir
        / Path(f"generated_problems_{args.image}")
        / Path("micronix-problem-root.pddl")
    )

    LOGGER.info("Solving root problem...")

    try:
        solve_problem(root_problem, temp_dir)
    except Exception as e:
        LOGGER.error(f"Caught exception: {e}")


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_subparser_extract(subparsers)
    add_subparser_cloud(subparsers)

    args = parser.parse_args()
    if args.command == "extract":
        handle_extract(args)
    elif args.command == "cloud":
        handle_cloud(args)


if __name__ == "__main__":
    try:
        main()
    finally:
        if STAT_DB:
            STAT_DB.end_run()
