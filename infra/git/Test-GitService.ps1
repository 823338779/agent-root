param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Forgejo-Service.ps1')

$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$image = 'codeberg.org/forgejo/forgejo:15.0.9-rootless'
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 12)
$container = "forgejo-test-$suffix"
$volume = "$container-data"
$testRoot = Join-Path ([IO.Path]::GetTempPath()) $container
$tmpRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$adminPassword = ConvertTo-SecureString 'Forgejo-Test-Only-Password-2026!' -AsPlainText -Force
$token = $null
$httpPort = $null
$sshPort = $null

function Assert-True([bool] $Condition, [string] $Message) {
    if (!$Condition) { throw $Message }
}

function Assert-Throws([scriptblock] $Action, [string] $MessagePattern) {
    try {
        & $Action
    } catch {
        if ($_.Exception.Message -notmatch $MessagePattern) {
            throw "异常与预期不符：$($_.Exception.Message)"
        }
        return
    }
    throw "预期操作失败，但实际成功：$MessagePattern"
}

# 测试容器始终使用随机命名资源；正式 Forgejo 容器和数据卷不在清理范围内。
function Start-TestContainer([bool] $ReusePorts) {
    $httpBinding = if ($ReusePorts) { "127.0.0.1:${httpPort}:3000" } else { '127.0.0.1::3000' }
    $sshBinding = if ($ReusePorts) { "127.0.0.1:${sshPort}:2222" } else { '127.0.0.1::2222' }
    Invoke-Checked docker @(
        'run', '-d', '--name', $container,
        '-e', 'FORGEJO__database__DB_TYPE=sqlite3',
        '-e', 'FORGEJO__server__ROOT_URL=http://127.0.0.1:3000/',
        '-e', 'FORGEJO__server__START_SSH_SERVER=true',
        '-e', 'FORGEJO__server__SSH_LISTEN_PORT=2222',
        '-e', 'FORGEJO__service__DISABLE_REGISTRATION=true',
        '-e', 'FORGEJO__repository__DEFAULT_BRANCH=main',
        '-e', 'FORGEJO__repository__FORCE_PRIVATE=true',
        '-e', 'FORGEJO__security__INSTALL_LOCK=true',
        '-p', $httpBinding, '-p', $sshBinding,
        '-v', "${volume}:/var/lib/gitea",
        $image
    )
}

