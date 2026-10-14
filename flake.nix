{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flakelight = {
      url = "github:m15a/flakelight-treefmt";
      inputs.flakelight.inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };
  outputs =
    {
      self,
      flakelight,
      pyproject-nix,
      ...
    }:
    let
      project = pyproject-nix.lib.project.loadPyproject { projectRoot = ./.; };
    in
    flakelight ./. {
      inputs.self = self;
      devShell =
        pkgs:
        let
          python = pkgs.python3;
          arg = project.renderers.withPackages { inherit python; };
          pythonEnv = python.withPackages arg;
        in
        {
          packages =
            with pkgs;
            [
              nixd
              ty
            ]
            ++ [ pythonEnv ];
        };
      treefmtConfig = {
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
      perSystem =
        pkgs:
        let
          python = pkgs.python3;
          attrs = project.renderers.buildPythonPackage { inherit python; };
        in
        {
          packages.default = python.pkgs.buildPythonPackage attrs;
        };
    };
}
