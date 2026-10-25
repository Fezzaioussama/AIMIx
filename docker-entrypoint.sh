#!/bin/sh
# The image's entrypoint: run the command (by default migrate, then serve) as the
# app user, never as root. See docs/deployment.md, "The image".
#
# Railway mounts the volume at $AIMIX_DATA_DIR owned by root, as does a new named
# Docker volume. Started as root, this hands that directory to the app user (the
# mount point, and anything an earlier run as root left in it), then drops to that
# user for good. Started as any other user (`docker run --user 10001`), it runs the
# command as it is.
set -eu

app_user=aimix

if [ "$(id -u)" -ne 0 ]; then
    exec "$@"
fi

# Directories and single-link regular files only: a symlink or a hard link left in
# the volume must not make root hand the app user a file from outside it.
find "$AIMIX_DATA_DIR" -xdev \( -type d -o -type f -links 1 \) \
    \( \! -user "$app_user" -o \! -group "$app_user" \) \
    -exec chown "$app_user:$app_user" {} +

HOME=$(getent passwd "$app_user" | cut -d: -f6)
export HOME
# No capabilities kept or regained (setuid binaries included) after the switch.
exec setpriv --reuid="$app_user" --regid="$app_user" --init-groups \
    --no-new-privs --inh-caps=-all --bounding-set=-all -- "$@"
