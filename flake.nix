{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/release-23.05";
    powerlifted-flake.url = "github:peperunas/planner8";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, powerlifted-flake }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

        powerlifted = powerlifted-flake.packages.${system}.powerlifted;

        shellWithPkgs = packages: pkgs.mkShell {
          inherit packages;
          shellHook = ''
            poetry update && poetry shell
          '';
        };

        shell = with pkgs; shellWithPkgs [
          poetry
          powerlifted
          parallel-full
          sqlite
        ];
      in
      {
        devShell = shell;
        defaultPackage = shell;
      });
}
