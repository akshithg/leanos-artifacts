#!/bin/bash

# Script to run a Linux kernel in QEMU with KVM acceleration and host CPU passthrough
#
# Usage:
#   ./run-kernel.sh <kernel> <disk> <extra_init_args> <outdir>
#
# Example:
#   ./run-kernel.sh ./bzImage ./debian.qcow2 "init=/bin/bash debug" ./logs
#
# Default init args:
#   nokaslr panic=-1 console=ttyS0 root=/dev/sda rw
#
# Final kernel command line will be:
#   "nokaslr panic=-1 console=ttyS0 root=/dev/sda rw <extra_init_args>"

set -euo pipefail

# --- Input Validation ---
if [ "$#" -ne 4 ]; then
    echo "Usage: $0 <kernel> <disk> <extra_init_args> <outdir>"
    exit 1
fi

KERNEL="$1"
DISK="$2"
EXTRA_INIT_ARGS="$3"
OUTDIR="$4"

# --- Default Init Arguments ---
DEFAULT_INIT_ARGS="raid=noautodetect nokaslr panic=-1 console=ttyS0 root=/dev/sda rw"

# Combine default with extra args
FINAL_INIT_ARGS="${DEFAULT_INIT_ARGS} ${EXTRA_INIT_ARGS}"

# --- Prepare Output Directory ---
mkdir -p "$OUTDIR"

# Log file
LOGFILE="${OUTDIR}/qemu-$(date +%Y%m%d-%H%M%S).log"

# --- Run QEMU ---
echo "[INFO] Running kernel with QEMU..."
echo "[INFO] Kernel: $KERNEL"
echo "[INFO] Disk: $DISK"
echo "[INFO] Kernel boot params: $FINAL_INIT_ARGS"
echo "[INFO] Logs will be saved to: $LOGFILE"

qemu-system-x86_64 \
    -machine pc,accel=kvm \
    -cpu host \
    -m 8G \
    -smp 4 \
    -kernel "$KERNEL" \
    -append "$FINAL_INIT_ARGS" \
    -drive file="$DISK",format=raw \
    -net nic,model=virtio \
    -net user \
    -no-reboot \
    -nographic \
    2>&1 | tee "$LOGFILE"

echo "[INFO] QEMU exited. Logs saved to: $LOGFILE"
