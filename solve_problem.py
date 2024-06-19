#!/usr/bin/env python3

import subprocess
import argparse
import os
from pathlib import Path


class Solver:
    # runs an executable and returns its stdout on a stream basis
    @staticmethod
    def __call_subprocess(cmd: list[str]) -> str:
        all_output = b""

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        while True:
            # Try to read a line from stdout
            output = process.stdout.readline()
            # If readline returned an empty string, the process has finished and closed the pipe
            if output == b"" and process.poll() is not None:
                break

            all_output += output

            print(str(output.strip(), encoding="utf-8"), flush=True)

        return str(all_output, encoding="utf-8")

    @staticmethod
    def solve(domain: Path, problem: Path) -> str:
        # commandline from powerlifted IPC2023 satisfycing track
        command = [
            "powerlifted",
            "--iteration",
            "alt-bfws1,rff,yannakakis,476",
            "--unit-cost",
            "--preprocess-task",
            "--only-effects-novelty-check",
            "--time-limit",
            "1800",
            "-d",
            domain,
            "-i",
            problem,
        ]

        output = Solver.__call_subprocess(command)

        # if we detected an error...
        if "solution found" not in output.lower():
            print("Error while trying to solve plan!")
            return None

        return output


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("-p", "--problem", type=str, required=True)
    parser.add_argument("-d", "--domain", type=str, required=True)
    args = parser.parse_args()

    domain = Path(args.domain)
    problem = Path(args.problem)

    if not domain.exists():
        print("Domain file does not exist!")
        exit(-1)

    if not problem.exists():
        print("Problem file does not exist!")
        exit(-1)

    plan = Solver.solve(domain, problem)

    if not plan:
        print("No solution found.")
        exit(-1)

    print('Plans(s) generated as "plan*" files.')

    return


if __name__ == "__main__":
    main()
