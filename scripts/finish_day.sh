#!/usr/bin/env bash
# finish_day — закоммитить и запушить задание дня в master (без PR).
# День определяется по изменённым файлам в weeks/ и journal/.
# Прочие изменения — отдельным коммитом до коммита задания.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: finish_day [-m "commit message"] [-n]

  -m  Сообщение коммита задания (иначе — из README дня).
  -n  Dry-run: только показать план, без commit/push.

День определяется автоматически по git status (weeks/week-NN/day-DD/, journal/).
EOF
  exit "${1:-0}"
}

MSG=""
DRY_RUN=0

while getopts "m:nh" opt; do
  case "$opt" in
    m) MSG="$OPTARG" ;;
    n) DRY_RUN=1 ;;
    h) usage 0 ;;
    *) usage 1 ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

branch="$(git branch --show-current)"
if [[ "$branch" != "master" ]]; then
  echo "finish_day: нужна ветка master (сейчас: $branch)" >&2
  exit 1
fi

get_changed_files() {
  {
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
  } | sort -u | grep -v '^$' || true
}

day_key_from_path() {
  local path="$1"
  if [[ "$path" =~ ^weeks/week-([0-9]+)/day-([0-9]+)/ ]]; then
    printf '%s-%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
  elif [[ "$path" =~ ^journal/week-([0-9]+)/day-([0-9]+)\.md$ ]]; then
    printf '%s-%s\n' "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
  fi
}

is_day_file() {
  local path="$1" week day
  [[ "$path" =~ ^weeks/week-[0-9]+/day-[0-9]+/ ]] || [[ "$path" =~ ^journal/week-[0-9]+/day-[0-9]+\.md$ ]]
}

belongs_to_day() {
  local path="$1" week="$2" day="$3"
  [[ "$path" == "weeks/week-${week}/day-${day}/"* ]] || [[ "$path" == "journal/week-${week}/day-${day}.md" ]]
}

commit_url() {
  local sha="$1"
  local remote url
  remote="$(git remote get-url origin 2>/dev/null || true)"
  if [[ "$remote" =~ git@github.com:(.+)\.git ]]; then
    url="https://github.com/${BASH_REMATCH[1]}"
  elif [[ "$remote" =~ https://github.com/(.+)\.git ]]; then
    url="https://github.com/${BASH_REMATCH[1]}"
  else
    echo "$sha"
    return
  fi
  echo "${url}/commit/${sha}"
}

mapfile -t ALL_FILES < <(get_changed_files)

if [[ ${#ALL_FILES[@]} -eq 0 ]]; then
  echo "finish_day: нет изменений для коммита" >&2
  exit 1
fi

declare -A DAY_KEYS=()
DAY_FILES=()
EXTRA_FILES=()

for f in "${ALL_FILES[@]}"; do
  if is_day_file "$f"; then
    key="$(day_key_from_path "$f")"
    if [[ -n "$key" ]]; then
      DAY_KEYS["$key"]=1
    fi
    DAY_FILES+=("$f")
  else
    EXTRA_FILES+=("$f")
  fi
done

if [[ ${#DAY_KEYS[@]} -eq 0 ]]; then
  echo "finish_day: нет изменений в weeks/week-NN/day-DD/ или journal/" >&2
  echo "Изменённые файлы:" >&2
  printf '  %s\n' "${ALL_FILES[@]}" >&2
  exit 1
fi

if [[ ${#DAY_KEYS[@]} -gt 1 ]]; then
  echo "finish_day: изменения в нескольких днях — закоммитьте вручную:" >&2
  for k in "${!DAY_KEYS[@]}"; do
    w="${k%-*}"
    d="${k#*-}"
    echo "  week-${w}/day-${d}" >&2
  done
  exit 1
fi

day_key="${!DAY_KEYS[@]}"
WEEK="${day_key%-*}"
DAY="${day_key#*-}"
WEEK_NUM=$((10#$WEEK))
DAY_NUM=$((10#$DAY))
DAY_DIR="weeks/week-${WEEK}/day-${DAY}"
README="${DAY_DIR}/README.md"

DAY_ONLY=()
for f in "${DAY_FILES[@]}"; do
  if belongs_to_day "$f" "$WEEK" "$DAY"; then
    DAY_ONLY+=("$f")
  else
    EXTRA_FILES+=("$f")
  fi
done

if [[ -z "$MSG" ]]; then
  if [[ -f "$README" ]]; then
    summary="$(awk '
      /^## Задание/ { found=1; next }
      /^## / { if (found) exit }
      found && /^- / { gsub(/^- /, ""); print; exit }
    ' "$README")"
    if [[ -n "$summary" ]]; then
      summary="${summary:0:72}"
      [[ ${#summary} -eq 72 ]] && summary="${summary}…"
      MSG="Week ${WEEK_NUM} day ${DAY_NUM}: ${summary}"
    fi
  fi
  MSG="${MSG:-Week ${WEEK_NUM} day ${DAY_NUM}: assignment.}"
fi

echo "finish_day: week-${WEEK}/day-${DAY}"
echo "  extra files: ${#EXTRA_FILES[@]}"
echo "  day files:   ${#DAY_ONLY[@]}"
echo "  day message: ${MSG}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] коммиты и push не выполнялись"
  exit 0
fi

EXTRA_SHA=""
if [[ ${#EXTRA_FILES[@]} -gt 0 ]]; then
  echo "→ коммит прочих изменений (${#EXTRA_FILES[@]} файлов)..."
  git add -- "${EXTRA_FILES[@]}"
  git commit -m "$(cat <<EOF
Update repo config and tooling.

Cursor rules, AGENTS.md, and other non-assignment changes.
EOF
)"
  EXTRA_SHA="$(git rev-parse HEAD)"
  echo "  extra commit: $(commit_url "$EXTRA_SHA")"
fi

if [[ ${#DAY_ONLY[@]} -eq 0 ]]; then
  echo "finish_day: нет файлов задания для week-${WEEK}/day-${DAY}" >&2
  exit 1
fi

echo "→ коммит задания week-${WEEK}/day-${DAY}..."
git add -- "${DAY_ONLY[@]}"
git commit -m "$(cat <<EOF
${MSG}
EOF
)"
DAY_SHA="$(git rev-parse HEAD)"
DAY_URL="$(commit_url "$DAY_SHA")"

echo "→ push origin master..."
git push origin master

echo ""
echo "DAY_COMMIT=${DAY_URL}"
if [[ -n "$EXTRA_SHA" ]]; then
  echo "EXTRA_COMMIT=$(commit_url "$EXTRA_SHA")"
fi
