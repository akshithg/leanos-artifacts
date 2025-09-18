#! /usr/bin/env bash

# download and extract the Linux kernel source code (v5.15)

set -euo pipefail

[ -d source ] && { echo "[ERROR] ./source directory already exists. Please remove or rename it first."; exit 1; }
if [ -f linux-5.15.tar.xz ]; then
  echo "[INFO] linux-5.15.tar.xz already exists, skipping download."
else
  echo "[INFO] Downloading linux-5.15.tar.xz..."
  wget https://cdn.kernel.org/pub/linux/kernel/v5.x/linux-5.15.tar.xz
fi

echo "[INFO] Extracting..."
tar -xf linux-5.15.tar.xz
mv -f linux-5.15 source

# normalize backslashes in the source tree (for easy trace to source to config mapping)
echo "[INFO] Normalizing backslashes in source files..."
python3 normalize_backslashes.py source normalized_source
mv -f normalized_source source

echo "[OK] Linux kernel source v5.15 downloaded and extracted to ./source and normalized."
