#!/usr/bin/env sh

set -eu

if ! command -v uv >/dev/null 2>&1; then
    echo "未找到 uv，请先安装 uv 后再运行此脚本。" >&2
    exit 1
fi

project_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

uv tool install --reinstall "$project_directory"
uv tool update-shell

echo "PathCraft 已安装。重新打开终端后，输入 pathcraft 即可启动。"
