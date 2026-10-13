# The standard Makefile.
#
# Copy this into a project, fill in the identity header, then replace each verb
# below with that stack's real command. Every repo answers the same eleven
# verbs, so `make` in any of them lists the same vocabulary.
#
#   help  setup  dev  build  run  test  check  verify  fmt  clean  distclean
#
# Rules that keep the set uniform:
#
#   * `make` on its own always prints the help. It never builds, installs or
#     starts anything.
#   * A verb that does not apply still EXISTS and explains why, via $(call NA,
#     '...'). A missing target gives make's "No rule to make target", which
#     reads like a broken Makefile rather than an answer.
#   * `check` is the fast gate and `verify` is `check` plus a build.
#   * `clean` is always safe to run. Anything that costs a reinstall — node_
#     modules, .venv, target/, docker volumes — belongs to `distclean`.
#   * A project's own targets keep their own `##@ Section`. Renaming one breaks
#     the docs, so the old name stays as an alias with no `##` comment, which
#     keeps it out of the help.
#
# The block between the two sentinels is byte-identical in every repo, so
# checking for drift is a diff and needs no parser.

# ─── Identity (the only part that differs between repos) ─────────────────────
# No apostrophes in any of these four: they are interpolated into a
# single-quoted shell string in the help recipe.
PROJECT       := re4mepc
TAGLINE       := Resident Evil 4 Mobile Linux PC host
# `=` and not `:=`: with `:=` these expand before the variables they cite are
# defined further down, and the help footer prints empty values with no error.
HELP_VARS      = PYTHON=$(PYTHON) ARGS=$(ARGS) TEST_ARGS=$(TEST_ARGS) DESKTOP_ARGS=$(DESKTOP_ARGS) APK=/path/to/game.apk
HELP_EXAMPLE   = make import APK="/path/to/Resident Evil 4.apk"

# ─── Preamble ────────────────────────────────────────────────────────────────
# -e stops a recipe at the first failing command; -o pipefail stops a gate that
# pipes through a filter from reporting the filter's exit code instead of the
# command's — without it, a suite that fails into `tail` "passes".
SHELL         := /usr/bin/env bash
.SHELLFLAGS   := -eo pipefail -c
.DEFAULT_GOAL := help
MAKEFLAGS     += --no-print-directory

# ─── Colour ──────────────────────────────────────────────────────────────────
# MAKE_TERMOUT (GNU Make >= 4.1) is set only when stdout is a terminal, and is
# the only reliable test available here: `test -t 1` inside $(shell ...) always
# reports false, because make captures that command's stdout through a pipe.
# So `make help | less` and CI logs stay clean. NO_COLOR disables, FORCE_COLOR
# overrides both.
COLOR ?= $(if $(MAKE_TERMOUT),1,0)
ifdef NO_COLOR
  COLOR := 0
endif
ifdef FORCE_COLOR
  COLOR := 1
endif
ifeq ($(COLOR),1)
  # Real ESC bytes, so a plain `echo` renders them without needing -e.
  C_HEAD := $(shell printf '\033[1m')
  C_CMD  := $(shell printf '\033[36m')
  C_OK   := $(shell printf '\033[32m')
  C_WARN := $(shell printf '\033[33m')
  C_ERR  := $(shell printf '\033[31m')
  C_DIM  := $(shell printf '\033[2m')
  C_OFF  := $(shell printf '\033[0m')
endif

# Explains why a core verb does not apply here, then fails.
NA = @printf '  $(C_ERR)make $@$(C_OFF) does not apply to $(PROJECT).\n  $(C_DIM)%s$(C_OFF)\n\n' $(1) >&2; exit 2

# Width of the target-name column in help; widen it where names are long.
HELP_PAD ?= 18

# PROJECT, TAGLINE, HELP_VARS and HELP_EXAMPLE are interpolated into a
# single-quoted shell string below, so none of them may contain an apostrophe.
##@ General
.PHONY: help
help: ## List the available targets
	@printf '\n  $(C_HEAD)$(PROJECT)$(C_OFF) — $(TAGLINE)\n'
	@printf '  $(C_DIM)usage: make <target>$(C_OFF)\n'
	@awk 'BEGIN { FS = ":.*?## " } \
	  /^##@ / { printf "\n  $(C_HEAD)%s$(C_OFF)\n", substr($$0, 5); next } \
	  /^[a-zA-Z0-9_.-]+:.*?## / { printf "    $(C_CMD)%-$(HELP_PAD)s$(C_OFF) %s\n", $$1, $$2 }' \
	  $(MAKEFILE_LIST)
	@printf '\n  $(C_DIM)Variables:$(C_OFF) $(HELP_VARS)\n'
	@printf '  $(C_DIM)Example:$(C_OFF)   $(HELP_EXAMPLE)\n\n'

