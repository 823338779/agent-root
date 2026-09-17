param([ValidateRange(1024, 65535)][int] $Port = 2222)

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$compose = Join-Path $workspace 'infra/compose/compose.yml'
$sshRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.ssh'
$clientDirectory = Join-Path $sshRoot 'agent-metrics-git'
$key = Join-Path $clientDirectory 'id_ed25519'
$knownHosts = Join-Path $clientDirectory 'known_hosts'
$clientConfig = Join-Path $clientDirectory 'config'
$sshConfig = Join-Path $sshRoot 'config'
$publicDirectory = Join-Path $workspace 'tmp/git-service'
$hostAlias = 'agent-metrics-git'
$container = 'git'

function Invoke-Checked([string] $Program, [string[]] $Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program 执行失败，退出码 $LASTEXITCODE" }
}

# 独立客户端密钥只生成一次，绝不覆盖已有私钥；仓库内仅保存被忽略的公钥副本。
New-Item -ItemType Directory -Path $clientDirectory, $publicDirectory -Force | Out-Null
if (!(Test-Path -LiteralPath $key)) {
    Invoke-Checked ssh-keygen @('-q', '-t', 'ed25519', '-N', '', '-f', $key)
}
if (!(Test-Path -LiteralPath "$key.pub")) { throw '客户端公钥缺失，请修复现有密钥对后重试' }
# SSH 相对 Include 与 ~ 路径同时兼容 Windows OpenSSH 和 Git 自带的 MSYS SSH。
$include = 'Include agent-metrics-git/config'
$existing = if (Test-Path -LiteralPath $sshConfig) { [IO.File]::ReadAllText($sshConfig) } else { '' }
if (!$existing.Contains($include) -and $existing -match '(?im)^\s*Host\s+.*\bagent-metrics-git\b') {
    throw 'SSH 配置已有同名 Host，请先核对，初始化不会覆盖它'
}
Copy-Item -LiteralPath "$key.pub" -Destination (Join-Path $publicDirectory 'authorized_keys')

# 只启动新增 Git 服务，不重建 PostgreSQL、Redis 或产品进程。
$env:GIT_SSH_PORT = "$Port"
# 显式创建或复用外部卷；更换 Compose 项目名不会换仓库，也不会隐式删除数据。
foreach ($volume in @('agent-platform_git-data', 'agent-platform_git-host-keys')) {
    Invoke-Checked docker @('volume', 'create', $volume)
}
Invoke-Checked docker @('compose', '-f', $compose, 'up', '-d', '--build', '--wait', '--wait-timeout', '90', 'git')
$hostKey = & docker exec $container cat /var/lib/git-host-keys/ssh_host_ed25519_key.pub
if ($LASTEXITCODE -ne 0 -or !$hostKey) { throw '读取本地容器主机公钥失败' }
$trustedLine = "[127.0.0.1]:$Port $($hostKey.Trim())`n"
if ((Test-Path -LiteralPath $knownHosts) -and [IO.File]::ReadAllText($knownHosts) -ne $trustedLine) {
    throw 'SSH 主机公钥或端口变化，请核对持久卷；不会自动覆盖已有信任记录'
}
[IO.File]::WriteAllText($knownHosts, $trustedLine)

# 从本机 Docker 控制通道建立主机信任；不使用不经核对的网络 keyscan。
$settings = @"
Host $hostAlias
    HostName 127.0.0.1
    Port $Port
    User git
    IdentityFile ~/.ssh/agent-metrics-git/id_ed25519
    IdentitiesOnly yes
    BatchMode yes
    StrictHostKeyChecking yes
    UserKnownHostsFile ~/.ssh/agent-metrics-git/known_hosts

"@
[IO.File]::WriteAllText($clientConfig, $settings)
if (!$existing.Contains($include)) {
    if (Test-Path -LiteralPath $sshConfig) {
        Copy-Item -LiteralPath $sshConfig -Destination (Join-Path $clientDirectory ('config-backup-' + [DateTime]::UtcNow.Ticks))
    }
    [IO.File]::WriteAllText($sshConfig, "$include`n$existing")
}
$env:DATA_AGENT_GIT_ENABLED = 'true'
$env:DATA_AGENT_GIT_REMOTE_URI = "ssh://git@$hostAlias/srv/git/metrics.git"
Invoke-Checked git @('ls-remote', $env:DATA_AGENT_GIT_REMOTE_URI, 'refs/heads/main')
Write-Output 'Git 服务已就绪；当前 PowerShell 已设置 DATA_AGENT_GIT_ENABLED 和 DATA_AGENT_GIT_REMOTE_URI。'
