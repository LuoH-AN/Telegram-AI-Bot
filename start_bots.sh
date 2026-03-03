#!/usr/bin/env bash
set -euo pipefail

TELEGRAM_PORT="${TELEGRAM_PORT:-7860}"
DISCORD_PORT="${DISCORD_PORT:-7861}"

declare -a bot_pids=()
declare -a bot_names=()

trim() {
    local value="${1:-}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

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

    echo ">>> Starting ${name} bot on PORT=${port}"
    if command -v xvfb-run >/dev/null 2>&1; then
        PORT="$port" xvfb-run -a python "$script" &
    else
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

if ((${#bot_pids[@]} == 0)); then
    echo ">>> No bot token configured. Set TELEGRAM_BOT_TOKEN and/or DISCORD_BOT_TOKEN."
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
