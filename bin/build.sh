#!/bin/sh
cd "$(dirname "$0")"
# Используем docker compose (без дефиса) если доступен
if docker compose version > /dev/null 2>&1; then
    docker compose up --build
    docker cp fest-engine:/app/bin/fest_engine.tar.gz ./fest_engine-linux-x64-minimal.tar.gz
    docker compose down
else
    docker-compose up --build
    docker cp fest-engine:/app/bin/fest_engine.tar.gz ./fest_engine-linux-x64-minimal.tar.gz
    docker-compose down
fi