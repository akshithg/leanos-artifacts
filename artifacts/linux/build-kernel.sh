#!/usr/bin/env bash
#
# Simple x86_64 Linux kernel build helper
# Usage:
#   ./build-kernel.sh <SRC_DIR> <BUILD_DIR> <CONFIG|Make Target>
#
# Examples:
#   ./build-kernel.sh ./source ./builds/abc ./configs/abc.config
#   ./build-kernel.sh ./source ./builds/defconfig defconfig

set -euo pipefail

### ---- helpers ----
err()  { echo -e "\e[31m[ERROR]\e[0m $*" >&2; }
info() { echo -e "\e[34m[INFO]\e[0m  $*"; }

cores() {
  nproc
}

### ---- args & validation ----
if [[ $# -lt 3 ]]; then
  err "Usage: $0 <SRC_DIR> <BUILD_DIR> <CONFIG|Make Target>"
  exit 1
fi

SRC_DIR="$1"
BUILD_DIR="$2"
CONFIG_ARG="$3"

if [[ ! -d "$SRC_DIR" ]]; then
  err "Source directory not found: $SRC_DIR"
  exit 1
fi

mkdir -p "$BUILD_DIR"

SRC_DIR_ABS="$(realpath "$SRC_DIR")"
BUILD_DIR_ABS="$(realpath "$BUILD_DIR")"

MAKE_JOBS="${MAKE_JOBS:-$(cores)}"
MAKE_OPTS=(-C "$SRC_DIR_ABS" O="$BUILD_DIR_ABS" -j"$MAKE_JOBS")

### ---- configuration step ----
if [[ -f "$CONFIG_ARG" ]]; then
  # CONFIG_ARG is a valid file -> treat it as a config file
  CONFIG_ABS="$(realpath "$CONFIG_ARG")"
  info "Using provided config file: $CONFIG_ABS"
  cp "$CONFIG_ABS" "$BUILD_DIR_ABS/.config"

  info "Running 'olddefconfig' to fill in any missing symbols..."
  make -C "$SRC_DIR_ABS" O="$BUILD_DIR_ABS" olddefconfig
else
  # CONFIG_ARG is NOT a file -> treat it as a make target
  info "Using make target: $CONFIG_ARG"
  make -C "$SRC_DIR_ABS" O="$BUILD_DIR_ABS" "$CONFIG_ARG"
fi

### ---- build step ----
LOG_FILE="$BUILD_DIR_ABS/build.log"
info "Building kernel (jobs=$MAKE_JOBS). Logs: $LOG_FILE"

{
  echo "=== $(date) ==="
  echo "SRC_DIR=$SRC_DIR_ABS"
  echo "BUILD_DIR=$BUILD_DIR_ABS"
  echo "JOBS=$MAKE_JOBS"
  echo

  # Build kernel image and modules
  make "${MAKE_OPTS[@]}" menuconfig
  make "${MAKE_OPTS[@]}"
  # make "${MAKE_OPTS[@]}" modules
} | tee "$LOG_FILE"

### ---- results ----
KERNEL_IMAGE="$BUILD_DIR_ABS/arch/x86/boot/bzImage"

if [[ -f "$KERNEL_IMAGE" ]]; then
  info "Kernel image built successfully: $KERNEL_IMAGE"
else
  err "Kernel build finished but no bzImage found. Check $LOG_FILE for errors."
  exit 1
fi

info "Done."
