#!/usr/bin/env python3

import argparse
from pathlib import Path

import dill
from pddl.formatter import problem_to_string

from modules.connectors import ListenConnector, RemoteConnector, SSHConnector
from modules.extractor import FactsExtractor
from modules.logger import Logger
from modules.encoder import Encoder


EXTRACTOR_PICKLE_PATH = Path("extractor_data.pkl")
OUTPUT_PROBLEMS_DIRECTORY = Path("generated_problems")

logger = Logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run phases on an IP address")
    parser.add_argument(
        "-p",
        type=int,
        help="Port to connect or listen on (depending on -r, -l or SSH)",
        required=True,
    )
    parser.add_argument(
        "-t",
        type=str,
        help="Target to connect to (to be used with -r or SSH)",
        required=False,
    )
    parser.add_argument(
        "-d", type=str, help="Reference PDDL domain file", required=True
    )
    parser.add_argument(
        "-n",
        type=str,
        help="Label name for the results: pickled facts and problems",
        required=False,
    )
    parser.add_argument(
        "-fc",
        action="store_true",
        help="Assume CVE are not patched",
        required=False,
    )
    connection_group = parser.add_mutually_exclusive_group(required=True)
    connection_group.add_argument(
        "-l",
        action="store_true",
        help="Bind to a port - listen for reverse shell connections instead of connecting to host",
    )
    connection_group.add_argument(
        "-r",
        action="store_true",
        help="Connect back to host's exposed shell",
    )
    connection_group.add_argument(
        "-s",
        action="store_true",
        help="Connect to the host via SSH",
    )

    ssh_group = connection_group.add_argument_group("SSH", "SSH related arguments")
    ssh_group.add_argument("-u", type=str, help="User for SSH connection")
    ssh_group.add_argument("-k", type=str, help="Private key for SSH connection")

    args = parser.parse_args()

    host = args.t
    port = args.p
    domain = Path(args.d)
    label = args.n

    # append label to stems
    if label:
        global EXTRACTOR_PICKLE_PATH
        EXTRACTOR_PICKLE_PATH = EXTRACTOR_PICKLE_PATH.with_stem(
            f"{EXTRACTOR_PICKLE_PATH.stem}_{label}"
        )

        global OUTPUT_PROBLEMS_DIRECTORY
        OUTPUT_PROBLEMS_DIRECTORY = OUTPUT_PROBLEMS_DIRECTORY.with_stem(
            f"{OUTPUT_PROBLEMS_DIRECTORY.stem}_{label}"
        )

    if not domain.exists():
        logger.error(f"Domain file {domain} does not exist")
        exit(-1)

    if port not in range(1, 65536):
        logger.error(f"Invalid port: {port}")
        exit(-1)

    if args.r and not host:
        logger.error("Please set -t when using -r")
        exit(-1)

    container_pickle = Path(EXTRACTOR_PICKLE_PATH)

    if container_pickle.exists():
        logger.info("Loading pickled facts...")
        with open(container_pickle, "rb") as f:
            facts_container = dill.load(f)
    else:
        if args.u and args.k:
            connector = SSHConnector(host, args.u, Path(args.k))
        elif args.l:
            connector = ListenConnector(port)
        else:
            connector = RemoteConnector(host, port)

        connector.initialize()

        fe = FactsExtractor(connector)
        if args.fc:
            fe.extract(args.fc)
        else:
            fe.extract()

        facts_container = fe.container

        logger.info(f"Pickling facts to {EXTRACTOR_PICKLE_PATH}")
        with open(EXTRACTOR_PICKLE_PATH, "wb") as f:
            dill.dump(facts_container, f)

    encoder = Encoder(facts_container)
    problems = encoder.generate_problems(domain)

    if not OUTPUT_PROBLEMS_DIRECTORY.exists():
        logger.info(f"Creating output directory {OUTPUT_PROBLEMS_DIRECTORY}...")
        OUTPUT_PROBLEMS_DIRECTORY.mkdir()

    for name, problem in problems.items():
        problem_filename = f"{name}.pddl"
        problem_file = OUTPUT_PROBLEMS_DIRECTORY / problem_filename

        with open(problem_file, "w") as f:
            f.write(problem_to_string(problem))

        logger.info(f"Written problem {problem_file}")


if __name__ == "__main__":
    main()
