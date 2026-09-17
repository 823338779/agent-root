#!/bin/sh
set -eu

# 不执行客户端传来的 shell 文本；只把完全匹配的两种命令映射到固定仓库。
repository=/srv/git/metrics.git
case "${SSH_ORIGINAL_COMMAND:-}" in
    "git-upload-pack '$repository'") exec git-upload-pack "$repository" ;;
    "git-receive-pack '$repository'") exec git-receive-pack "$repository" ;;
    *) printf '%s\n' 'Only Git clone/fetch/push for metrics.git is allowed.' >&2; exit 1 ;;
esac
