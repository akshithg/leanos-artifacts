# Artifacts: "In Pursuit of Lean OS Kernels: Improving Configuration-Based Debloating"

This repo contains all the code artifacts for the paper "In Pursuit of Lean OS Kernels: Improving Configuration-Based Debloating" presented at ACSAC 2025.

## Infrastructure Requirements

Docker + Docker Compose

```bash
# build and start the docker image/container and test environment
make up

# stop the container
make down

# enter the container, the current working directory will be mounted to /work in the container
make shell

# prepare the python env, and linux src + build environment
make prepare # inside the container

# clean up for a fresh start
make clean   # inside the container
```

## Overview

```txt
artifacts/
├── linux/                  # Linux kernel source and build environment
│   ├── source              # Linux kernel source (v5.15)
│   └── builder             # Scripts to build and test the kernel
│
├── tracie/                 # Trace-based approach: Tracie
│   ├── qemu.patch          # Patch for QEMU to support Tracie's tracing mechanism
│   ├── cr3-kmod/           # Kernel module to log CR3 values for filtering user-space noise
│   ├── kconfig_db.py       # Script to build the config.db database
│   ├── config.db           # Database mapping config options to source files and line numbers
│   ├── trace2config.py     # Script to map execution traces to kernel config options
│   └── config-solver.py    # Script to compute a minimal kernel config using a SAT solver
│
├── dice/                   # Trace-free approach: Dice
│   └── dice.py             # Script that iteratively prunes the kernel config tree/graph
│
├── uv.lock                 # Python environment lock file
├── Makefile                # Makefile
├── LICENSE                 # License file
└── readme.md               # This file
```

## System 1: Tracie

```mermaid
flowchart LR
    subgraph TRACIE["Trace-Based Approach: TRACIE"]
        A1["Instrumented Kernel Run (QEMU + CR3 Filtering)"]
        A2["Runtime Execution Trace (PC Addresses)"]
        A3["Source Mapping (addr2line, debug info)"]
        A4["Config Expression Extraction (#ifdef, CONFIG)"]
        A5["SAT-Based Resolution"]
        A6["Specialized Config Generation"]
        A7["Build and Validate Kernel"]

        A1 --> A2 --> A3 --> A4 --> A5 --> A6 --> A7
    end
```

### Trace Artifact Overview

Code:

- [qemu.patch](./artifacts/tracie/qemu.patch): Patch for QEMU to support Tracie's tracing mechanism (PC + CR3).
- [cr3-kmod](./artifacts/tracie/cr3-kmod/): Kernel module to log CR3 values for filtering user-space noise from workload kernel traces.
- [kconfig_db.py](./artifacts/tracie/kconfig_db.py): Script to build the [config.db](./artifacts/tracie/config.db) database from the Linux kernel source which maps config options to source files and line numbers.
- [trace2config.py](./artifacts/tracie/trace2config.py): Script to map execution traces to kernel configuration options.
- [config_solver.py](./artifacts/tracie/config_solver.py): Script to compute a minimal kernel configuration based on traced options using a SAT solver.

Data:

- [config.db](./artifacts/tracie/config.db): Database mapping kernel configuration options to source files and line numbers.

## System 2: Dice

```mermaid
flowchart TD
    subgraph DICE["Trace-Free Approach: DICE"]
        B1["Baseline Config (localmodconfig)"]
        B2["Config Dependency Graph (Kconfiglib)"]
        B3["Heuristic Grouping (Leafs, SCCs, Menus)"]
        B4["Group-Wise Pruning + Bisection"]
        B5["Iterative Build + Boot + Test"]
        B6["Final Validated Config"]

        B1 --> B2 --> B3 --> B4 --> B5 --> B6
    end
```

### Dice Artifact Overview

Code:

- [dice.py](./artifacts/dice/dice.py): Script that iteratively prunes the kernel configuration tree/graph to remove unused options.


## Claim

We share steps to reproduce the claims in the paper in the readme located in [claims/claim1/readme.md](./claims/claim1/readme.md).
