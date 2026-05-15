#!/usr/bin/env bash
set -euo pipefail

SRCDIR="$(cd "$(dirname "$0")" && pwd)"
BUILDDIR="$SRCDIR/_build"
PREFIX="$SRCDIR/_install"

# Setup build directory with prefix pointing to local install
if [ ! -d "$BUILDDIR" ]; then
    meson setup "$BUILDDIR" "$SRCDIR" --prefix="$PREFIX"
fi

# Build
meson compile -C "$BUILDDIR"

# Install
meson install -C "$BUILDDIR"

# Run
export GSETTINGS_SCHEMA_DIR="$PREFIX/share/glib-2.0/schemas"

"$PREFIX/bin/fedora-updater" "$@"
