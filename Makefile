# A2A-BFT -- thin wrapper around reproduce.sh
#
# Every target merely forwards to ./reproduce.sh <stage> and duplicates no logic.
# Verdict semantics, the serialization constraint, the lock file, and exit codes
# all live in reproduce.sh, so `make verify` and `./reproduce.sh verify` behave
# identically.
#
# .RECIPEPREFIX changes the recipe prefix from TAB to '>': a TAB prefix is easily
# and silently converted to spaces when files travel between editors or platforms;
# a visible character avoids that failure mode.
# Requires GNU make >= 3.82. If make is unavailable, call ./reproduce.sh directly.

.RECIPEPREFIX = >
.DEFAULT_GOAL := verify

.PHONY: help verify doctor figures datasets install all full

help:
> @./reproduce.sh help

# Default target: 10 audits + 5 negative-test groups (CPU only)
verify:
> @./reproduce.sh verify

# Run this first: report how far this machine can reproduce
doctor:
> @./reproduce.sh doctor

figures:
> @./reproduce.sh figures

datasets:
> @./reproduce.sh datasets

install:
> @./reproduce.sh install

all:
> @./reproduce.sh all

# Needs 2x80GB GPU + 78GB weights; aborts outright when prerequisites are unmet
full:
> @./reproduce.sh full
