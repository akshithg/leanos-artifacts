#!/bin/bash

echo "make sure you are running this within the container/docker"

LINUX_SRC_DIR="../../artifacts/linux/source"

function build_kernel() {
    local config_file=$1
    local build_name=$(basename $config_file .config)
    local build_id=${build_name//./_}  # replace dots with underscores for directory

    if [ -f ./build/$build_id/vmlinux ]; then
        echo "Kernel for config $config_file already built. Skipping."
        return
    fi

    echo "Building kernel with config: $config_file"

    mkdir -p ./build/$build_id
    cp $config_file ./build/$build_id/.config

    make -j$(nproc) -C $LINUX_SRC_DIR O=$(pwd)/build/$build_id olddefconfig
    make -j$(nproc) -C $LINUX_SRC_DIR O=$(pwd)/build/$build_id
    echo "Kernel built at ./build/$build_id/vmlinux"
}

function get_kernel_text_size() {
    local build_id=$1
    # local text_size=$(size -A ./build/$build_id/vmlinux | grep .text | awk '{print $2}')
    text_size=$(size -A ./build/$build_id/vmlinux | grep '\.text' | awk '{sum += $2} END {printf "%.2f MB\n", sum/1024/1024}')
    echo "Kernel text size for build $build_id: $text_size"
}

CONFIG_DIR="../../artifacts/linux/configs"
SIZE_OUTPUT_FILE="./kernel_sizes.txt"

for config_file in $CONFIG_DIR/*.config; do
    # skip ubuntu config
    if [[ $(basename $config_file) == *"ubuntu"* ]]; then
        echo "Skipping ubuntu config: $config_file"
        continue
    fi
    build_kernel $config_file
    build_name=$(basename $config_file .config)
    build_id=${build_name//./_}
    get_kernel_text_size $build_id >> $SIZE_OUTPUT_FILE
done
