# Claim: Kernel Size Reduction




Build kernel with configs in `/artifacts/linux/configs/`. Each corresponding to the reduction method presented in the paper.

Size for the kernel text `size -A ./build/<id>/vmlinux | grep .text` should correspond to the Table 1 Debloating Evaluation (Kenrel Size).

Small deviations may occur due to different compiler version.
