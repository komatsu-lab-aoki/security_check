#!/usr/bin/env bash
set -e

echo "[deploy] stop service"
sudo systemctl stop security_check.service

echo "[deploy] git pull"
git pull

echo "[deploy] start service"
sudo systemctl start security_check.service

sudo systemctl status security_check.service --no-pager
