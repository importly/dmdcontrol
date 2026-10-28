#!/bin/bash
set -euo pipefail

# Needs: cmake gcc-c++ git python3-devel boost-devel libusb1-devel opencv-devel
#   hdf5-devel glew-devel glfw-devel protobuf-devel gtest-devel gmock-devel libcanberra-gtk3, uv,
#   and OpenEB's udev rules 88-cyusb.rules + 99-evkv2.rules in /etc/udev/rules.d for USB access.

OPENEB_TAG="5.2.0"
OPENEB_DIR="$HOME/openeb"
BUILD_DIR="$OPENEB_DIR/build-py314"
BUILD_VENV="$OPENEB_DIR/py314venv"
UV="${UV:-$HOME/.local/bin/uv}"

log() { echo "[openeb] $*"; }

if [ ! -d "$OPENEB_DIR/.git" ]; then
  log "cloning OpenEB $OPENEB_TAG into $OPENEB_DIR"
  git clone --depth 1 -b "$OPENEB_TAG" https://github.com/prophesee-ai/openeb.git "$OPENEB_DIR"
fi

if [ ! -x "$BUILD_VENV/bin/python" ]; then
  log "creating build venv $BUILD_VENV"
  "$UV" venv --python /usr/bin/python3.14 "$BUILD_VENV"
  "$UV" pip install --python "$BUILD_VENV/bin/python" "pybind11>=3"
fi
PY="$BUILD_VENV/bin/python"

log "configuring $BUILD_DIR"
# GCC 15 needs -include cstdint, and OpenEB's CMake only finds Python <= 3.12 on its own
cmake -S "$OPENEB_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF \
  -DPython3_EXECUTABLE="$PY" -DPython3_FIND_VIRTUALENV=ONLY \
  -Dpybind11_DIR="$("$PY" -m pybind11 --cmakedir)" \
  -DCMAKE_CXX_FLAGS="-include cstdint"

log "building (a clean build takes ~5 min)"
cmake --build "$BUILD_DIR" --config Release -j "$(( $(nproc) * 2 / 3 ))"
log "done: $BUILD_DIR"
