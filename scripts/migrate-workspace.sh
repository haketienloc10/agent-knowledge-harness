#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/migrate-workspace.sh [options] <workspace-path>

Options:
  --dry-run           Show planned changes without writing files or migration state.
  --force             Replace colliding added/modified managed files when merge is unsafe.
  --verify            Run workspace-check.sh and each repo-check.sh before recording state.
  --status            Show recorded migration versions and exit.
  --to-version <n>    Apply migrations only through version <n>.
  -h, --help          Show this help.

Migration state is stored in:
  <workspace>/.qiqi/agent-knowledge-harness-migrations.tsv

Diverged modified managed files are migrated with a three-way merge using the
migration FROM_REF as base and TO_REF as the incoming template. Diverged files
removed by a migration are archived under .qiqi/migration-backups/ before removal.
USAGE
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '%s\n' "$*"
}

dry_run=0
force=0
verify=0
status_only=0
to_version=""
workspace_arg=""

while (($#)); do
  case "$1" in
    --dry-run)
      dry_run=1
      shift
      ;;
    --force)
      force=1
      shift
      ;;
    --verify)
      verify=1
      shift
      ;;
    --status)
      status_only=1
      shift
      ;;
    --to-version)
      (($# >= 2)) || fail '--to-version requires a value'
      to_version="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      (($# <= 1)) || fail 'too many positional arguments'
      if (($# == 1)); then
        workspace_arg="$1"
        shift
      fi
      ;;
    -*)
      fail "unknown option: $1"
      ;;
    *)
      [[ -z "$workspace_arg" ]] || fail 'only one workspace path is allowed'
      workspace_arg="$1"
      shift
      ;;
  esac
done

[[ -n "$workspace_arg" ]] || { usage >&2; exit 2; }
[[ -z "$to_version" || "$to_version" =~ ^[0-9]+$ ]] || fail '--to-version must be a non-negative integer'
((dry_run && verify)) && fail '--verify cannot be combined with --dry-run'

for command in git yq cmp mktemp cp; do
  command -v "$command" >/dev/null 2>&1 || fail "missing required command: $command"
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
harness_root="$(git -C "$script_dir/.." rev-parse --show-toplevel 2>/dev/null)" || \
  fail 'script must run from a Git checkout of agent-knowledge-harness'
[[ -d "$harness_root/workspace-template" && -d "$harness_root/repo-template" ]] || \
  fail "invalid harness checkout: $harness_root"

migrations_dir="$harness_root/migrations"
[[ -d "$migrations_dir" ]] || fail "missing migrations directory: $migrations_dir"

workspace_root="$(cd "$workspace_arg" 2>/dev/null && pwd -P)" || \
  fail "workspace path does not exist: $workspace_arg"
[[ -f "$workspace_root/repos.yaml" ]] || fail "workspace is missing repos.yaml: $workspace_root"

if ! yq --version 2>&1 | grep -Eq 'version v?4\.'; then
  fail 'yq v4 is required'
fi

mapfile -t migration_files < <(find "$migrations_dir" -maxdepth 1 -type f -name '[0-9][0-9][0-9][0-9]-*.env' -print | sort)
((${#migration_files[@]} > 0)) || fail 'no migration definitions found'

migration_version() {
  local file="$1" base
  base="$(basename "$file")"
  printf '%d\n' "$((10#${base%%-*}))"
}

latest_version=0
expected_version=1
for migration_file in "${migration_files[@]}"; do
  version="$(migration_version "$migration_file")"
  ((version == expected_version)) || \
    fail "migration sequence gap: expected $(printf '%04d' "$expected_version"), found $(printf '%04d' "$version")"
  latest_version="$version"
  expected_version=$((expected_version + 1))
done

if [[ -z "$to_version" ]]; then
  target_version="$latest_version"
else
  target_version="$to_version"
  ((target_version <= latest_version)) || \
    fail "requested version $target_version exceeds latest migration $latest_version"
fi

state_file="$workspace_root/.qiqi/agent-knowledge-harness-migrations.tsv"
declare -A state=()
if [[ -f "$state_file" ]]; then
  while IFS=$'\t' read -r key value extra; do
    [[ -n "$key" ]] || continue
    [[ -z "${extra:-}" ]] || fail "invalid migration state row for $key"
    [[ "$value" =~ ^[0-9]+$ ]] || fail "invalid migration version for $key: $value"
    state["$key"]="$value"
  done < "$state_file"
fi

mapfile -t repo_paths < <(yq -r '.repositories[].path' "$workspace_root/repos.yaml")
((${#repo_paths[@]} > 0)) || fail 'repos.yaml must contain at least one repository'

declare -A seen_repo_paths=()
declare -a repo_roots=()
for repo_rel in "${repo_paths[@]}"; do
  [[ -n "$repo_rel" && "$repo_rel" != "null" ]] || fail 'repos.yaml contains an empty repository path'
  [[ "$repo_rel" != /* ]] || fail "repository path must be relative: $repo_rel"
  IFS='/' read -r -a parts <<< "$repo_rel"
  for part in "${parts[@]}"; do
    [[ "$part" != '..' ]] || fail "repository path must not contain '..': $repo_rel"
  done
  [[ -z "${seen_repo_paths[$repo_rel]:-}" ]] || fail "duplicate repository path: $repo_rel"
  seen_repo_paths["$repo_rel"]=1

  repo_root="$(cd "$workspace_root/$repo_rel" 2>/dev/null && pwd -P)" || \
    fail "repository path does not exist: $repo_rel"
  git_root="$(git -C "$repo_root" rev-parse --show-toplevel 2>/dev/null)" || \
    fail "repository path is not a Git repository: $repo_rel"
  git_root="$(cd "$git_root" && pwd -P)"
  [[ "$git_root" == "$repo_root" ]] || fail "repository path is not the exact Git root: $repo_rel"
  repo_roots+=("$repo_root")
done

get_state_version() {
  local key="$1"
  printf '%s\n' "${state[$key]:-0}"
}

if ((status_only)); then
  printf 'Harness migrations: latest=%d target=%d\n' "$latest_version" "$target_version"
  printf 'workspace\t%s\n' "$(get_state_version workspace)"
  for repo_rel in "${repo_paths[@]}"; do
    printf 'repo:%s\t%s\n' "$repo_rel" "$(get_state_version "repo:$repo_rel")"
  done
  exit 0
fi

ref_exists() {
  git -C "$harness_root" cat-file -e "$1^{commit}" 2>/dev/null
}

ref_file_exists() {
  local ref="$1" path="$2"
  git -C "$harness_root" cat-file -e "$ref:$path" 2>/dev/null
}

ref_mode() {
  local ref="$1" path="$2"
  git -C "$harness_root" ls-tree "$ref" -- "$path" | awk 'NR == 1 {print $1}'
}

mode_is_supported() {
  [[ "$1" == '100644' || "$1" == '100755' ]]
}

validate_ref_file_mode() {
  local ref="$1" source_path="$2" mode
  mode="$(ref_mode "$ref" "$source_path")"
  mode_is_supported "$mode" || fail "unsupported Git mode $mode for $source_path at $ref"
}

target_matches_ref() {
  local target="$1" ref="$2" source_path="$3" mode tmp expected_exec actual_exec
  ref_file_exists "$ref" "$source_path" || return 1
  [[ -f "$target" && ! -L "$target" ]] || return 1
  mode="$(ref_mode "$ref" "$source_path")"
  mode_is_supported "$mode" || return 1
  tmp="$(mktemp)"
  git -C "$harness_root" show "$ref:$source_path" > "$tmp"
  if ! cmp -s "$target" "$tmp"; then
    rm -f "$tmp"
    return 1
  fi
  rm -f "$tmp"
  expected_exec=0
  actual_exec=0
  [[ "$mode" == '100755' ]] && expected_exec=1
  [[ -x "$target" ]] && actual_exec=1
  ((expected_exec == actual_exec))
}

render_three_way_merge() {
  local from_ref="$1" to_ref="$2" source_path="$3" target="$4" output="$5"
  local base incoming current rc
  [[ -f "$target" && ! -L "$target" ]] || return 2
  ref_file_exists "$from_ref" "$source_path" || return 2
  ref_file_exists "$to_ref" "$source_path" || return 2

  base="$(mktemp)"
  incoming="$(mktemp)"
  current="$(mktemp)"
  git -C "$harness_root" show "$from_ref:$source_path" > "$base"
  git -C "$harness_root" show "$to_ref:$source_path" > "$incoming"
  cp -p "$target" "$current"

  set +e
  git merge-file -p \
    -L "workspace:${source_path}" \
    -L "template-base:${source_path}" \
    -L "template-target:${source_path}" \
    "$current" "$base" "$incoming" > "$output"
  rc=$?
  set -e
  rm -f "$base" "$incoming" "$current"
  return "$rc"
}

three_way_merge_is_clean() {
  local from_ref="$1" to_ref="$2" source_path="$3" target="$4" merged rc
  merged="$(mktemp)"
  set +e
  render_three_way_merge "$from_ref" "$to_ref" "$source_path" "$target" "$merged"
  rc=$?
  set -e
  rm -f "$merged"
  return "$rc"
}

backup_root_for() {
  local key="$1" version="$2"
  if [[ "$key" == 'workspace' ]]; then
    printf '%s/.qiqi/migration-backups/v%04d/workspace\n' "$workspace_root" "$version"
  else
    printf '%s/.qiqi/migration-backups/v%04d/repos/%s\n' \
      "$workspace_root" "$version" "${key#repo:}"
  fi
}

preflight_backup_target() {
  local target="$1" backup="$2"
  if [[ ! -e "$backup" && ! -L "$backup" ]]; then
    return 0
  fi
  if [[ -f "$backup" && ! -L "$backup" ]] && cmp -s "$target" "$backup"; then
    return 0
  fi
  printf 'CONFLICT: %s\n' "$backup" >&2
  printf '  migration backup path already exists with different content/type.\n' >&2
  return 1
}

backup_diverged_deletion() {
  local target="$1" backup="$2"
  [[ -f "$target" && ! -L "$target" ]] || fail "cannot safely archive non-regular managed path: $target"
  mkdir -p "$(dirname "$backup")"
  if [[ -e "$backup" || -L "$backup" ]]; then
    [[ -f "$backup" && ! -L "$backup" ]] || fail "migration backup path is not a regular file: $backup"
    cmp -s "$target" "$backup" || fail "migration backup already exists with different content: $backup"
    return 0
  fi
  cp -p "$target" "$backup"
}

preflight_change() {
  local status="$1" from_ref="$2" to_ref="$3" source_path="$4" target="$5"
  local rc
  case "$status" in
    A)
      validate_ref_file_mode "$to_ref" "$source_path"
      if [[ ! -e "$target" && ! -L "$target" ]] || target_matches_ref "$target" "$to_ref" "$source_path"; then
        return 0
      fi
      ;;
    M)
      validate_ref_file_mode "$to_ref" "$source_path"
      if [[ ! -e "$target" && ! -L "$target" ]] || \
         target_matches_ref "$target" "$to_ref" "$source_path" || \
         target_matches_ref "$target" "$from_ref" "$source_path"; then
        return 0
      fi
      if [[ -f "$target" && ! -L "$target" ]]; then
        set +e
        three_way_merge_is_clean "$from_ref" "$to_ref" "$source_path" "$target"
        rc=$?
        set -e
        if ((rc == 0)); then
          return 0
        fi
        if ((rc == 1)); then
          printf 'CONFLICT: %s\n' "$target" >&2
          printf '  local edits overlap template changes; automatic three-way merge has conflicts.\n' >&2
          printf '  merge it manually or rerun with --force to replace it with the target template.\n' >&2
          return 1
        fi
      fi
      ;;
    D)
      if [[ ! -e "$target" && ! -L "$target" ]] || target_matches_ref "$target" "$from_ref" "$source_path"; then
        return 0
      fi
      if [[ -f "$target" && ! -L "$target" ]]; then
        return 0
      fi
      ;;
    *)
      fail "unsupported migration status '$status' for $source_path"
      ;;
  esac

  if ((force)); then
    printf 'FORCE conflict: %s\n' "$target" >&2
    return 0
  fi
  printf 'CONFLICT: %s\n' "$target" >&2
  printf '  managed path cannot be migrated safely with its current type/content.\n' >&2
  printf '  merge it manually or rerun with --force to replace it.\n' >&2
  return 1
}

apply_copy() {
  local to_ref="$1" source_path="$2" target="$3" mode tmp
  mode="$(ref_mode "$to_ref" "$source_path")"
  validate_ref_file_mode "$to_ref" "$source_path"
  mkdir -p "$(dirname "$target")"
  tmp="$(mktemp "$(dirname "$target")/.migrate.XXXXXX")"
  git -C "$harness_root" show "$to_ref:$source_path" > "$tmp"
  if [[ "$mode" == '100755' ]]; then
    chmod 755 "$tmp"
  else
    chmod 644 "$tmp"
  fi
  mv -f "$tmp" "$target"
}

apply_three_way_merge() {
  local from_ref="$1" to_ref="$2" source_path="$3" target="$4" mode tmp rc
  mode="$(ref_mode "$to_ref" "$source_path")"
  validate_ref_file_mode "$to_ref" "$source_path"
  tmp="$(mktemp "$(dirname "$target")/.migrate.XXXXXX")"
  set +e
  render_three_way_merge "$from_ref" "$to_ref" "$source_path" "$target" "$tmp"
  rc=$?
  set -e
  if ((rc == 0)); then
    if [[ "$mode" == '100755' ]]; then
      chmod 755 "$tmp"
    else
      chmod 644 "$tmp"
    fi
    mv -f "$tmp" "$target"
    return 0
  fi
  rm -f "$tmp"
  return "$rc"
}

prune_empty_parents() {
  local dir="$1" stop="$2"
  while [[ "$dir" != "$stop" && "$dir" == "$stop"/* ]]; do
    rmdir "$dir" 2>/dev/null || break
    dir="$(dirname "$dir")"
  done
}

process_file_set() {
  local phase="$1" key="$2" version="$3" from_ref="$4" to_ref="$5" prefix="$6" target_root="$7"
  shift 7
  local -a source_paths=("$@")
  local source_path line status changed_path relative target failures=0 backup_root backup rc
  backup_root="$(backup_root_for "$key" "$version")"

  for source_path in "${source_paths[@]}"; do
    [[ "$source_path" == "$prefix/"* ]] || fail "migration path outside $prefix: $source_path"
    line="$(git -C "$harness_root" diff --no-renames --name-status "$from_ref" "$to_ref" -- "$source_path")"
    [[ -n "$line" ]] || fail "migration manifest lists unchanged path: $source_path"
    [[ "$line" != *$'\n'* ]] || fail "migration path produced multiple diff rows: $source_path"
    status="${line%%$'\t'*}"
    changed_path="${line#*$'\t'}"
    [[ "$changed_path" == "$source_path" ]] || fail "unexpected diff path for $source_path: $changed_path"

    relative="${source_path#"$prefix/"}"
    target="$target_root/$relative"

    if [[ "$phase" == 'preflight' ]]; then
      if ! preflight_change "$status" "$from_ref" "$to_ref" "$source_path" "$target"; then
        failures=$((failures + 1))
      elif [[ "$status" == 'D' && -f "$target" && ! -L "$target" ]] && \
           ! target_matches_ref "$target" "$from_ref" "$source_path"; then
        backup="$backup_root/$relative"
        if ! preflight_backup_target "$target" "$backup"; then
          failures=$((failures + 1))
        fi
      fi
      continue
    fi

    case "$status" in
      A)
        if target_matches_ref "$target" "$to_ref" "$source_path"; then
          log "  = $relative"
        elif ((dry_run)); then
          if [[ -e "$target" || -L "$target" ]]; then
            log "  + $relative (force replace)"
          else
            log "  + $relative"
          fi
        else
          apply_copy "$to_ref" "$source_path" "$target"
          log "  + $relative"
        fi
        ;;
      M)
        if target_matches_ref "$target" "$to_ref" "$source_path"; then
          log "  = $relative"
        elif [[ ! -e "$target" && ! -L "$target" ]] || target_matches_ref "$target" "$from_ref" "$source_path"; then
          if ((dry_run)); then
            log "  + $relative"
          else
            apply_copy "$to_ref" "$source_path" "$target"
            log "  + $relative"
          fi
        elif ((force)); then
          if ((dry_run)); then
            log "  + $relative (force replace)"
          else
            apply_copy "$to_ref" "$source_path" "$target"
            log "  + $relative (force replace)"
          fi
        else
          if ((dry_run)); then
            log "  ~ $relative (clean 3-way merge)"
          else
            set +e
            apply_three_way_merge "$from_ref" "$to_ref" "$source_path" "$target"
            rc=$?
            set -e
            if ((rc == 0)); then
              log "  ~ $relative (3-way merged)"
            else
              fail "three-way merge became unsafe after preflight for $target (exit $rc)"
            fi
          fi
        fi
        ;;
      D)
        if [[ ! -e "$target" && ! -L "$target" ]]; then
          log "  = $relative (already absent)"
        elif target_matches_ref "$target" "$from_ref" "$source_path"; then
          if ((dry_run)); then
            log "  - $relative"
          else
            rm -f "$target"
            prune_empty_parents "$(dirname "$target")" "$target_root"
            log "  - $relative"
          fi
        elif [[ -f "$target" && ! -L "$target" ]]; then
          backup="$backup_root/$relative"
          if ((dry_run)); then
            log "  - $relative (archive customized file -> ${backup#"$workspace_root/"})"
          else
            backup_diverged_deletion "$target" "$backup"
            rm -f "$target"
            prune_empty_parents "$(dirname "$target")" "$target_root"
            log "  - $relative (archived -> ${backup#"$workspace_root/"})"
          fi
        elif ((force)); then
          if ((dry_run)); then
            log "  - $relative (force remove non-regular path)"
          else
            rm -rf -- "$target"
            prune_empty_parents "$(dirname "$target")" "$target_root"
            log "  - $relative (force removed)"
          fi
        else
          fail "non-regular deleted managed path became unsafe after preflight: $target"
        fi
        ;;
      *)
        fail "unsupported migration status '$status' for $source_path"
        ;;
    esac
  done

  ((failures == 0))
}

load_migration() {
  local migration_file="$1" expected="$2"
  unset VERSION FROM_REF TO_REF DESCRIPTION WORKSPACE_FILES REPO_FILES WORKSPACE_MANUAL_REVIEW REPO_MANUAL_REVIEW
  # shellcheck disable=SC1090
  source "$migration_file"
  [[ "${VERSION:-}" =~ ^[0-9]+$ ]] || fail "invalid VERSION in $migration_file"
  ((VERSION == expected)) || fail "VERSION mismatch in $migration_file: expected $expected, got $VERSION"
  [[ -n "${FROM_REF:-}" && -n "${TO_REF:-}" ]] || fail "missing FROM_REF/TO_REF in $migration_file"
  declare -p WORKSPACE_FILES >/dev/null 2>&1 || fail "missing WORKSPACE_FILES array in $migration_file"
  declare -p REPO_FILES >/dev/null 2>&1 || fail "missing REPO_FILES array in $migration_file"
  ref_exists "$FROM_REF" || fail "migration $VERSION base commit is unavailable: $FROM_REF"
  ref_exists "$TO_REF" || fail "migration $VERSION target commit is unavailable: $TO_REF"
}

run_target_migrations() {
  local phase="$1" key="$2" prefix="$3" target_root="$4" current next migration_file
  local -a files=() manual_review=()
  current="$(get_state_version "$key")"
  ((current <= target_version)) || fail "$key is recorded at future version $current (target $target_version)"

  if ((current == target_version)); then
    [[ "$phase" == 'apply' ]] && log "$key: already at version $current"
    return 0
  fi

  for migration_file in "${migration_files[@]}"; do
    next="$(migration_version "$migration_file")"
    ((next > current && next <= target_version)) || continue
    load_migration "$migration_file" "$next"

    manual_review=()
    if [[ "$prefix" == 'workspace-template' ]]; then
      files=("${WORKSPACE_FILES[@]}")
      if declare -p WORKSPACE_MANUAL_REVIEW >/dev/null 2>&1; then
        manual_review=("${WORKSPACE_MANUAL_REVIEW[@]}")
      fi
    else
      files=("${REPO_FILES[@]}")
      if declare -p REPO_MANUAL_REVIEW >/dev/null 2>&1; then
        manual_review=("${REPO_MANUAL_REVIEW[@]}")
      fi
    fi

    if [[ "$phase" == 'preflight' ]]; then
      log "$key: preflight migration $VERSION ${DESCRIPTION:+- $DESCRIPTION}"
      process_file_set preflight "$key" "$VERSION" "$FROM_REF" "$TO_REF" "$prefix" "$target_root" "${files[@]}" || return 1
    else
      if ((dry_run)); then
        log "$key: dry-run migration $VERSION"
      else
        log "$key: apply migration $VERSION"
      fi
      process_file_set apply "$key" "$VERSION" "$FROM_REF" "$TO_REF" "$prefix" "$target_root" "${files[@]}"

      if ((${#manual_review[@]} > 0)); then
        log "$key: manual review (not overwritten automatically):"
        for source_path in "${manual_review[@]}"; do
          log "  ! ${source_path#"$prefix/"}"
        done
      fi

      state["$key"]="$VERSION"
    fi
    current="$VERSION"
  done
}

write_state() {
  local temp key
  mkdir -p "$(dirname "$state_file")"
  temp="$(mktemp "$(dirname "$state_file")/.migrations.XXXXXX")"
  {
    printf 'workspace\t%s\n' "${state[workspace]:-0}"
    for repo_rel in "${repo_paths[@]}"; do
      key="repo:$repo_rel"
      printf '%s\t%s\n' "$key" "${state[$key]:-0}"
    done
  } > "$temp"
  mv -f "$temp" "$state_file"
}

preflight_failed=0
if ! run_target_migrations preflight workspace workspace-template "$workspace_root"; then
  preflight_failed=1
fi
for index in "${!repo_paths[@]}"; do
  repo_rel="${repo_paths[$index]}"
  if ! run_target_migrations preflight "repo:$repo_rel" repo-template "${repo_roots[$index]}"; then
    preflight_failed=1
  fi
done
((preflight_failed == 0)) || fail 'migration preflight has conflicts; no managed files were changed'

run_target_migrations apply workspace workspace-template "$workspace_root"
for index in "${!repo_paths[@]}"; do
  repo_rel="${repo_paths[$index]}"
  run_target_migrations apply "repo:$repo_rel" repo-template "${repo_roots[$index]}"
done

if ((verify)); then
  log 'verification: workspace'
  [[ -x "$workspace_root/scripts/workspace-check.sh" || -f "$workspace_root/scripts/workspace-check.sh" ]] || \
    fail 'workspace checker is missing after migration'
  bash "$workspace_root/scripts/workspace-check.sh"

  for repo_root in "${repo_roots[@]}"; do
    log "verification: $repo_root"
    [[ -x "$repo_root/scripts/repo-check.sh" || -f "$repo_root/scripts/repo-check.sh" ]] || \
      fail "repo checker is missing after migration: $repo_root"
    bash "$repo_root/scripts/repo-check.sh"
  done
fi

if ((dry_run)); then
  log "dry-run complete; migration state remains unchanged at $state_file"
else
  write_state
  log "migration complete; state recorded at $state_file"
fi
