import logging
import sqlite3

import coloredlogs

from enum import Enum
from pathlib import Path
from datetime import datetime
from typing import Optional


class StatDB:
    """
    A class to represent a database for storing instance metadata and run information.

    Attributes:
        ami (str): The Amazon Machine Image (AMI) this StatDB is going to implicitly handle.
        run_id (int): The run ID this object is going to handle.
                      (Assumes a StatDB can handle a single run)
    """

    class RunState(Enum):
        """
        Enum representing the various states a run can be in.
        """

        # nothing happened, yet
        INITIALIZED = "initialized"
        # misc errors before spawning an instance
        PRE_SPAWN_FAILURE = "pre_spawn_failure"
        # misc errors before spawning an instance
        OPTIN_REQUIRED = "optin_required"
        AUTH_FAILURE = "auth_failure"
        REQUEST_LIMIT_EXCEEDED = "request_limit_exceeded"
        UNSUPPORTED_OPERATION = "unsupported_operation"
        AMI_NOT_FOUND = "ami_not_found"
        AMI_MALFORMED = "ami_malformed"
        # init was ok, waiting for positive status checks
        SPAWNING = "spawning"
        # the instance was correctly spawned and ready to go
        INSTANCE_SPAWNED = "spawned"
        # the instance was reachable via SSH
        SSH_CONNECTED = "ssh_success"
        # the instance was NOT reachable via SSH
        SSH_FAILED = "ssh_failed"
        # we were able to extract facts
        FACTS_EXTRACTED = "facts_success"
        # we were NOT able to extract facts
        FACTS_FAILED = "facts_failed"
        # we generated the problems
        PROBLEMS_GENERATED = "problems_success"
        # we DID NOT generate the problems
        PROBLEMS_FAILED = "problems_failed"
        # something something solver did not work
        SOLVER_ERROR = "solver_failed"
        # solution found
        SOLUTION_FOUND = "solution_success"
        # solution NOT found
        SOLUTION_NOT_FOUND = "solution_failed"

    def __init__(self, db_name: Path, ami: str, cve_patch_checked: bool):
        """
        Constructs all the necessary attributes for the StatDB object.

        Args:
            db_name (Path): The name of the database.
            ami (str): The Amazon Machine Image (AMI) this StatDB is going to implicitly handle.
        """

        self.conn = sqlite3.connect(str(db_name))
        self.cursor = self.conn.cursor()

        # the AMI this statDB is going to implicitly handle
        self.ami: str = ami
        self.cve_patch_checked: bool = cve_patch_checked
        # the run ID this object is going to handle
        # (here we assume a StatDB can handle a single run)
        self.run_id: int = None

        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='runs'"
        )
        if not self.cursor.fetchone():
            self.cursor.execute(
                """
                CREATE TABLE runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ami TEXT,
                    start_timestamp TEXT,
                    end_timestamp TEXT,
                    facts_extracted INTEGER,
                    state TEXT,
                    problem_generation_time REAL,
                    solve_time REAL,
                    cve_patch_checked BOOLEAN
                )
                """
            )
        self.conn.commit()

    def start_run(self):
        """
        Starts a run and inserts a new row in the 'runs' table.

        Args:
            solve_time (float, optional): Time taken to solve the problem in seconds. Defaults to 0.0.
            problem_generation_time (float, optional): Time taken to generate the problem in seconds. Defaults to 0.0.
        """

        timestamp = datetime.now().isoformat()
        self.cursor.execute(
            """
            INSERT INTO runs (ami, start_timestamp, end_timestamp, facts_extracted, solve_time, problem_generation_time, cve_patch_checked) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (self.ami, timestamp, 0, 0, 0, 0, self.cve_patch_checked),
        )
        self.conn.commit()

        self.run_id = self.cursor.lastrowid

        # set the instance state to FAILED by default
        self.update_run_state(self.RunState.INITIALIZED)

    def update_solve_time(self, solve_time: float):
        """
        Updates the solve time for the current run.

        Args:
            solve_time (float): The time taken to solve the problem in seconds.
        """

        if not self.run_id:
            return

        if solve_time < 0:
            raise ValueError("Solve time cannot be negative")

        self.cursor.execute(
            """
            UPDATE runs SET solve_time = ? WHERE id = ?
            """,
            (solve_time, self.run_id),
        )
        self.conn.commit()

    def update_problem_generation_time(self, problem_generation_time: float):
        """
        Updates the problem generation time for the current run.

        Args:
            problem_generation_time (float): The time taken to generate the problem in seconds.
        """

        if not self.run_id:
            return

        if problem_generation_time < 0:
            raise ValueError("Problem generation time cannot be negative")

        self.cursor.execute(
            """
            UPDATE runs SET problem_generation_time = ? WHERE id = ?
            """,
            (problem_generation_time, self.run_id),
        )
        self.conn.commit()

    def end_run(self):
        """
        Ends a run by updating the 'end_timestamp' in the 'runs' table.
        """

        if not self.run_id:
            return

        timestamp = datetime.now().isoformat()
        self.cursor.execute(
            """
            UPDATE runs SET end_timestamp = ? WHERE id = ?
            """,
            (timestamp, self.run_id),
        )
        self.conn.commit()

    def get_runs(self, ami: str):
        """
        Retrieves all runs for a given AMI.

        Args:
            ami (str): The Amazon Machine Image (AMI) to retrieve runs for.

        Returns:
            list: A list of tuples where each tuple represents a run.
        """

        self.cursor.execute(
            """
            SELECT id, start_timestamp, end_timestamp, facts_extracted, solution_found FROM runs WHERE ami = ? ORDER BY start_timestamp
            """,
            (self.ami,),
        )
        return self.cursor.fetchall()

        """

        Returns:
        """

        self.cursor.execute(
            """
            """,
            (self.ami,),
        )
        return self.cursor.fetchone()

    def get_ami_with_both_cve_used(self):
        query = """
            SELECT ami
            FROM runs
            GROUP BY ami
            HAVING COUNT(DISTINCT cve_used) > 1;
        """
        self.cursor.execute(query)

        return [row[0] for row in self.cursor.fetchall()]

    def update_run_state(self, state: RunState):
        """
        Updates the state of the current run.

        Args:
            state (RunState): The new state of the run.
        """

        if not self.run_id:
            return

        self.cursor.execute(
            """
            UPDATE runs SET state = ? WHERE id = ?
            """,
            (str(state), self.run_id),
        )
        self.conn.commit()

    def get_solve_times(self, amis, cve_patch_checked):
        placeholders = ", ".join("?" for ami in amis)
        query = f"""
            SELECT solve_time
            FROM runs
            WHERE ami IN ({placeholders}) AND cve_used = ? AND state = 'RunState.SOLUTION_FOUND'
        """
        self.cursor.execute(query, (*amis, cve_patch_checked))

        return [row[0] for row in self.cursor.fetchall()]

    def get_execution_times(self, amis, cve_patch_checked):
        placeholders = ", ".join("?" for ami in amis)
        query = f"""
            SELECT (strftime('%s', end_timestamp) - strftime('%s', start_timestamp))
            FROM runs
            WHERE ami IN ({placeholders}) AND cve_used = ? AND (state = 'RunState.SOLUTION_FOUND' OR state = 'RunState.SOLUTION_NOT_FOUND') AND end_timestamp != '0'
        """
        self.cursor.execute(query, (*amis, cve_patch_checked))

        return [row[0] for row in self.cursor.fetchall()]

    def get_problem_generation_times(self, amis, cve_patch_checked):
        placeholders = ", ".join("?" for ami in amis)
        query = f"""
            SELECT problem_generation_time
            FROM runs
            WHERE ami IN ({placeholders}) AND cve_used = ? AND (state = 'RunState.SOLUTION_FOUND' OR state = 'RunState.SOLUTION_NOT_FOUND')
        """
        self.cursor.execute(query, (*amis, cve_patch_checked))

        return [row[0] for row in self.cursor.fetchall()]

        """

        Returns:
        """
        statuses = {
            "With solution": self.RunState.SOLUTION_FOUND,
            "No solution": self.RunState.SOLUTION_NOT_FOUND,
            "Opt-in required": self.RunState.OPTIN_REQUIRED,
            "SSH failed": self.RunState.SSH_FAILED,
            "Spawn failed": self.RunState.PRE_SPAWN_FAILURE,
            "Fact generation failed": self.RunState.PROBLEMS_FAILED,
            "Solver error": self.RunState.SOLVER_ERROR,
        }

        status_counts = {}
        for status_name, status_value in statuses.items():
            status_counts[status_name] = self.cursor.execute(
                """
                SELECT COUNT(*) FROM runs WHERE state = ?
                """,
                (str(status_value),),
            ).fetchone()[0]

        return status_counts

    def close(self):
        """
        Closes the database connection.
        """

        self.conn.close()

    def get_solved_amis_no_cves(self):
        """
        Retrieves all the AMIs that have cve_used set to 0 and have status SOLUTION_FOUND or SOLUTION_NOT_FOUND.

        Returns:
            list: A list of AMIs that meet the criteria.
        """

        self.cursor.execute(
            """
            SELECT ami FROM runs 
            WHERE cve_used = 0 AND 
            (state = ? OR state = ?)
            """,
            (str(self.RunState.SOLUTION_FOUND), str(self.RunState.SOLUTION_NOT_FOUND)),
        )
        return [row[0] for row in self.cursor.fetchall()]

    def __enter__(self):
        """
        Makes StatDB usable with "with" statement.
        """

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Makes StatDB usable with "with" statement and ensures the database connection is closed.
        """

        self.close()


class Logger:
    """
    A class to represent a logger with colored logs.

    Attributes:
        logger (logging.Logger): The logger object.
    """

    def __init__(
        self,
        name,
        stat_db_path: Optional[Path] = None,
        log_to_file: bool = False,
        log_file: str = "log.txt",
    ):
        """
        Constructs all the necessary attributes for the Logger object.

        Args:
            name (str): The name of the logger.
            stat_db_path (Path, optional): The path to the StatDB database file.
            log_to_file (bool, optional): Whether to log messages to a file. Defaults to False.
            log_file (str, optional): The name of the file to log messages to. Defaults to "log.txt".
        """

        self.logger = logging.getLogger(name)

        coloredlogs.install(
            fmt="%(asctime)s [%(name)s] - [%(levelname)s] %(message)s",
            datefmt="%d/%m/%Y %H:%M:%S",
            logger=self.logger,
        )

        if log_to_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(name)s] - [%(levelname)s] %(message)s"
                )
            )
            self.logger.addHandler(file_handler)

    def get_logger(self):
        """
        Returns the logger object.

        Returns:
            logging.Logger: The logger object.
        """

        return self.logger

    def __getattr__(self, name):
        """
        Delegates attribute access to the underlying logger object.

        Args:
            name (str): The name of the attribute.

        Returns:
            Any: The value of the attribute.
        """

        return getattr(self.logger, name)
