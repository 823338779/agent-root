#!/bin/sh
set -eu

repository=/srv/git/metrics.git
host_key=/var/lib/git-host-keys/ssh_host_ed25519_key
authorized_keys=/run/keys/authorized_keys

# 公钥由部署端只读挂载；复制到 Linux 文件系统以获得严格的 SSH 权限。
test -s "$authorized_keys" || { echo 'Initialize authorized_keys before starting Git.' >&2; exit 1; }
mkdir -p /home/git/.ssh /var/lib/git-host-keys /run/sshd /srv/git
cp "$authorized_keys" /home/git/.ssh/authorized_keys
chown -R git:git /home/git/.ssh
chmod 700 /home/git/.ssh
chmod 600 /home/git/.ssh/authorized_keys
chmod 700 /var/lib/git-host-keys
if [ ! -f "$host_key" ]; then
    ssh-keygen -q -t ed25519 -N '' -f "$host_key"
fi

# 只初始化空卷；已有历史绝不覆盖。无 main 的已有仓库应人工检查，不能自动重置。
if [ ! -d "$repository" ]; then
    chown git:git /srv/git
    su-exec git git init --bare --initial-branch=main "$repository"
    tree=$(printf '' | su-exec git git --git-dir="$repository" mktree)
    commit=$(printf '%s\n' 'Initialize main' | su-exec git git --git-dir="$repository" \
        -c user.name='Repository Bootstrap' -c user.email=bootstrap@example.invalid commit-tree "$tree")
    su-exec git git --git-dir="$repository" update-ref refs/heads/main "$commit"
fi
su-exec git git --git-dir="$repository" rev-parse --verify refs/heads/main >/dev/null
su-exec git git --git-dir="$repository" config receive.denyNonFastForwards true
su-exec git git --git-dir="$repository" config receive.denyDeletes true

# 只维护服务自带的 pre-receive；保留持久卷中运维安装的 post-receive 接点。
cp /usr/local/bin/pre-receive.sh "$repository/hooks/pre-receive"
chown git:git "$repository/hooks/pre-receive"
chmod 755 "$repository/hooks/pre-receive"
exec /usr/sbin/sshd -D -e
