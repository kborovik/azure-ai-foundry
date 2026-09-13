ifeq ($(filter notintermediate,$(.FEATURES)),)
$(error GNU Make ≥ 4.4 required (this is $(MAKE_VERSION) from $(MAKE)). On macOS: brew install make && gmake <target>)
endif

.SILENT:

SHELL := /bin/sh
MAKEFLAGS += --no-builtin-rules --no-builtin-variables
export PATH := $(abspath .venv)/bin:$(PATH)

UV ?= uv
export PYTHONUNBUFFERED := 1

empty :=
space := $(empty) $(empty)
s := $(shell printf '\036')
esc := $(shell printf '\033')
blue := $(esc)[34m
green := $(esc)[32m
yellow := $(esc)[33m
reset := $(esc)[0m

header = $(info $(blue)==> $1 <==$(reset))

# Short flags live in the first MAKEFLAGS word (`nprR`). `-n` is `n` there;
# later words (`--jobserver-auth=...`) also contain `n` and must be ignored.
dry-run = $(findstring n,$(firstword $(MAKEFLAGS)))

need-terraform = $(if $(dry-run),,$(if $(shell command -v terraform),,$(error terraform not on PATH — https://developer.hashicorp.com/terraform/install)))
need-az = $(if $(dry-run),,$(if $(shell command -v az),,$(error az CLI required — https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)))
need-az-auth = $(if $(dry-run),,$(shell az account show >/dev/null 2>&1)$(if $(filter 0,$(.SHELLSTATUS)),,$(error az not authenticated — run: az login)))
need-gh = $(if $(dry-run),,$(if $(shell command -v gh),,$(error gh CLI required — https://cli.github.com/)))
need-gh-auth = $(if $(dry-run),,$(shell gh auth status >/dev/null 2>&1)$(if $(filter 0,$(.SHELLSTATUS)),,$(error gh not authenticated — run: gh auth login)))
need-clean = $(if $(dry-run),,$(if $(shell git status --porcelain),$(error working tree not clean — commit or stash first)))
need-part = $(if $(part),,$(error usage: gmake release major|minor|patch))

ALLOWED_ENVS := dev1 prd1
ENV ?= dev1
AZURE_LOCATION ?= swedencentral
AZURE_SUBSCRIPTION_ID ?= f298e323-efae-4203-ba61-fc3496190479
TFSTATE_RG := rg-credit-policy-tfstate
TFSTATE_CONTAINER := tfstate
TFSTATE_ACCOUNT := sttfstlab5
export ARM_SUBSCRIPTION_ID ?= $(AZURE_SUBSCRIPTION_ID)
export ARM_USE_AZUREAD := true

need-env = $(if $(filter $(ENV),$(ALLOWED_ENVS)),,$(error ENV must be dev1 or prd1 (got $(ENV))))

# Recursive glob. `*` skips dot-dirs (.git, .venv).
rwildcard = $(strip \
	$(wildcard $(1)$(2)) \
	$(foreach d,$(wildcard $(1)*),$(if $(wildcard $(d)/.),$(call rwildcard,$(d)/,$(2)))))

default: help

.PHONY: help test check generate deploy infra infra-backend
.PHONY: infra-create infra-plan infra-fmt infra-validate infra-show infra-destroy infra infra-init
.PHONY: infra-backend-create infra-backend-show infra-backend-destroy infra-backend
.PHONY: e2e clean preflight release major minor patch
.PHONY: _release-pre _release-bump _release-tag _release-gh

###############################################################################
# Tests and local loop
###############################################################################

test: .venv ## Unit tests (no Azure)
	$(call header,Running unit tests)
	$(UV) run pytest

check: .venv ## Format check, lint, unit tests (no Azure)
	$(call header,Checking)
	$(UV) run ruff format --check
	$(UV) run ruff check
	$(MAKE) test

generate: .venv ## Render corpus locally (no Azure)
	$(call header,Generating credit policies)
	$(UV) run talos generate policy --local-only

deploy: .venv ## Provision Foundry IQ + agent (`talos deploy --wait`)
	$(call need-terraform)
	$(call header,Generating client applications)
	$(UV) run talos generate application --all --force --local-only
	$(call header,Deploying Foundry IQ)
	$(UV) run talos deploy --wait

preflight: .venv
	$(call need-az)
	$(call need-terraform)
	$(call need-az-auth)
	$(call header,Azure preflight)
	az account show --query name -o tsv
	terraform version

infra-backend-create:
	$(call need-az)
	$(call need-az-auth)
	$(call header,Checking az auth)
	az account show --query name -o tsv
	$(call header,Creating tfstate backend $(AZURE_LOCATION))
	az group create --name $(TFSTATE_RG) --location $(AZURE_LOCATION) \
		--tags environment=tfstate project=credit-policy-agent \
		--output none
	az storage account create \
		--name $(TFSTATE_ACCOUNT) \
		--resource-group $(TFSTATE_RG) \
		--location $(AZURE_LOCATION) \
		--sku Standard_LRS \
		--kind StorageV2 \
		--min-tls-version TLS1_2 \
		--allow-blob-public-access false \
		--https-only true \
		--access-tier Hot \
		--tags environment=tfstate project=credit-policy-agent \
		--output none
	az storage container create \
		--name $(TFSTATE_CONTAINER) \
		--account-name $(TFSTATE_ACCOUNT) \
		--public-access off \
		--output none
	scope=$$(az storage account show --name $(TFSTATE_ACCOUNT) --resource-group $(TFSTATE_RG) --query id -o tsv); \
	principal=$$(az ad signed-in-user show --query id -o tsv 2>/dev/null || az ad sp show --id "$$(az account show --query user.name -o tsv)" --query id -o tsv); \
	existing=$$(az role assignment list --assignee $$principal --scope $$scope --role "Storage Blob Data Contributor" --query "[0].id" -o tsv); \
	if [ -z "$$existing" ]; then \
	  az role assignment create --assignee $$principal --role "Storage Blob Data Contributor" --scope $$scope --output none; \
	fi
	echo "tfstate account $(TFSTATE_ACCOUNT)"

infra-backend-show:
	$(call need-az)
	$(call need-az-auth)
	$(call header,Showing tfstate backend)
	az group show --name $(TFSTATE_RG)
	az storage account show --name $(TFSTATE_ACCOUNT) --resource-group $(TFSTATE_RG)

infra-backend-destroy:
	$(call need-az)
	$(call need-az-auth)
	$(call header,Deleting tfstate backend)
	az group delete --name $(TFSTATE_RG) --yes

infra-fmt: ## terraform fmt in infra/
	$(call need-terraform)
	$(call header,Terraform fmt)
	terraform -chdir=infra fmt

infra-init: infra-fmt
	$(call need-env)
	$(call need-az)
	$(call need-terraform)
	$(call need-az-auth)
	az storage account show --name $(TFSTATE_ACCOUNT) --resource-group $(TFSTATE_RG) --output none \
	  || { echo "backend storage missing — run: gmake infra-backend-create" >&2; exit 1; }
	terraform -chdir=infra init -input=false -reconfigure \
		-backend-config="storage_account_name=$(TFSTATE_ACCOUNT)" \
		-backend-config="key=$(ENV).tfstate"

infra-validate: infra-init ## terraform validate in infra/ (ENV=dev1|prd1)
	$(call header,Terraform validate $(ENV))
	terraform -chdir=infra validate

infra-plan: infra-validate ## terraform plan in infra/ (ENV=dev1|prd1)
	$(call header,Terraform plan $(ENV))
	terraform -chdir=infra plan -input=false \
		-var-file=$(ENV).tfvars

infra-create: infra-validate ## terraform apply in infra/; write infra/outputs.json (ENV=dev1|prd1)
	$(call header,Checking az auth)
	az account show --query name -o tsv
	$(call header,Terraform apply $(ENV))
	terraform -chdir=infra apply -input=false -auto-approve \
		-var-file=$(ENV).tfvars
	terraform -chdir=infra output -json > infra/outputs.json

infra-show: ## Show workload terraform state (ENV=dev1|prd1)
	terraform -chdir=infra show -no-color -var-file=$(ENV).tfvars | bat --language Terraform

infra:
	$(error use gmake infra-create)

infra-backend:
	$(error use gmake infra-backend-create)

infra-destroy: infra-init ## terraform destroy workload stack; drop infra/outputs.json (ENV=dev1|prd1)
	$(call header,Terraform destroy $(ENV))
	terraform -chdir=infra destroy -input=false -auto-approve \
		-var-file=$(ENV).tfvars
	rm -f infra/outputs.json

# `gmake e2e FILE=<path-or-stem>` scopes to one test file; unset = live markers.
e2e_target := $(if $(FILE),$(firstword $(wildcard $(FILE) tests/$(FILE) tests/$(FILE).py)),)
ifneq ($(filter e2e,$(MAKECMDGOALS)),)
$(if $(FILE),$(if $(e2e_target),,$(error no test file matches FILE=$(FILE))))
endif

e2e: check preflight ## Live pytest vs terraform outputs (ingestion / retrieval / agent)
	$(call header,Live e2e)
	$(UV) run pytest -m "ingestion or retrieval or agent" --override-ini addopts= $(e2e_target)

clean: ## Remove caches, build artifacts, and bytecode
	$(call header,Cleaning)
	rm -rf .ruff_cache .pytest_cache dist build src/talos.egg-info *.egg-info $(call rwildcard,,__pycache__)
	rm -f .release-notes $(call rwildcard,,*.pyc) $(call rwildcard,,.DS_Store)

###############################################################################
# Release
###############################################################################

# `gmake release <part>` passes the part as an extra goal; pick it out and
# give the part words no-op recipes so make does not try to build them.
# Local recipe only: bump, tag, push, `gh release create`. CI deploy.yml
# runs on GitHub `release: published` (`uv run talos deploy --wait` + live pytest).
# Chain splits around `uv version --bump` so $(VERSION) is read after the bump.
part := $(firstword $(filter major minor patch,$(MAKECMDGOALS)))
ifneq ($(filter release,$(MAKECMDGOALS)),)
$(if $(part),,$(error usage: gmake release major|minor|patch))
endif
VERSION = $(shell $(UV) version --short)

release: check _release-gh ## Bump version, promote CHANGELOG, tag, push, gh release

_release-pre: check
	$(call need-part)
	$(call need-clean)
	$(call need-gh)
	$(call need-gh-auth)
	$(call header,Checking CHANGELOG Unreleased has shippable bullets)
	./changelog check

_release-bump: _release-pre
	$(call header,Bumping $(part) version)
	$(UV) version --bump $(part)

_release-tag: _release-bump
	$(call header,Promoting CHANGELOG Unreleased → v$(VERSION))
	./changelog promote "$(VERSION)"
	git add pyproject.toml uv.lock CHANGELOG.md
	git commit -m "chore: release v$(VERSION)"
	git tag "v$(VERSION)"

_release-gh: _release-tag
	$(call header,Pushing v$(VERSION))
	git push
	git push --tags
	$(call header,Creating GitHub release v$(VERSION))
	./changelog notes "$(VERSION)" > .release-notes
	gh release create "v$(VERSION)" \
		--title "v$(VERSION)" \
		--notes-file .release-notes \
		--verify-tag
	rm -f .release-notes
	$(info $(green)Released v$(VERSION) — CI deploy.yml runs on release published$(reset))

major minor patch: ;

###############################################################################
# Python env
###############################################################################

.venv: uv.lock
	$(UV) venv --clear
	$(UV) sync

uv.lock: pyproject.toml
	$(UV) lock --upgrade
	touch $@

###############################################################################
# Help
###############################################################################

# Target-line double-hash descriptions, read with $(file) and split with $(let).
help-src := $(file < $(firstword $(MAKEFILE_LIST)))
help-words := $(foreach w,$(subst $(space),$(s),$(help-src)),$(if $(and $(findstring $(s)##$(s),$(w)),$(filter-out \#%,$(w))),$(w)))
pad-check := check$(space)$(space)$(space)$(space)$(space)
pad-clean := clean$(space)$(space)$(space)$(space)$(space)
pad-test := test$(space)$(space)$(space)$(space)$(space)$(space)
pad-deploy := deploy$(space)$(space)$(space)$(space)
pad-generate := generate$(space)$(space)
pad-infra-fmt := infra-fmt$(space)
pad-preflight := preflight$(space)
pad-release := release$(space)$(space)$(space)
pad-e2e := e2e$(space)$(space)$(space)$(space)$(space)$(space)$(space)
pad10 = $(or $(pad-$1),$1)
show-help = $(let tgt desc,$(subst $(s)##$(s), ,$1),$(let name text,$(patsubst %:,%,$(firstword $(subst $(s),$(space),$(tgt)))) $(strip $(subst $(s),$(space),$(desc))),$(info   $(yellow)$(call pad10,$(name))$(reset) $(text))))

help:
	$(info $(blue)Usage: $(green)gmake [recipe]$(reset))
	$(info $(blue)Recipes:$(reset))
	$(foreach w,$(sort $(help-words)),$(call show-help,$(w)))
	:
