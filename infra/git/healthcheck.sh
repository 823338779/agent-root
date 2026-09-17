#!/bin/sh
set -eu

# 检查真实 SSH 监听与已初始化引用；不依赖外部网络或读取客户端私钥。
ssh-keyscan -T 2 -t ed25519 127.0.0.1 >/dev/null 2>&1
su-exec git git --git-dir=/srv/git/metrics.git rev-parse --verify refs/heads/main >/dev/null