try {
    New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
    Invoke-Checked docker @('volume', 'create', $volume)
    Start-TestContainer $false

    $httpPort = ((& docker port $container '3000/tcp') -split ':')[-1].Trim()
    $sshPort = ((& docker port $container '2222/tcp') -split ':')[-1].Trim()
    $baseUri = "http://127.0.0.1:$httpPort"
    Wait-ForgejoHealthy $baseUri

    Ensure-ForgejoAdmin $container $adminPassword
    $wrongPassword = ConvertTo-SecureString 'Forgejo-Wrong-Password-2026!' -AsPlainText -Force
    Ensure-ForgejoAdmin $container $wrongPassword
    Assert-Throws { Assert-ForgejoAdminCredential $baseUri } '管理员密码验证失败'
    Ensure-ForgejoAdmin $container $adminPassword
    Assert-ForgejoAdminCredential $baseUri
    $token = New-ForgejoAccessToken $container
    Ensure-ForgejoRepository $baseUri $token

    # 隔离仓库先放置旧平台目标，切换后禁止自动发布，重复清理不增生。
    $hooksPath = "/repos/$script:ForgejoAdminUsername/$script:ForgejoRepositoryName/hooks"
    Invoke-ForgejoApi 'POST' $baseUri $hooksPath $token @{
        type = 'forgejo'; active = $true; events = @('push')
        config = @{ url = 'http://host.docker.internal:8090/internal/git-sync/events'; content_type = 'json' }
    } | Out-Null
    Disable-MetricsPublishingWebhooks $baseUri $token
    Disable-MetricsPublishingWebhooks $baseUri $token
    $hooks = (Invoke-ForgejoApi 'GET' $baseUri $hooksPath $token $null).Data
    $activeHooks = @($hooks | Where-Object active)
    Assert-True ($activeHooks.Count -eq 0) '旧发布通知没有停用'

    # 客户端密钥只存在于本次随机测试目录，用真实 SSH Git 行为验证服务端配置。
    $key = Join-Path $testRoot 'id_ed25519'
    Invoke-Checked ssh-keygen @('-q', '-t', 'ed25519', '-N', '', '-f', $key)
    $publicKey = [IO.File]::ReadAllText("$key.pub").Trim()
    Ensure-ForgejoSshKey $baseUri $token $publicKey
    Ensure-MainProtection $baseUri $token

    # 重复执行必须复用完全匹配的资源，不得创建重复记录。
    Ensure-ForgejoRepository $baseUri $token
    Ensure-ForgejoSshKey $baseUri $token $publicKey
    Ensure-MainProtection $baseUri $token

    $otherKey = Join-Path $testRoot 'other_ed25519'
    Invoke-Checked ssh-keygen @('-q', '-t', 'ed25519', '-N', '', '-f', $otherKey)
    $otherPublicKey = [IO.File]::ReadAllText("$otherKey.pub").Trim()
    Assert-Throws { Ensure-ForgejoSshKey $baseUri $token $otherPublicKey } '同名 SSH Key'

    $hostKey = Get-ForgejoHostPublicKey $container
    $knownHosts = Join-Path $testRoot 'known_hosts'
    Ensure-ForgejoKnownHost $knownHosts ([int] $sshPort) $hostKey
    $tamperedKnownHosts = Join-Path $testRoot 'tampered-known_hosts'
    [IO.File]::WriteAllText($tamperedKnownHosts, "[127.0.0.1]:$sshPort ssh-rsa INVALID`n")
    Assert-Throws { Ensure-ForgejoKnownHost $tamperedKnownHosts ([int] $sshPort) $hostKey } 'SSH 主机公钥或端口变化'
    $sshCommand = "ssh -F /dev/null -i `"$($key.Replace('\', '/'))`" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=`"$($knownHosts.Replace('\', '/'))`""
    $remote = "ssh://git@127.0.0.1:$sshPort/agent-admin/metrics.git"
    $clone = Join-Path $testRoot 'clone'
    Invoke-Checked git @('-c', "core.sshCommand=$sshCommand", 'clone', $remote, $clone)

    $initial = (& git -C $clone rev-parse HEAD).Trim()
    [IO.File]::WriteAllText((Join-Path $clone 'smoke.txt'), "Forgejo Docker smoke test`n")
    Invoke-Checked git @('-C', $clone, 'add', 'smoke.txt')
    Invoke-Checked git @('-C', $clone, '-c', 'user.name=Forgejo Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'Verify Forgejo service')
    Invoke-Checked git @('-C', $clone, '-c', "core.sshCommand=$sshCommand", 'push', 'origin', 'main')
    $pushed = (& git -C $clone rev-parse HEAD).Trim()

    # main 必须拒绝回退和删除；普通功能分支必须仍可创建。
    & git -C $clone -c "core.sshCommand=$sshCommand" push --force origin "${initial}:refs/heads/main"
    Assert-True ($LASTEXITCODE -ne 0) 'main 错误地接受了强推'
    & git -C $clone -c "core.sshCommand=$sshCommand" push origin ':refs/heads/main'
    Assert-True ($LASTEXITCODE -ne 0) 'main 错误地接受了删除'
    Invoke-Checked git @('-C', $clone, '-c', "core.sshCommand=$sshCommand", 'push', 'origin', 'HEAD:refs/heads/feature-smoke')

    # 关闭注册后，注册页面不得提供可提交的注册表单。
    $signUp = Invoke-WebRequest -Uri "$baseUri/user/sign_up" -SkipHttpErrorCheck
    Assert-True ($signUp.Content -notmatch 'name="user_name"') 'Forgejo 错误地开放了自助注册'

    Remove-ForgejoAccessToken $baseUri $token
    $token = $null
    Invoke-Checked docker @('rm', '-f', $container)
    Start-TestContainer $true
    Wait-ForgejoHealthy $baseUri

    $restoredHostKey = Get-ForgejoHostPublicKey $container
    Assert-True ($restoredHostKey -eq $hostKey) '容器重建后 SSH 主机密钥改变'
    $restoredHead = ((& git -C $clone -c "core.sshCommand=$sshCommand" ls-remote origin refs/heads/main) -split '\s+')[0]
    Assert-True ($LASTEXITCODE -eq 0 -and $restoredHead -eq $pushed) '容器重建后远端提交丢失'

    Write-Output 'PASS：Forgejo Web、幂等初始化、SSH Git、main 保护、功能分支、禁止注册及容器重建持久性。'
} finally {
    if ($token -and $baseUri) {
        try { Remove-ForgejoAccessToken $baseUri $token } catch { Write-Warning '隔离测试 Token 清理失败，测试卷仍将被删除。' }
    }
    & docker rm -f $container 2>$null | Out-Null
    & docker volume rm $volume 2>$null | Out-Null
    # 递归清理前验证随机目录严格位于工作区 tmp 下，避免路径计算异常扩大删除范围。
    $resolvedTestRoot = [IO.Path]::GetFullPath($testRoot)
    $tmpPrefix = $tmpRoot.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if ($resolvedTestRoot.StartsWith($tmpPrefix, [StringComparison]::OrdinalIgnoreCase) -and
        $resolvedTestRoot -ne $tmpRoot -and (Test-Path -LiteralPath $resolvedTestRoot)) {
        Remove-Item -LiteralPath $resolvedTestRoot -Recurse -Force
    }
}
