#!/bin/bash
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$ROOT/local"
cd "$ROOT"
go build -o "$ROOT/local/tcp_stream_player" .
echo "built: $ROOT/local/tcp_stream_player"