# ─── End of the shared block ─────────────────────────────────────────────────

PYTHON ?= .venv/bin/python
ARGS ?=
TEST_ARGS ?=
DESKTOP_ARGS ?=
APK ?=
# Pass APK paths through the environment so spaces and shell characters stay literal.
override APK := $(value APK)
export APK

##@ Setup
.PHONY: setup
setup: ## Prepare the Python environment and compile native helpers
	./setup.sh

##@ Desktop app
.PHONY: install uninstall desktop uninstall-desktop
install: setup ## Set up the app and install the re4mepc CLI and app-menu entry
	$(PYTHON) tools/install_desktop.py $(DESKTOP_ARGS)
uninstall: uninstall-desktop ## Remove the installed CLI and shortcuts; preserve game and saves
desktop: build ## Install a Linux executable and app-menu shortcut (DESKTOP_ARGS selects icon)
	$(PYTHON) tools/install_desktop.py $(DESKTOP_ARGS)
uninstall-desktop: ## Remove the per-user launcher and icon; preserve game and saves
	$(PYTHON) tools/install_desktop.py --uninstall $(DESKTOP_ARGS)

##@ Development
.PHONY: dev build run
dev: run ## Launch the game for local development
build: ## Compile native audio and memory helpers
	$(PYTHON) -u tools/build_native.py
run: ## Launch the game with live terminal logs (ARGS adds options)
	./re4pc.sh run $(ARGS)

##@ Game and CLI
.PHONY: play launcher import cli settings backup backups
play: launcher ## Open the launcher to import an APK or play
launcher: ## Open the native graphical launcher (ARGS adds options)
	./re4pc.sh launcher $(ARGS)
import: ## Import your APK: make import APK="/path/to/game.apk" (ARGS adds options)
	@test -n "$$APK" || { printf 'Usage: make import APK="/path/to/game.apk"\n' >&2; exit 2; }
	./re4pc.sh import "$$APK" $(ARGS)
cli: ## Run any CLI command: make cli ARGS="--help" (no ARGS opens launcher)
	./re4pc.sh $(ARGS)
settings: ## Show settings or change a value with ARGS
backup: ## Create a save backup (ARGS adds options)
backups: ## List save backups (ARGS adds options)
settings backup backups:
	./re4pc.sh $@ $(ARGS)

##@ Gates
.PHONY: test check verify fmt check-game audit-source
test: build ## Run component regression tests with synthetic data
	$(PYTHON) -u tools/test_components.py
check: test ## Run game-free component tests
	@printf 'CHECK_PASS\n'
check-game: ## Validate the user-supplied imported game
	./re4pc.sh check $(ARGS)
audit-source: ## Audit staged files and every Git blob, including history
	$(PYTHON) tools/audit_source.py --worktree
verify: check audit-source ## Compile helpers, test synthetic data and audit sources
	@printf 'VERIFY_PASS\n'
fmt: ## Explain formatter availability
	$(call NA,'No automatic formatter is configured for this project.')

##@ Visible game checks
.PHONY: visible-test controls-test
visible-test: ## Open the game and verify startup, rendering and audio
	$(PYTHON) -u tools/test_visible.py $(TEST_ARGS)
controls-test: ## Open the game and exercise PC gameplay controls
	$(PYTHON) -u tools/test_pc_controls.py $(TEST_ARGS)

##@ Cleaning
.PHONY: clean distclean
clean: ## Remove compiled helpers and Python caches; preserve game and saves
	rm -f build/libre4audio.so build/libre4fast.so build/libunicorn.so.2
	find re4pc tests tools -type d -name __pycache__ -prune -exec rm -rf {} +
distclean: clean ## Also remove the local Python environment
	rm -rf .venv

##@ Distribution
.PHONY: package
package: ## Build audited Linux x86_64 AppImage and portable archive using Ubuntu 22.04 Docker
	$(PYTHON) tools/package.py $(PACKAGE_ARGS)
