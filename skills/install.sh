#!/bin/sh
# Install the wicked-e2e skills (skills/wicked-e2e*) into an agent CLI's skills directory.
#
#   skills/install.sh [--copy] [--force] [--dry-run] DEST_SKILLS_DIR
#   skills/install.sh [--copy] [--force] [--dry-run] --codex          # into $CODEX_HOME/skills
#
# DEST_SKILLS_DIR is required (for Claude Code: a workspace's .claude/skills directory). Nothing is
# written anywhere else. --codex uses $CODEX_HOME/skills and refuses when CODEX_HOME is unset.
#
# Default: each skill is a symlink to this checkout, so a `git pull` updates it and the skill finds
# the e2e CLI two directories above its real path. --copy copies the files instead (use it on
# Windows, or where symlinks are not followed) and writes a `wicked-ci-root` file into each copied
# skill naming this checkout. An existing skill of the same name is replaced only with --force,
# except a symlink into this checkout, which is refreshed.
set -eu

copy=0; force=0; dry=0; dest=""
while [ $# -gt 0 ]; do
  case "$1" in
    --copy) copy=1 ;;
    --force) force=1 ;;
    --dry-run) dry=1 ;;
    --codex)
      if [ -z "${CODEX_HOME:-}" ]; then echo "install.sh: --codex needs CODEX_HOME set (the Codex home whose skills/ to use)" >&2; exit 2; fi
      if [ -n "$dest" ]; then echo "install.sh: one destination only" >&2; exit 2; fi
      dest="$CODEX_HOME/skills" ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    -*) echo "install.sh: unknown option $1" >&2; exit 2 ;;
    *) if [ -n "$dest" ]; then echo "install.sh: one destination only" >&2; exit 2; fi; dest="$1" ;;
  esac
  shift
done
if [ -z "$dest" ]; then
  echo "install.sh: name the skills directory to install into (or --codex); see --help" >&2
  exit 2
fi

here=$(cd "$(dirname "$0")" && pwd -P)
root=$(cd "$here/.." && pwd -P)
if [ ! -f "$root/e2e/bin/e2e" ]; then echo "install.sh: $root has no e2e/bin/e2e" >&2; exit 1; fi

run() { if [ "$dry" = 1 ]; then echo "would: $*"; else "$@"; fi; }

# Never install into the sources themselves (or below them): replacing a skill there deletes it. The
# destination is resolved before anything is created: no `..` component, and the nearest existing
# ancestor canonicalised with the not-yet-created rest appended.
case "/$dest/" in
  */../*) echo "install.sh: give the destination without a .. component" >&2; exit 2 ;;
esac
p="$dest"; rest=""
while [ ! -d "$p" ]; do
  rest="/$(basename "$p")$rest"
  p=$(dirname "$p")
done
cdest="$(cd "$p" && pwd -P)$rest"
case "$cdest/" in
  "$here"/*) echo "install.sh: $dest is inside this checkout's skills/ ($here); choose another directory" >&2; exit 2 ;;
esac

run mkdir -p "$dest"
# Preflight every target before changing anything: none may be, or contain, this checkout.
for src in "$here"/wicked-e2e*; do
  [ -f "$src/SKILL.md" ] || continue
  t="$dest/$(basename "$src")"
  if [ -d "$t" ] && [ ! -L "$t" ]; then
    ct=$(cd "$t" && pwd -P)
    case "$root/" in
      "$ct"/*) echo "install.sh: $t contains this checkout ($root); refusing to replace it" >&2; exit 2 ;;
    esac
  fi
done
n=0
for src in "$here"/wicked-e2e*; do
  [ -f "$src/SKILL.md" ] || continue
  name=$(basename "$src")
  target="$dest/$name"
  if [ -L "$target" ]; then
    link=$(readlink "$target" || true)
    if [ "$link" != "$src" ] && [ "$force" != 1 ]; then
      echo "install.sh: $target is a symlink to $link, not this checkout; use --force to replace it" >&2; exit 1
    fi
    run rm "$target"
  elif [ -e "$target" ]; then
    if [ "$force" != 1 ]; then echo "install.sh: $target exists; use --force to replace it" >&2; exit 1; fi
    run rm -rf "$target"
  fi
  if [ "$copy" = 1 ]; then
    run cp -R "$src" "$target"
    # A native path on Windows (Git Bash's `pwd -W`), so a Windows Python can open it.
    native=$( (cd "$root" && pwd -W) 2>/dev/null || printf '%s' "$root")
    if [ "$dry" = 1 ]; then echo "would: write $target/wicked-ci-root"; else printf '%s\n' "$native" > "$target/wicked-ci-root"; fi
  else
    run ln -s "$src" "$target"
  fi
  n=$((n + 1))
done
echo "install.sh: $n skills -> $dest ($( [ "$copy" = 1 ] && echo copied || echo symlinked ); the e2e CLI is $root/e2e/bin/e2e)"
