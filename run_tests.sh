#!/usr/bin/env bash

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
TEST_DIR="${SCRIPT_DIR}/tests"
DOMAIN_FILE="${SCRIPT_DIR}/domain.pddl"
SOLVER_CMD="${SCRIPT_DIR}/solve_problem.py"

# Recap file to store the results
RECAP_FILE="${SCRIPT_DIR}/tests_recap.txt"

# Clear the recap file if it exists
> "$RECAP_FILE"

# Check if the test directory exists
if [ ! -d "$TEST_DIR" ]; then
	echo "Test directory $TEST_DIR does not exist."
	exit 1
fi

# Iterate over all PDDL files in the test directory
for TEST_FILE in "$TEST_DIR"/*.pddl; do
	# Check if there are any PDDL files
	if [ ! -e "$TEST_FILE" ]; then
		echo "No PDDL files found in $TEST_DIR."
		exit 1
	fi

	$SOLVER_CMD -d "${DOMAIN_FILE}" -p "${TEST_FILE}"

	# Check if the plan.1 file exists to determine if the test succeeded
	if [ -f "plan.1" ]; then
		echo "Test $(basename "$TEST_FILE") succeeded." >> "$RECAP_FILE"
	else
		echo "Test $(basename "$TEST_FILE") failed." >> "$RECAP_FILE"
	fi

	rm -f "plan.1"
done

# Output the recap
cat "$RECAP_FILE"
