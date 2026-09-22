param(
    [ValidateRange(1024, 65535)][int] $Port = 2222,
    [SecureString] $AdminPassword
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Forgejo-Service.ps1')

$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$compose = Join-Path $workspace 'infra/compose/compose.yml'
$forgejoVolume = 'agent-platform_forgejo-data'
$container = 'forgejo'
$baseUri = 'http://127.0.0.1:3000'
$hostAlias = 'agent-metrics-git'
$remoteUri = "ssh://git@$hostAlias/agent-admin/metrics.git"
$sshRoot = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.ssh'
$clientDirectory = Join-Path $sshRoot $hostAlias
$key = Join-Path $clientDirectory 'id_ed25519'
$knownHosts = Join-Path $clientDirectory 'known_hosts'
$clientConfig = Join-Path $clientDirectory 'config'
$sshConfig = Join-Path $sshRoot 'config'

# 客户端密钥只生成一次；缺少公钥时停止，避免覆盖已有私钥或改变 Agent 身份。
New-Item -ItemType Directory -Path $clientDirectory -Force | Out-Null
if (!(Test-Path -LiteralPath $key)) {
    Invoke-Checked ssh-keygen @('-q', '-t', 'ed25519', '-N', '', '-f', $key) | Out-Null
}
if (!(Test-Path -LiteralPath "$key.pub")) {
    throw '客户端公钥缺失，请修复现有密钥对后重试'
}
$publicKey = [IO.File]::ReadAllText("$key.pub").Trim()

# 外部卷先显式创建，随后只启动 Forgejo 服务，不重建其他基础设施容器。
Invoke-Checked docker @('volume', 'create', $forgejoVolume) | Out-Null
$env:GIT_SSH_PORT = "$Port"
Invoke-Checked docker @(
    'compose', '-f', $compose, 'up', '-d', '--wait', '--wait-timeout', '120', 'git'
) | Out-Null
Wait-ForgejoHealthy $baseUri

# 管理员密码仅存在于当前 PowerShell 进程；短期 Token 无论后续成功或失败都尝试撤销。
if (!$AdminPassword) {
    $AdminPassword = Read-Host '请输入 Forgejo 管理员 agent-admin 的密码' -AsSecureString
}
Ensure-ForgejoAdmin $container $AdminPassword
$token = $null
try {
    $token = New-ForgejoAccessToken $container
    Ensure-ForgejoRepository $baseUri $token
    Ensure-ForgejoSshKey $baseUri $token $publicKey
    Ensure-MainProtection $baseUri $token
} finally {
    if ($token) { Remove-ForgejoAccessToken $baseUri $token }
    $token = $null
}

# 主机信任只来自本机 Docker 控制通道；已有记录不一致时拒绝自动覆盖。
$hostKey = Get-ForgejoHostPublicKey $container
Ensure-ForgejoKnownHost $knownHosts $Port $hostKey

# 独立 Include 同时兼容 Windows OpenSSH 与 Git 自带的 MSYS SSH。
$include = 'Include agent-metrics-git/config'
$existing = if (Test-Path -LiteralPath $sshConfig) { [IO.File]::ReadAllText($sshConfig) } else { '' }
if (!$existing.Contains($include) -and $existing -match '(?im)^\s*Host\s+.*\bagent-metrics-git\b') {
    throw 'SSH 配置已有同名 Host，请先核对，初始化不会覆盖它'
}
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
        $backup = Join-Path $clientDirectory ('config-backup-' + [DateTime]::UtcNow.Ticks)
        Copy-Item -LiteralPath $sshConfig -Destination $backup
    }
    [IO.File]::WriteAllText($sshConfig, "$include`n$existing")
}

# 当前进程直接获得 Data Agent V2 所需配置，并用真实 SSH 读取 main 作为最终验收。
$env:DATA_AGENT_GIT_ENABLED = 'true'
$env:DATA_AGENT_GIT_REMOTE_URI = $remoteUri
Invoke-Checked git @('ls-remote', $remoteUri, 'refs/heads/main')
Write-Output "Forgejo 已就绪：$baseUri；当前 PowerShell 已设置 DATA_AGENT_GIT_ENABLED 和 DATA_AGENT_GIT_REMOTE_URI。"
