<p align="center">
  <img src=images/logo.png alt="Logo" width=250px />
</p>

---


# ChainReactor: Automated Privilege Escalation Chain Discovery via AI Planning

ChainReactor is a research project that leverages AI planning to discover exploitation chains for privilege escalation on Unix systems. The project models the problem as a sequence of actions to achieve privilege escalation from initial access to a target system. This repository contains the open-source implementation of the system described in the paper "ChainReactor: Automated Privilege Escalation Chain Discovery via AI Planning."

**We are proud to announce that ChainReactor was presented at USENIX Security 24 and received the Distinguished Artifact Award!**

## Overview

ChainReactor automates the discovery of privilege escalation chains by:
- Extracting information about available executables, system configurations, and known vulnerabilities on the target system.
- Encoding this data into a Planning Domain Definition Language (PDDL) problem.
- Using a modern planner to generate chains that incorporate vulnerabilities and benign actions.

The tool has been evaluated on synthetic vulnerable VMs, Amazon EC2, and Digital Ocean instances, demonstrating its capability to rediscover known exploits and identify new chains.

## Citation

If you use ChainReactor in your research or wish to refer to it, please use the following citation:

```bibtex
@inproceedings {depasquale_chainreactor,
author = {Giulio De Pasquale and Ilya Grishchenko and Riccardo Iesari and Gabriel Pizarro and Lorenzo Cavallaro and Christopher Kruegel and Giovanni Vigna},
title = {{ChainReactor}: Automated Privilege Escalation Chain Discovery via {AI} Planning},
booktitle = {33rd USENIX Security Symposium (USENIX Security 24)},
year = {2024},
isbn = {978-1-939133-44-1},
address = {Philadelphia, PA},
pages = {5913--5929},
url = {https://www.usenix.org/conference/usenixsecurity24/presentation/de-pasquale},
publisher = {USENIX Association},
month = aug
}
```

