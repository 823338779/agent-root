#!/bin/sh
set -eu

# 产品只维护 main；配置负责拒绝非快进和删除，此处拒绝额外分支及标签。
while read -r old_commit new_commit ref_name; do
    if [ "$ref_name" != refs/heads/main ]; then
        printf '%s\n' 'Only refs/heads/main is writable.' >&2
        exit 1
    fi
done
