#!/usr/bin/env bash
set -e

echo "[deploy] git pull"
git pull

echo "[deploy] restart service"
systemctl restart security_check.service

systemctl status security_check.service --no-pager
