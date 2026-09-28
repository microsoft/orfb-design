# ORFB Design network — standardized build & launch.
#
# The graphormer / retrochimera server images bake in model checkpoints staged
# under model-assets/ (git-ignored). Graphormer checkpoints are copied from
# caller-supplied local paths; RetroChimera comes from public Figshare.
#
# Quick start:
#   export GRAPHORMER_REDUCTION_CHECKPOINT_SOURCE=/path/to/reduction.pt
#   export GRAPHORMER_OXIDATION_CHECKPOINT_SOURCE=/path/to/oxidation.pt
#   make up           # fetch checkpoints -> build base image -> build & launch
#
# Individual steps:
#   make checkpoints             # stage all checkpoints (idempotent)
#   make graphormer-checkpoints  # copy caller-supplied local files
#   make retrochimera-checkpoint # download the public Figshare artifact
#   make ezbattery-source        # fetch the pinned upstream EZBattery source
#   make base-image   # build the shared base image (mcp-server-base:local)
#   make build        # checkpoints + base-image + docker compose build
#   make up           # build + docker compose up -d
#   make down         # stop and remove the network
#   make ps / logs    # inspect the running network

SHELL := /bin/bash

AGORA_WORKBENCH_VERSION ?= 0.3.1
BASE_IMAGE              ?= mcp-server-base:local
BASE_DOCKERFILE         := deployment/docker/base.Dockerfile

# Marker files let Make skip already-staged checkpoints without re-shelling out.
GRAPHORMER_REDUCTION_CKPT := model-assets/graphormer/reduction_checkpoint_best.pt
GRAPHORMER_OXIDATION_CKPT := model-assets/graphormer/oxidation_checkpoint_best.pt
RETRO_CKPT                := model-assets/retrochimera/pistachio/models.json

.PHONY: all up build base-image checkpoints graphormer-checkpoints retrochimera-checkpoint ezbattery-source down ps logs clean-checkpoints

all: up

## Stage all model checkpoints into model-assets/ (idempotent).
checkpoints:
	scripts/fetch_checkpoints.sh all

graphormer-checkpoints:
	scripts/fetch_checkpoints.sh graphormer

retrochimera-checkpoint:
	scripts/fetch_checkpoints.sh retrochimera

ezbattery-source:
	scripts/fetch_ezbattery_source.sh

$(GRAPHORMER_REDUCTION_CKPT) $(GRAPHORMER_OXIDATION_CKPT):
	scripts/fetch_checkpoints.sh graphormer

$(RETRO_CKPT):
	scripts/fetch_checkpoints.sh retrochimera

## Build the Agora Workbench base image the domain/hub images extend.
base-image:
	docker build \
	  --build-arg AGORA_WORKBENCH_VERSION="$(AGORA_WORKBENCH_VERSION)" \
	  -f "$(BASE_DOCKERFILE)" \
	  -t "$(BASE_IMAGE)" \
	  .

## Fetch checkpoints, build the base image, then build all service images.
build: $(GRAPHORMER_REDUCTION_CKPT) $(GRAPHORMER_OXIDATION_CKPT) $(RETRO_CKPT) base-image
	mkdir -p published_artifacts && chmod 1777 published_artifacts
	docker compose build

## Build everything and launch the full network in the background.
up: build
	docker compose up -d

## Stop and remove the network.
down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f --tail=50

## Remove staged checkpoints (forces a re-fetch on the next build).
clean-checkpoints:
	rm -rf model-assets .cache/checkpoints
