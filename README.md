# ChainReactor: Automated Privilege Escalation Chain Discovery via AI Planning

ChainReactor is a research project that leverages AI planning to discover exploitation chains for privilege escalation on Unix systems. The project models the problem as a sequence of actions to achieve privilege escalation from initial access to a target system. This repository contains the open-source implementation of the system described in the paper "ChainReactor: Automated Privilege Escalation Chain Discovery via AI Planning."

## Overview

ChainReactor automates the discovery of privilege escalation chains by:
- Extracting information about available executables, system configurations, and known vulnerabilities on the target system.
- Encoding this data into a Planning Domain Definition Language (PDDL) problem.
- Using a modern planner to generate chains that incorporate vulnerabilities and benign actions.

The tool has been evaluated on synthetic vulnerable VMs, Amazon EC2, and Digital Ocean instances, demonstrating its capability to rediscover known exploits and identify new chains.

## Using Nix for development

Nix is a powerful package manager for Linux and other Unix systems that makes package management reliable and reproducible. It provides atomic upgrades and rollbacks, side-by-side installation of multiple versions of a package, multi-user package management and easy setup of build environments.

This repository uses a `flake.nix` file, which describes the project's dependencies and how to build it. The preferred way to bootstrap the development environment is to use Nix.

### Installing Nix

If Nix is not already installed on your system, you can install it using the [Determinate Systems installer](https://github.com/DeterminateSystems/nix-installer).

```bash
curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install
```

You can verify that Nix was installed correctly by running `nix --version`.

### Entering the Development Environment

Once Nix is installed, you can enter the development environment for this repository.

1. Navigate to the root directory of this repository in your terminal.

2. Run the following command:

```bash
nix develop
```

This command reads the `flake.nix` file and sets up the development environment as described in that file. You are now in the development environment and can begin developing.

## Using the Fact Extractor

The Fact Extractor is a Python script used to extract system facts, which are later processed into PDDL problems with predicates and objects. It supports various connection methods, including reverse shell, bind shell, and SSH connections.

### Usage

```
usage: facts_extractor.py [-h] -p P [-t T] -d D [-n N] [-fc] (-l | -r | -s) [-u U] [-k K]

Run phases on an IP address

options:
  -h, --help            show this help message and exit
  -p P                  Port to connect or listen on (depending on -r, -l or SSH)
  -t T                  Target to connect to (to be used with -r or SSH)
  -d D                  Reference PDDL domain file
  -n N                  Label name for the results: pickled facts and problems
  -fc                   Assume CVE are not patched

connection options:
  -l                    Bind to a port - listen for reverse shell connections instead of connecting to host
  -r                    Connect back to host's exposed shell
  -s                    Connect to the host via SSH

SSH options:
  -u U                  User for SSH connection
  -k K                  Private key for SSH connection
```

### Examples

#### Reverse Shell Connection

To use the Fact Extractor to connect to a remote shell on a target host `192.168.1.2` on port `5000` with the reference PDDL domain file `domain.pddl`, you would run:

```bash
facts_extractor.py -p 5000 -t 192.168.1.2 -d domain.pddl -r
```

#### Bind Shell Connection

To use the Fact Extractor to listen for reverse shell connections on port `5000` with the reference PDDL domain file `domain.pddl`, you would run:

```bash
facts_extractor.py -p 5000 -d domain.pddl -l
```

#### SSH Connection

To use the Fact Extractor to connect via SSH to a target host `192.168.1.2` on port `22` with the reference PDDL domain file `domain.pddl`, you would run:

```bash
facts_extractor.py -p 22 -t 192.168.1.2 -d domain.pddl -s -u username -k /path/to/private/key
```

Replace `username` with the SSH username and `/path/to/private/key` with the path to the SSH private key file.

### Advanced Options

- **Labeling Results**: You can label the results (pickled facts and problems) using the `-n` option. This is useful for organizing multiple runs.
  
  ```bash
  facts_extractor.py -p 5000 -t 192.168.1.2 -d domain.pddl -r -n run1
  ```

- **Assume CVEs Are Not Patched**: Use the `-fc` flag to assume that all CVEs are not patched during the extraction process.

  ```bash
  facts_extractor.py -p 5000 -t 192.168.1.2 -d domain.pddl -r -fc
  ```

### Output

After running the Fact Extractor, you will have a set of generated problems under the directory `generated_problems/`. The problems can then be fed to any PDDL 2.1 planner for solving.

### Workflow

1. **Initialize the Connection**: Depending on the connection method chosen (reverse shell, bind shell, or SSH), the script will establish a connection to the target system.
2. **Extract Facts**: The script will extract system facts, including users, groups, executables, writable files, SUID/SGID files, and vulnerabilities.
3. **Encode Problems**: The extracted facts are encoded into PDDL problems using the specified domain file.
4. **Save Results**: The encoded problems are saved in the `generated_problems/` directory, and the extracted facts are optionally pickled for reuse.

## Tests Overview

This repository contains a bash script (`run_tests.sh`) that automates the execution of a series of tests defined in PDDL (Planning Domain Definition Language) files. The script runs a specified binary command on each test file in a directory and provides a summary of the test results.

The script is designed to:
1. Execute a binary command on all PDDL test files within a specified directory.
2. Check for the existence of a `plan.1` file after each test execution to determine success.
3. Generate a recap of the test results, indicating which tests succeeded and which failed.

The tests represent different scenarios within our domain. Below is an overview of the provided test files:

| Test File | Description |
|-----------|-------------|
| `copy_file.pddl` | Tests the ability to copy a file from a source to a destination location. |
| `upload_file.pddl` | Tests the ability to upload a file from a local to a remote location. |
| `write_to_file_group.pddl` | Tests the ability of a user within a group to write data to a file owned by another group member. |
| `escalate_shell_user_executable.pddl` | Tests privilege escalation by injecting shellcode into a sensitive script using a user binary. |
| `download_file.pddl` | Tests the ability to download a file from a remote to a local location. |
| `cve_shell_command_injection_needs_writable_dir_write_to_file.pddl` | Tests command injection vulnerability requiring writable directory permissions. |
| `read_file_suid.pddl` | Tests reading a file using an SUID executable. |
| `write_to_file.pddl` | Tests writing data to a file using a system executable. |
| `escalate_shell_via_chmod_suid.pddl` | Tests privilege escalation by making a binary SUID and spawning a shell. |
| `change_file_owner.pddl` | Tests changing the owner of a file using a system executable. |
| `escalate_shell.pddl` | Tests privilege escalation by injecting shellcode into a sensitive script using a system executable. |
| `read_file_group.pddl` | Tests reading a file using group permissions. |
| `corrupt_daemon_file.pddl` | Tests corrupting a daemon-managed file to inject a command. |
| `cve_shell_command_injection_write_to_file.pddl` | Tests command injection vulnerability to write data to a file. |
| `escalate_shell_sideload.pddl` | Tests privilege escalation by sideloading a library into a shell executable. |
| `write_to_file_suid.pddl` | Tests writing data to a sensitive file using an SUID executable. |
| `read_file.pddl` | Tests reading a file using a system executable. |
| `passwd_writable.pddl` | Tests overwriting an entry in `/etc/passwd` to gain control of another user. |
| `add_file_permission.pddl` | Tests adding a write permission to a file owned by the user. |
| `add_directory_permission.pddl` | Tests adding a write permission to a directory owned by the user. |

