{
  lib,
  buildPythonPackage,

  # build-system
  uv-build,

  # nativeBuildInputs
  beets-minimal,

  # tests
  mediafile,
}:

buildPythonPackage (finalAttrs: {
  pname = "beets-myplugins";
  version = "0.1.0";
  pyproject = true;

  src = ./.;

  build-system = [
    uv-build
  ];

  nativeBuildInputs = [
    beets-minimal
  ];

  dependencies = [
    mediafile
  ];

  nativeCheckInputs = [
    mediafile
  ];

  meta = {
    license = lib.licenses.mit;
    inherit (beets-minimal.meta) platforms;
  };
})
