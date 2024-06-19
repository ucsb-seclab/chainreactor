# Using Nix for development

Nix is a powerful package manager for Linux and other Unix systems that makes package management reliable and reproducible. It provides atomic upgrades and rollbacks, side-by-side installation of multiple versions of a package, multi-user package management and easy setup of build environments.

This repository uses a `flake.nix` file, which describes the project's dependencies and how to build it. The preferred way to bootstrap the development environment is to use Nix.

## Installing Nix

If Nix is not already installed on your system, you can install it using the [Determinate Systems installer](https://github.com/DeterminateSystems/nix-installer).

```bash
curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install
```

You can verify that Nix was installed correctly by running `nix --version`.

## Entering the Development Environment

Once Nix is installed, you can enter the development environment for this repository.

1. Navigate to the root directory of this repository in your terminal.

2. Run the following command:

```bash
nix develop
```

This command reads the `flake.nix` file and sets up the development environment as described in that file. You are now in the development environment and can begin developing.

# Using the Fact Extractor

The Fact Extractor is a Python script used to extract system facts which are later processed into PDDL problem with predicates and objects. It either expects a reverse connection to a shell or connects to a bind shell on a remote system.

The Fact Extractor is included as part of the development environment setup by the `flake.nix` file. Once you've entered the development environment, you can use the Fact Extractor as follows:

## Usage

```
usage: main.py [-h] -p P [-t T] -d D (-l | -r)

Run phases on an IP address

options:
  -h, --help  show this help message and exit
  -p P        Port to connect or listen on (depending on -r or -l)
  -t T        Target to connect to (to be used with -r)
  -d D        Reference PDDL domain file
  -l          Bind to a port - listen for reverse shell connections
              instead of connecting to host
  -r          Connect back to host's exposed shell
```

## Examples

To use the Fact Extractor to connect to a remote shell on a target host `192.168.1.2` on port `5000` with the reference PDDL domain file `domain.pddl`, you would run:

```bash
main.py -p 5000 -t 192.168.1.2 -d domain.pddl -r
```

To use the Fact Extractor to listen for reverse shell connections on port `5000` with the reference PDDL domain file `domain.pddl`, you would run:

```bash
main.py -p 5000 -d domain.pddl -l
```

Remember to replace the port, target IP address, and PDDL domain file with your actual values.

After running the Fact Extractor, you will have a set of generated problems under the directory `generated_problems/`. The problems can then be fed to any PDDL 2.1 planner for solving.
