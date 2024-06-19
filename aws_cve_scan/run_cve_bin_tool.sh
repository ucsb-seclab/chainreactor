#!/usr/bin/env bash

# needed for pip's user installations
export PATH=$PATH:$HOME/.local/bin

install_packages() {
    echo "Installing pip..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y python3-pip
    elif command -v yum >/dev/null 2>&1; then
        sudo yum install -y python3-pip
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3-pip
    elif command -v zypper >/dev/null 2>&1; then
        sudo zypper install -y python3-pip
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Syu python-pip
    else
        echo "Unsupported package manager. Could not install pip."
        exit 1
    fi
    echo "Done."
}

# Check if arguments are provided
if [ $# -eq 0 ]; then
    echo "No arguments provided. Please provide a path for cve-bin-tool."
    exit 1
fi

path_to_scan=$1

# If cve-bin-tool is installed, skip installation
if command -v cve-bin-tool >/dev/null 2>&1; then
    echo "cve-bin-tool is already installed."
else
    if command -v pip >/dev/null 2>&1; then
        echo "pip is already installed."
    else
        install_packages
    fi

    echo "Installing cve-bin-tool..."
    python3 -m pip install cve-bin-tool
fi

echo "Launching cve-bin-tool..."

mkdir -p ~/.cache/cve-bin-tool && cve-bin-tool --import "cve-bin-tool.sqlite"
cve-bin-tool --offline -o output.json -f json $path_to_scan