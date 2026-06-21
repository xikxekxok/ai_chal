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

find_plan_for_day() {
  local week="$1" day="$2"
  local plans_dir=".cursor/plans"
  local day_path="weeks/week-${week}/day-${day}"
  local journal_path="journal/week-${week}/day-${day}.md"
  local -a matches=()

  shopt -s nullglob
  for plan in "$plans_dir"/*.plan.md; do
    if grep -qF "$day_path" "$plan" 2>/dev/null || grep -qF "$journal_path" "$plan" 2>/dev/null; then
      matches+=("$plan")
    fi
  done
  shopt -u nullglob

  if [[ ${#matches[@]} -eq 1 ]]; then
    printf '%s\n' "${matches[0]}"
    return 0
  fi
  if [[ ${#matches[@]} -gt 1 ]]; then
    echo "finish_day: несколько plan-файлов для week-${week}/day-${day}:" >&2
    printf '  %s\n' "${matches[@]}" >&2
    exit 1
  fi

  local week_num day_num
  week_num=$((10#$week))
  day_num=$((10#$day))
  shopt -s nullglob
  for plan in \
    "$plans_dir"/week"${week_num}"*day"${day_num}"*.plan.md \
    "$plans_dir"/week-"${week}"*day-"${day}"*.plan.md \
    "$plans_dir"/day_"${day}"_*.plan.md \
    "$plans_dir"/day-"${day}"_*.plan.md; do
    matches+=("$plan")
  done
  shopt -u nullglob

  if [[ ${#matches[@]} -eq 1 ]]; then
    printf '%s\n' "${matches[0]}"
    return 0
  fi
  if [[ ${#matches[@]} -gt 1 ]]; then
    echo "finish_day: несколько plan-файлов по имени для week-${week}/day-${day}:" >&2
    printf '  %s\n' "${matches[@]}" >&2
    exit 1
  fi
  return 1
}

remove_from_array() {
  local needle="$1"
  shift
  local -a src=("$@")
  local -a out=()
  local item
  for item in "${src[@]}"; do
    [[ "$item" == "$needle" ]] || out+=("$item")
  done
  printf '%s\n' "${out[@]}"
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

PLAN_FILE=""
if PLAN_FILE="$(find_plan_for_day "$WEEK" "$DAY")"; then
  mapfile -t EXTRA_FILES < <(remove_from_array "$PLAN_FILE" "${EXTRA_FILES[@]+"${EXTRA_FILES[@]}"}")
  already=0
  for f in "${DAY_ONLY[@]}"; do
    [[ "$f" == "$PLAN_FILE" ]] && already=1 && break
  done
  [[ "$already" -eq 0 ]] && DAY_ONLY+=("$PLAN_FILE")
fi

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
if [[ -n "$PLAN_FILE" ]]; then
  echo "  plan file:   ${PLAN_FILE}"
else
  echo "  plan file:   (не найден в .cursor/plans/)"
fi
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

echo ""
echo "DAY_COMMIT=${DAY_URL}"
if [[ -n "$EXTRA_SHA" ]]; then
  echo "EXTRA_COMMIT=$(commit_url "$EXTRA_SHA")"
fi

echo "→ push origin master..."
if ! git push origin master; then
  echo "" >&2
  echo "finish_day: PUSH_FAILED — коммиты созданы локально (ссылки выше), push не выполнен." >&2
  echo "  Частая причина в Cursor: sandbox блокирует DNS/SSH до github.com." >&2
  echo "  Повторите: git push origin master  (агенту — с правами all, не sandbox)." >&2
  exit 1
fi

echo "PUSH_OK=true"
