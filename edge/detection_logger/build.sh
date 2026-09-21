#!/usr/bin/env bash
# detection-logger-postproc.so を Raspberry Pi 5 上でビルドする。
#
# 使い方 (このディレクトリで実行):
#   bash build.sh            build/ にビルドする。システムには何も変更しない。
#   bash build.sh install    ビルド後、既存の .so を build/backup/ へ退避してから
#                            rpicam-apps の post-processing ディレクトリへ配置する (sudo が必要)。
#
# ビルドコマンドは docs/progress/phase-0.5-progress.md の実機確認済みの手順と同一。

set -euo pipefail

cd "$(dirname "$0")"

OUT_DIR="build"
OUT_SO="${OUT_DIR}/detection-logger-postproc.so"
BACKUP_DIR="${OUT_DIR}/backup"
INSTALL_DIR="/usr/lib/aarch64-linux-gnu/rpicam-apps-postproc"
INSTALLED_SO="${INSTALL_DIR}/detection-logger-postproc.so"

check_prerequisites() {
    local missing=0

    for cmd in g++ pkg-config; do
        if ! command -v "${cmd}" > /dev/null 2>&1; then
            echo "ERROR: ${cmd} が見つかりません。" >&2
            missing=1
        fi
    done

    if [ ! -d /usr/include/rpicam-apps ]; then
        echo "ERROR: /usr/include/rpicam-apps がありません (librpicam-app-dev が未導入)。" >&2
        missing=1
    fi

    if ! pkg-config --exists libcamera 2> /dev/null; then
        echo "ERROR: libcamera の開発ファイルが見つかりません (libcamera-dev が未導入)。" >&2
        missing=1
    fi

    if [ "${missing}" -ne 0 ]; then
        echo "必要パッケージ: sudo apt install librpicam-app-dev libcamera-dev libboost-dev" >&2
        exit 1
    fi
}

build() {
    mkdir -p "${OUT_DIR}"

    g++ -std=c++17 -fPIC -shared \
        detection_logger.cpp \
        -o "${OUT_SO}" \
        -I/usr/include/rpicam-apps \
        $(pkg-config --cflags --libs libcamera) \
        -lrpicam_app

    echo "Built: $(pwd)/${OUT_SO}"
}

install_plugin() {
    if [ -f "${INSTALLED_SO}" ]; then
        mkdir -p "${BACKUP_DIR}"
        local backup="${BACKUP_DIR}/detection-logger-postproc.so.$(date +%Y%m%dT%H%M%S)"
        cp "${INSTALLED_SO}" "${backup}"
        echo "Backed up existing plugin: $(pwd)/${backup}"
    fi

    sudo cp "${OUT_SO}" "${INSTALL_DIR}/"
    echo "Installed: ${INSTALLED_SO}"
}

case "${1:-}" in
    "" )
        check_prerequisites
        build
        ;;
    install )
        check_prerequisites
        build
        install_plugin
        ;;
    * )
        echo "Usage: bash build.sh [install]" >&2
        exit 2
        ;;
esac
