#!/usr/bin/env python3

import argparse
import subprocess
import time

from pathlib import Path
from tempfile import mkdtemp
import dill
from pddl.formatter import problem_to_string

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
from modules.connectors import ListenConnector, RemoteConnector, SSHConnector
from modules.extractor import FactsExtractor
from modules.encoder import Encoder

SCRIPT_DIR = Path(__file__).resolve().parent
STAT_DB: StatDB = None  # Initialized later
STAT_DB_PATH: Path = SCRIPT_DIR / "stats.sqlite"
LOGGER = Logger(__name__, stat_db_path=STAT_DB_PATH, log_to_file=True)
DOMAIN_PATH: Path = SCRIPT_DIR / "domain.pddl"


def init_statdb(ami, fc):
    global STAT_DB
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
    print(args)


def handle_cloud(args):
    validate_args_cloud(args)


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
