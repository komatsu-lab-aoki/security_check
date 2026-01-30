#!/usr/bin/env bash
set -e

echo "[deploy] stop service"
systemctl stop security_check.service

echo "[deploy] git pull"
git pull

echo "[deploy] start service"
systemctl start security_check.service

systemctl status security_check.service --no-pager
