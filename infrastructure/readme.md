# Infrastructure

Replication only depends on Docker and Docker Compose.

The rest of the infrastructure (Linux kernel source, QEMU, etc.) is automatically fetched and set up using the provided `Makefile`.

## Dockerized Ubuntu Env

Docker + Compose environment for compiling/building projects within a Linux environment. Primarily intended for building the Linux kernel from source.
Add additional packages in the commented apt-get section of `Dockerfile`.

### Inside the container

The working directory is `/work` which contains the following volume mounts from the host (host -> container):

- `./src -> /work/src`
- `./build -> /work/build`
- `./out -> /work/out`

### Quick start

```sh
cp .env.sample .env    # optional
make up                # build + start container
make shell             # open a shell in the container
make down              # stop container
make clean             # remove host build/ and out/
```
