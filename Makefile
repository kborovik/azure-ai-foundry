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

need-azd = $(if $(dry-run),,$(if $(shell command -v azd),,$(error azd not on PATH — https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd)))
need-az = $(if $(dry-run),,$(if $(shell command -v az),,$(error az CLI required — https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)))
need-az-auth = $(if $(dry-run),,$(shell az account show >/dev/null 2>&1)$(if $(filter 0,$(.SHELLSTATUS)),,$(error az not authenticated — run: az login)))
need-azd-auth = $(if $(dry-run),,$(shell azd auth login --check-status >/dev/null 2>&1)$(if $(filter 0,$(.SHELLSTATUS)),,$(error azd not authenticated — run: azd auth login)))
need-gh = $(if $(dry-run),,$(if $(shell command -v gh),,$(error gh CLI required — https://cli.github.com/)))
need-gh-auth = $(if $(dry-run),,$(shell gh auth status >/dev/null 2>&1)$(if $(filter 0,$(.SHELLSTATUS)),,$(error gh not authenticated — run: gh auth login)))
need-clean = $(if $(dry-run),,$(if $(shell git status --porcelain),$(error working tree not clean — commit or stash first)))
need-part = $(if $(part),,$(error usage: gmake release major|minor|patch))

AZD_ENV ?= dev
AZURE_LOCATION ?= swedencentral
AZURE_SUBSCRIPTION_ID ?= f298e323-efae-4203-ba61-fc3496190479

# Recursive glob. `*` skips dot-dirs (.git, .venv).
rwildcard = $(strip \
	$(wildcard $(1)$(2)) \
	$(foreach d,$(wildcard $(1)*),$(if $(wildcard $(d)/.),$(call rwildcard,$(d)/,$(2)))))

default: help

.PHONY: help check generate deploy bicep e2e clean preflight release major minor patch
.PHONY: _release-pre _release-bump _release-tag _release-gh

###############################################################################
# Tests and local loop
###############################################################################

check: .venv ## Format check, lint, unit tests (no Azure)
	$(call header,Running unit tests)
	$(UV) run ruff format --check
	$(UV) run ruff check
	$(UV) run talos test

generate: .venv ## Render corpus locally (no Azure)
	$(call header,Generating credit policies)
	$(UV) run talos generate --local-only

deploy: .venv ## Provision Foundry IQ + agent (`talos deploy --wait`)
	$(call need-azd)
	$(call header,Deploying Foundry IQ)
	$(UV) run talos deploy --wait

preflight: .venv ## Read-only az / azd session check
	$(call need-az)
	$(call need-azd)
	$(call need-az-auth)
	$(call need-azd-auth)
	$(call header,Azure preflight)
	az account show --query name -o tsv
	azd auth login --check-status
	azd env list

bicep: ## Check az/azd auth; create env dev; azd up
	$(call need-az)
	$(call need-azd)
	$(call need-az-auth)
	$(call need-azd-auth)
	$(call header,Checking az / azd auth)
	az account show --query name -o tsv
	azd auth login --check-status
	$(call header,Creating azd env $(AZD_ENV))
	azd env select $(AZD_ENV) >/dev/null 2>&1 || azd env new $(AZD_ENV) --location $(AZURE_LOCATION) --subscription $(AZURE_SUBSCRIPTION_ID) --no-prompt
	azd env set AZURE_LOCATION $(AZURE_LOCATION)
	azd env set AZURE_SUBSCRIPTION_ID $(AZURE_SUBSCRIPTION_ID)
	$(call header,Running azd up)
	azd up --environment $(AZD_ENV) --no-prompt

# `gmake e2e FILE=<path-or-stem>` scopes to one test file; unset = live markers.
e2e_target := $(if $(FILE),$(firstword $(wildcard $(FILE) tests/$(FILE) tests/$(FILE).py)),)
ifneq ($(filter e2e,$(MAKECMDGOALS)),)
$(if $(FILE),$(if $(e2e_target),,$(error no test file matches FILE=$(FILE))))
endif

e2e: check preflight ## Live pytest vs azd env (ingestion / retrieval / agent)
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
pad-bicep := bicep$(space)$(space)$(space)$(space)$(space)
pad-check := check$(space)$(space)$(space)$(space)$(space)
pad-clean := clean$(space)$(space)$(space)$(space)$(space)
pad-deploy := deploy$(space)$(space)$(space)$(space)
pad-generate := generate$(space)$(space)
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
