# Infrastructure

.PHONY: up shell down
COMPOSE ?= docker compose
SERVICE ?= buildenv
COMPOSE_FILE ?= ./infrastructure/docker-compose.yml

up:
	$(COMPOSE) -f $(COMPOSE_FILE) up -d --build $(SERVICE)

shell:
	@$(COMPOSE) -f $(COMPOSE_FILE) exec $(SERVICE) bash 2>/dev/null || $(COMPOSE) run --rm $(SERVICE) bash

down:
	$(COMPOSE) -f $(COMPOSE_FILE) down


# Kernel
.PHONY: prepare prepare-python-env prepare-kernel-src

prepare: prepare-python-env prepare-kernel-src

prepare-python-env:
	@uv sync
	@echo "Run: \"source .venv/bin/activate\" to activate the virtual environment"

prepare-kernel-src:
	@cd artifacts/linux && ./fetch-linux.sh


# Clean
.PHONY: clean clean-linux clean-python-env clean-builds
clean: clean-linux clean-python-env clean-builds

clean-python-env:
	@rm -rf .venv

clean-linux:
	@rm -rf artifacts/linux/source artifacts/linux/linux-5.15.tar.xz

clean-builds:
	@rm -rf claims/**/build
