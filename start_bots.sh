#!/usr/bin/env bash
set -euo pipefail

TELEGRAM_PORT="${TELEGRAM_PORT:-7860}"
DISCORD_PORT="${DISCORD_PORT:-7861}"
WECHAT_PORT="${WECHAT_PORT:-7862}"

declare -a bot_pids=()
declare -a bot_names=()

trim() {
    local value="${1:-}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

apply_env_text() {
    local raw text line key value
    raw="$(trim "${ENV_TEXT:-}")"
    if [[ -z "$raw" ]]; then
        raw="$(trim "${ENV_CONTENT:-}")"
    fi
    if [[ -z "$raw" ]]; then
        return
    fi

    text="${raw//$'\r\n'/$'\n'}"
    text="${text//$'\r'/$'\n'}"
    if [[ "$text" != *$'\n'* && "$text" == *"\\n"* ]]; then
        text="${text//\\n/$'\n'}"
    fi

    while IFS= read -r line; do
        line="$(trim "$line")"
        if [[ -z "$line" || "$line" == \#* ]]; then
            continue
        fi
        if [[ "$line" == export\ * ]]; then
            line="$(trim "${line#export }")"
        fi
        if [[ "$line" != *=* ]]; then
            continue
        fi
        key="$(trim "${line%%=*}")"
        value="$(trim "${line#*=}")"
        if [[ ! "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
            continue
        fi
        if [[ "${#value}" -ge 2 ]]; then
            if [[ "${value:0:1}" == '"' && "${value: -1}" == '"' ]]; then
                value="${value:1:${#value}-2}"
            elif [[ "${value:0:1}" == "'" && "${value: -1}" == "'" ]]; then
                value="${value:1:${#value}-2}"
            fi
        fi
        if [[ -z "${!key:-}" ]]; then
            export "${key}=${value}"
        fi
    done <<< "$text"
}

apply_env_text

BROWSER_HEADLESS="$(trim "${BROWSER_HEADLESS:-1}")"

is_configured_token() {
    local token
    token="$(trim "${1:-}")"
    if [[ -z "$token" ]]; then
        return 1
    fi

    case "$token" in
        your_telegram_bot_token_here|your_discord_bot_token_here|changeme|CHANGE_ME)
            return 1
            ;;
    esac
    return 0
}

start_bot() {
    local name="$1"
    local script="$2"
    local port="$3"
    local headless_mode

    headless_mode="${BROWSER_HEADLESS,,}"

    echo ">>> Starting ${name} bot on PORT=${port}"
    if [[ "$headless_mode" =~ ^(0|false|no|off|headed)$ ]] \
        && command -v xvfb-run >/dev/null 2>&1 \
        && command -v xauth >/dev/null 2>&1; then
        PORT="$port" xvfb-run -a python "$script" &
    else
        if [[ "$headless_mode" =~ ^(0|false|no|off|headed)$ ]] \
            && command -v xvfb-run >/dev/null 2>&1 \
            && ! command -v xauth >/dev/null 2>&1; then
            echo ">>> xauth not found; falling back to direct python launch"
        fi
        PORT="$port" python "$script" &
    fi

    bot_pids+=("$!")
    bot_names+=("$name")
}

terminate_children() {
    local pid
    for pid in "${bot_pids[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    if ((${#bot_pids[@]} > 0)); then
        wait "${bot_pids[@]}" 2>/dev/null || true
    fi
}

if is_configured_token "${TELEGRAM_BOT_TOKEN:-}"; then
    start_bot "Telegram" "bot.py" "$TELEGRAM_PORT"
else
    echo ">>> Telegram disabled (TELEGRAM_BOT_TOKEN is not configured)"
fi

if is_configured_token "${DISCORD_BOT_TOKEN:-}"; then
    start_bot "Discord" "discord_bot.py" "$DISCORD_PORT"
else
    echo ">>> Discord disabled (DISCORD_BOT_TOKEN is not configured)"
fi

if [[ "${WECHAT_ENABLED:-}" =~ ^([1Yy]|[Tt][Rr][Uu][Ee]|[Yy][Ee][Ss]|[Oo][Nn])$ ]]; then
    start_bot "WeChat" "wechat_bot.py" "$WECHAT_PORT"
else
    echo ">>> WeChat disabled (WECHAT_ENABLED is not enabled)"
fi

if ((${#bot_pids[@]} == 0)); then
    echo ">>> No bot process configured. Set TELEGRAM_BOT_TOKEN and/or DISCORD_BOT_TOKEN, or enable WECHAT_ENABLED=1."
    exit 1
fi

trap 'terminate_children; exit 0' INT TERM

status=0
if ((${#bot_pids[@]} == 1)); then
    if wait "${bot_pids[0]}"; then
        status=0
    else
        status=$?
    fi
else
    if wait -n "${bot_pids[@]}"; then
        status=0
    else
        status=$?
    fi
    echo ">>> One bot process exited (status=${status}), stopping remaining bot processes."
fi

terminate_children
exit "$status"
