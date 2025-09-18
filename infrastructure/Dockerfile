FROM ubuntu:22.04

# Noninteractive APT and locale
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Build args to align container user with host UID/GID
ARG BUILDER_UID=1003
ARG BUILDER_GID=1003
ARG BUILDER_USER=builder
ARG BUILDER_GROUP=builder

# Create user and base folders
RUN set -eux; \
    groupadd -g "${BUILDER_GID}" "${BUILDER_GROUP}"; \
    useradd -m -u "${BUILDER_UID}" -g "${BUILDER_GID}" -s /bin/bash "${BUILDER_USER}"; \
    mkdir -p /work/src /work/build /work/out; \
    chown -R "${BUILDER_USER}:${BUILDER_GROUP}" /work

# Install your build dependencies here
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        autoconf automake bc bison build-essential cmake curl dwarves flex \
        g++ gcc git libelf-dev libncurses-dev libssl-dev libtool make meson \
        ninja-build pkg-config python3 python3-pip rsync wget zstd \
        && rm -rf /var/lib/apt/lists/*

RUN pip3 install uv

# Standardized directories
ENV WORKDIR=/work
WORKDIR ${WORKDIR}

# Use non-root by default
USER ${BUILDER_USER}

CMD ["bash"]