The full paper is available at: [https://www.usenix.org/conference/usenixsecurity24/presentation/de-pasquale](https://www.usenix.org/conference/usenixsecurity24/presentation/de-pasquale)

## Using Nix for development

Nix is a powerful package manager for Linux and other Unix systems that makes package management reliable and reproducible. It provides atomic upgrades and rollbacks, side-by-side installation of multiple versions of a package, multi-user package management and easy setup of build environments.

This repository uses a `flake.nix` file, which describes the project's dependencies and how to build it. The preferred way to bootstrap the development environment is to use Nix.

### Installing Nix

If Nix is not already installed on your system, you can install it using the [Determinate Systems installer](https://github.com/DeterminateSystems/nix-installer).

```bash
curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install
```

You can verify that Nix was installed correctly by running `nix --version`.

### Enabling and Configuring Flakes

Flakes are an experimental feature in Nix and need to be explicitly enabled. Here's how to enable and configure flakes:

### Temporary Enablement
To enable flakes temporarily for a single command, add the following options:

```bash
--experimental-features 'nix-command flakes'
```

For example:

```bash
nix --experimental-features 'nix-command flakes' develop
```

#### Permanent Enablement

To enable flakes permanently, you have several options depending on your setup:

##### For NixOS

Add the following to your system configuration:

```nix
nix.settings.experimental-features = [ "nix-command" "flakes" ];
```

#### For other distros using Home-Manager

Add the following to your home-manager config:

```nix
nix = {
  package = pkgs.nix;
  settings.experimental-features = [ "nix-command" "flakes" ];
};
```

##### For other distros without Home-Manager 

Add the following to `~/.config/nix/nix.conf` or `/etc/nix/nix.conf`:

```
experimental-features = nix-command flakes
```

After making these changes, restart the Nix daemon or reboot your system for the changes to take effect.

### Entering the Development Environment

Once Nix is installed, you can enter the development environment for this repository.

1. Navigate to the root directory of this repository in your terminal.

2. Run the following command:

```bash
nix develop
```

This command reads the `flake.nix` file and sets up the development environment as described in that file. You are now in the development environment and can begin developing / testing / using Chain Reactor.

## Domain Description

The `domain.pddl` file defines the planning domain for the ChainReactor project. It specifies the types, constants, predicates, and actions used to model the privilege escalation problem in a Unix system.

### Types

The domain defines several types of objects:

- `file`, `data`, `location`, `user`, `group`, `permission`, `process`, `purpose` - general object types.
- `executable` - a subtype of `file`.
- `local`, `remote`, `directory` - subtypes of `location`.

### Constants

The domain includes some constants:

- `FS_READ`, `FS_WRITE`, `FS_EXEC` - permissions.
- `SHELL` - indicates a file has been corrupted by the attacker.
- `SYSFILE_PASSWD` - indicates a file acts like the `/etc/passwd` file on Linux.

### Predicates

Predicates define the properties and relationships between objects:

- Capabilities of executables (e.g., `(CAP_write_file ?e - executable)`).
- User and group properties (e.g., `(user_is_admin ?u - user)`, `(controlled_user ?u - user)`).
- File and directory properties (e.g., `(file_owner ?f - file ?u - user ?g - group)`, `(directory_owner ?d - directory ?u - user ?g - group)`).
- Process-related predicates (e.g., `(process_executable ?p - process ?u - user ?e - executable)`).
- Composed predicates generated by actions (e.g., `(user_can_read_file ?u - user ?g - group ?f - file)`).

### Actions

Actions define how the state of the system can change. Each action includes parameters, preconditions, and effects:

- **File Manipulation Actions**:
  - `propagate_loaded_file_contents`: Propagates file contents from one file to another.
  - `write_data_to_file`: Writes arbitrary data to a file.
  - `read_file`: Reads the contents of a file and stores them in a buffer.

- **Permission and Ownership Actions**:
  - `make_executable_suid`: Makes an executable SUID.
  - `change_file_owner`: Changes the owner of a file.
  - `add_permission_of_owned_file`: Adds a permission to a file owned by the user.

- **Process and Execution Actions**:
  - `spawn_process`: Spawns a process from an executable.
  - `spawn_suid_process`: Spawns a process from a SUID executable.
  - `spawn_shell`: Spawns a shell from an executable with the `CAP_shell` capability.

- **Network and Data Transfer Actions**:
  - `download_file`: Downloads a file from a remote location to a local location.
  - `upload_file`: Uploads a file from a local location to a remote location.

- **Assumptions and Derived Actions**:
  - `assume_executable_with_cap_command_has_other_capabilities`: Assumes an executable with the `COMMAND` capability has other capabilities.
  - `derive_user_can_read_file`: Derives that a user can read a file based on various conditions.

### CVE-Specific Actions

The domain includes actions related to specific CVEs:

- `derive_executable_with_cap_cve_shell_command_injection_has_other_capabilities`: Derives capabilities for an executable vulnerable to shell command injection.
- `check_cve_shell_command_injection_needs_writable_directory`: Checks if a writable directory is needed for shell command injection.
- `derive_user_can_read_anything_from_executable_with_CAP_CVE_read_any_file`: Derives that a user can read any file using an executable with the capability to read any file.
- `write_data_to_file_using_executable_with_CAP_CVE_write_any_file`: Writes data to a file using an executable with the capability to write any file.

## Components

### The BFG9000

The `bfg9000.py` script is an end-to-end script designed to automate the entire process of running the ChainReactor project. This includes spawning instances, extracting system facts via the Facts Extractor, generating PDDL problems, and solving these problems with Powerlifted. The script supports both AWS and Digital Ocean instances.

This is the overview of what the BFG wraps up:

1. **Initialize the Connection**: Depending on the connection method chosen (reverse shell, bind shell, or SSH), the script will establish a connection to the target system.
2. **Extract Facts**: The script will extract system facts, including users, groups, executables, writable files, SUID/SGID files, and vulnerabilities.
3. **Encode Problems**: The extracted facts are encoded into PDDL problems using the specified domain file.
4. **Save Results**: The encoded problems are saved in the `generated_problems/` directory, and the extracted facts are optionally pickled for reuse.

#### Prerequisites

Before running the `bfg9000.py` script, ensure that you have the necessary modules and dependencies installed. We use `nix` and `poetry` to handle the dependencies. 

If you use Nix, which we strongly recommend, this is all handled automatically when entering the development environment.

#### Usage

The `bfg9000.py` script provides several commands to handle different tasks.

```bash
./bfg9000.py <command> [options]
```

The BFG provides three main commands: `extract`, `cloud`, and `solve`. Each command has specific arguments and options.

### Extract

Establish a connection with the target system, extract system information and generate PDDL problems.

```
usage: bfg9000.py extract [-h] -p PORT [-t TARGET] [-n NAME] [-uc] [-l | -r | -s] [-u USER] [-k KEY]

Extract system information, generate problems, and attempt to solve from a custom connection.

optional arguments:
  -h, --help            show this help message and exit

Extract:
  -p PORT, --port PORT  Port to connect or listen on (depending on -r, -l or SSH)
  -t TARGET, --target TARGET
                        Target to connect to (to be used with -r or SSH)
  -n NAME, --name NAME  Filesystem name for the results (pickled facts and PDDL problems)
  -uc, --unpatched-cves
                        If set, assume CVEs in remote binaries are unpatched

Connection:
  -l, --listen          Listen for reverse shell connection instead of connecting to host
  -r, --reverse         Connect back to host's exposed shell
  -s, --ssh             Connect to the host via SSH
  -u USER, --user USER  SSH user
  -k KEY, --key KEY     SSH private key
```

After running the Fact Extractor, you will have a set of generated problems under the directory `generated_problems/`. The problems can then be fed to any PDDL 2.1 planner for solving - or be solved via the `solve` command. 

The problem filenames reflect the goal of the escalation; in the current state, the problems are appended to the user to whom the planner will try to find an escalation path. For example, `micronix-problem-root.pddl` is the problem whose goal is to escalate to `root`.

#### Local Hosts Examples

1. **Extract facts via a bind shell:**

```sh
./bfg9000.py extract -p 5555 -l
```

In this example, the BFG is set to listen for an incoming connection on port `5555`. This is useful for scenarios where you have control over the target machine and can initiate a reverse shell connection back to the script's listening port. Once the connection is established, the script will extract system information and generate problems based on the gathered data.

2. **Extract facts by connecting to a host with an open shell on port 4444:**

```sh
./bfg9000.py extract -p 4444 -r -t 192.168.1.100
```

In this example, the BFG will connect to a remote host at `192.168.1.100` on port `4444`, where a shell is already listening for incoming connections. This method is helpful if the remote host has a shell exposed on a specific port, allowing the script to connect, extract system information, and generate problems based on the extracted data.

#### Cloud

Spawn, extract system information, generate problems, and attempt to solve a cloud-provided instance.

```
usage: bfg9000.py cloud [-h] [-s SCRIPT] [-uc] {aws,do} image

Spawn, extract system information, generate problems, and attempt to solve a cloud-provided instance.

positional arguments:
  provider              Which cloud provider to use (aws=Amazon, do=Digital Ocean)
  image                 The provider-specific image ID to spawn

optional arguments:
  -h, --help            show this help message and exit
  -s SCRIPT, --script SCRIPT
                        A local script to be executed on the remote instance
  -uc, --unpatched-cves
                        If set, assume CVEs in remote binaries are unpatched
```

#### Examples

1. **Extract facts and solve problems from an AWS instance:**

```sh
./bfg9000.py cloud aws ami-12345678
```

2. **Run a custom script on a Digital Ocean instance:**

```sh
./bfg9000.py cloud do ubuntu-20-04-x64 -s my_script.sh
```

### Solve

Use the PDDL planner to solve a generated problem.

```
usage: bfg9000.py solve [-h] -p PROBLEM

Use the PDDL planner to solve a generated problem.

optional arguments:
  -h, --help            show this help message and exit

Solve:
  -p PROBLEM, --problem PROBLEM
                        Path to the problem file to solve
```

#### Examples

1. **Solve a specific problem:**

```sh
./bfg9000.py solve -p path/to/problem.pddl
```

### Logging and Statistics

The BFG uses a logging module to log essential events and errors; additionally, it maintains a SQLite database (`stats.sqlite`) to store statistics about the runs, including problem generation time and solve time.

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

## Artifacts

We have included artifacts for the exploited AWS and Digital Ocean (DO) instances under the `artifacts` directory. These artifacts consist of:

- Pickle files
- Generated problems
- Generated plans

### Reproducing the Solution

To reproduce the solution, you can run the solver on the generated problems. Here's how to do it:

1. Ensure you have the necessary dependencies installed as described in the "Using Nix for development" section.
2. Navigate to the `generated_problems/` directory.
3. Run the solver on any of the problem files using the following command:

```bash
./bfg9000.py solve -p <PROBLEM_FILE>
```

Replace `<PROBLEM_FILE>` with the path to the problem file you want to solve and `<DOMAIN_FILE>` with the path to the domain file.

### Disclaimer

Please note that we did not include artifacts for 6 missing AWS instances as we had difficulties retrieving them. We apologize for any inconvenience this may cause.

## Acknowledgments

We would like to thank Augusto Blaas Corrêa for his PDDL expertise and support throughout the development of this study. This material is based on research sponsored by DARPA under agreement number N66001-22-2-4037. The U.S. Government is authorized to reproduce and distribute reprints for Governmental purposes notwithstanding any copyright notation thereon. This material is also supported by the National Science Foundation under grant no. 2229876 and is supported in part by funds provided by the National Science Foundation, by the Department of Homeland Security, and by IBM. Partial support was also provided through a gift from Cisco. The views and conclusions contained herein are those of the authors and should not be interpreted as necessarily representing the official policies or endorsements, either expressed or implied, of DARPA or the U.S. Government, or of NSF or its federal agency and industry partners.

