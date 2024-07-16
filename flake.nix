{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/release-24.05";
    powerlifted-flake.url = "github:peperunas/planner8";
    flake-utils.url = "github:numtide/flake-utils";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, powerlifted-flake, poetry2nix }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        };

        ponix = poetry2nix.lib.mkPoetry2Nix { inherit pkgs; };
        inherit (ponix) mkPoetryEnv;

        powerlifted = powerlifted-flake.packages.${system}.powerlifted;

        shellWithPkgs = packages:
          pkgs.mkShell {
            inherit packages;
            buildInputs = [
              (mkPoetryEnv {
                projectDir = self;
                python = pkgs.python312;
                preferWheels = true;
                overrides = ponix.overrides.withDefaults (self: super: {
                  bcrypt = super.bcrypt.override (old: {
                    preferWheel = false;
                  });
                  gcs-oauth2-boto-plugin = super.gcs-oauth2-boto-plugin.overridePythonAttrs (old: {
                    buildInputs = (old.buildInputs or [ ]) ++ [ super.setuptools ];
                  });
                  gsutil = super.gsutil.overridePythonAttrs (old: {
                    buildInputs = (old.buildInputs or [ ]) ++ [ super.setuptools ];
                  });
                  python-gflags = super.python-gflags.overridePythonAttrs (old: {
                    buildInputs = (old.buildInputs or [ ]) ++ [ super.setuptools ];
                  });
                });
              })
            ];
          };
        shell = with pkgs; shellWithPkgs [
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
