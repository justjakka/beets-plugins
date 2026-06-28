{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    treefmt-nix.url = "github:numtide/treefmt-nix";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    inputs@{
      flake-parts,
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      ...
    }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [ inputs.treefmt-nix.flakeModule ];
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      perSystem =
        { pkgs, lib, ... }:
        let
          workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
          overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
          python = lib.head (
            pyproject-nix.lib.util.filterPythonInterpreters {
              inherit (workspace) requires-python;
              inherit (pkgs) pythonInterpreters;
            }
          );
          pythonBase = pkgs.callPackage pyproject-nix.build.packages { inherit python; };
          pyprojectOverrides = final: prev: {
            numba = prev.numba.overrideAttrs (old: {
              buildInputs = (old.buildInputs or [ ]) ++ [ pkgs.tbb ];
            });
          };
          pythonSet = pythonBase.overrideScope (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.wheel
              overlay
              pyprojectOverrides
            ]
          );
          editableOverlay = workspace.mkEditablePyprojectOverlay { root = "$REPO_ROOT"; };

          editablePythonSet = pythonSet.overrideScope editableOverlay;

          virtualenv = editablePythonSet.mkVirtualEnv "beetsplug" workspace.deps.all;
        in
        {
          packages.default = pkgs.callPackage ./package.nix {
            inherit (pkgs.python313Packages) buildPythonPackage mediafile beets-minimal;
            uv-build = pythonSet.uv-build or pkgs.uv;
          };
          devShells.default = pkgs.mkShell {
            packages =
              with pkgs;
              [
                nixd
                nixfmt
                ruff
                ty
                uv
              ]
              ++ virtualenv.buildInputs;
            env = {
              UV_NO_SYNC = "1";
              UV_PYTHON = pythonSet.python.interpreter;
              UV_PYTHON_DOWNLOADS = "never";
            };
            shellHook = ''
              unset PYTHONPATH
              export REPO_ROOT=$(git rev-parse --show-toplevel)
            '';
          };
          treefmt = {
            projectRootFile = "flake.nix";
            programs = {
              nixfmt = {
                enable = true;
                strict = true;
              };
              ruff = {
                check = true;
                format = true;
              };
            };
          };
        };
    };
}
