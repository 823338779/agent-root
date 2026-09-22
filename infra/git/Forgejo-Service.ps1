$script:ForgejoAdminUsername = 'agent-admin'
$script:ForgejoAdminEmail = 'agent-admin@localhost.invalid'
$script:ForgejoRepositoryName = 'metrics'
$script:ForgejoDefaultBranch = 'main'
$script:ForgejoTokenName = 'agent-platform-initialize'
$script:ForgejoSshKeyTitle = 'agent-metrics-git'
$script:ForgejoApiPrefix = '/api/v1'
$script:ForgejoHostKeyPath = '/var/lib/gitea/ssh/gitea.rsa.pub'
$script:ForgejoAdminPassword = $null
$script:ForgejoActiveTokenName = $null

# 统一执行外部命令并保留其输出；错误消息不回显参数，避免密码或 Token 泄漏。
function Invoke-Checked([string] $Program, [string[]] $Arguments) {
    $output = & $Program @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "命令执行失败：$Program`n$($output | Out-String)"
    }
    return $output
}

# Forgejo 启动时会短暂接受 TCP 后主动断开，因此健康探测把网络异常视为可重试状态。
function Wait-ForgejoHealthy([string] $BaseUri, [int] $TimeoutSeconds = 120) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri "$BaseUri/api/healthz" -TimeoutSec 3 -ErrorAction Stop
            if ($response.StatusCode -eq 200) { return }
        } catch {
            # 启动窗口内的连接失败和非 200 响应均由截止时间统一处理。
        }
        Start-Sleep -Seconds 1
    } while ([DateTime]::UtcNow -lt $deadline)

    throw "Forgejo 未在 $TimeoutSeconds 秒内通过健康检查：$BaseUri"
}

# 管理员只在缺失时创建；同名但邮箱或管理员权限不符时停止，绝不覆盖既有账户。
function Ensure-ForgejoAdmin([string] $Container, [SecureString] $Password) {
    $script:ForgejoAdminPassword = $Password
    $users = (Invoke-Checked docker @('exec', $Container, 'forgejo', 'admin', 'user', 'list')) -join "`n"
    $userPattern = "(?m)^\s*\d+\s+$([Regex]::Escape($script:ForgejoAdminUsername))\s+(\S+)\s+\S+\s+(\S+)\s+"
    $match = [Regex]::Match($users, $userPattern)
    if ($match.Success) {
        if ($match.Groups[1].Value -ne $script:ForgejoAdminEmail -or $match.Groups[2].Value -ne 'true') {
            throw "Forgejo 同名用户与预期管理员配置不一致：$($script:ForgejoAdminUsername)"
        }
        return
    }

    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Password)
    try {
        $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        Invoke-Checked docker @(
            'exec', $Container, 'forgejo', 'admin', 'user', 'create',
            '--username', $script:ForgejoAdminUsername,
            '--password', $plainPassword,
            '--email', $script:ForgejoAdminEmail,
            '--admin', '--must-change-password=false'
        ) | Out-Null
    } finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
        $plainPassword = $null
    }
}

# Token 仅通过函数返回给当前调用栈；随机后缀避免异常中断遗留的同名 Token 阻塞重试。
function New-ForgejoAccessToken([string] $Container) {
    $script:ForgejoActiveTokenName = "$script:ForgejoTokenName-$([Guid]::NewGuid().ToString('N'))"
    $output = Invoke-Checked docker @(
        'exec', $Container, 'forgejo', 'admin', 'user', 'generate-access-token',
        '--username', $script:ForgejoAdminUsername,
        '--token-name', $script:ForgejoActiveTokenName,
        '--scopes', 'write:repository,write:user',
        '--raw'
    )
    return (($output -join "`n").Trim())
}

# HTTP 封装只返回状态码和解析结果；异常中不包含 Authorization Header 或 Token。
function Invoke-ForgejoApi(
    [string] $Method,
    [string] $BaseUri,
    [string] $Path,
    [string] $Token,
    [hashtable] $Body
) {
    $parameters = @{
        Uri = "$BaseUri$script:ForgejoApiPrefix$Path"
        Method = $Method
        Headers = @{ Authorization = "token $Token" }
        SkipHttpErrorCheck = $true
        ErrorAction = 'Stop'
    }
    if ($Body) {
        $parameters.ContentType = 'application/json'
        $parameters.Body = $Body | ConvertTo-Json -Depth 10 -Compress
    }

    try {
        $response = Invoke-WebRequest @parameters
    } catch {
        throw "Forgejo API 请求失败：$Method $Path；$($_.Exception.Message)"
    }

    $data = $null
    if ($response.Content) {
        try { $data = $response.Content | ConvertFrom-Json } catch { $data = $response.Content }
    }
    return [PSCustomObject]@{ StatusCode = [int] $response.StatusCode; Data = $data }
}

# 仓库仅在 404 时创建；已有仓库必须仍为私有且默认分支为 main。
function Ensure-ForgejoRepository([string] $BaseUri, [string] $Token) {
    $path = "/repos/$script:ForgejoAdminUsername/$script:ForgejoRepositoryName"
    $response = Invoke-ForgejoApi 'GET' $BaseUri $path $Token $null
    if ($response.StatusCode -eq 404) {
        $response = Invoke-ForgejoApi 'POST' $BaseUri '/user/repos' $Token @{
            name = $script:ForgejoRepositoryName
            private = $true
            auto_init = $true
            default_branch = $script:ForgejoDefaultBranch
        }
        if ($response.StatusCode -ne 201) { throw "创建 Forgejo 仓库失败，状态码：$($response.StatusCode)" }
    } elseif ($response.StatusCode -ne 200) {
        throw "读取 Forgejo 仓库失败，状态码：$($response.StatusCode)"
    }

    if (!$response.Data.private -or $response.Data.default_branch -ne $script:ForgejoDefaultBranch) {
        throw 'Forgejo 同名仓库不是预期的私有 main 仓库'
    }
}

# SSH Key 按固定标题幂等核对；标题相同但公钥不同表示身份漂移，必须人工处理。
function Ensure-ForgejoSshKey([string] $BaseUri, [string] $Token, [string] $PublicKey) {
    $response = Invoke-ForgejoApi 'GET' $BaseUri '/user/keys?limit=50' $Token $null
    if ($response.StatusCode -ne 200) { throw "读取 Forgejo SSH Key 失败，状态码：$($response.StatusCode)" }
    $existing = @($response.Data) | Where-Object { $_.title -eq $script:ForgejoSshKeyTitle }
    if ($existing.Count -gt 1) { throw 'Forgejo 存在多个同名 SSH Key' }
    if ($existing.Count -eq 1) {
        if ($existing[0].key.Trim() -ne $PublicKey.Trim()) { throw 'Forgejo 同名 SSH Key 与本地公钥不一致' }
        return
    }

    $created = Invoke-ForgejoApi 'POST' $BaseUri '/user/keys' $Token @{
        title = $script:ForgejoSshKeyTitle
        key = $PublicKey.Trim()
        read_only = $false
    }
    if ($created.StatusCode -ne 201) { throw "创建 Forgejo SSH Key 失败，状态码：$($created.StatusCode)" }
}

# main 保护规则允许正常推送，但应用于管理员并拒绝强推；删除受同一保护规则约束。
function Ensure-MainProtection([string] $BaseUri, [string] $Token) {
    $path = "/repos/$script:ForgejoAdminUsername/$script:ForgejoRepositoryName/branch_protections/$script:ForgejoDefaultBranch"
    $response = Invoke-ForgejoApi 'GET' $BaseUri $path $Token $null
    if ($response.StatusCode -eq 404) {
        $created = Invoke-ForgejoApi 'POST' $BaseUri "/repos/$script:ForgejoAdminUsername/$script:ForgejoRepositoryName/branch_protections" $Token @{
            branch_name = $script:ForgejoDefaultBranch
            rule_name = $script:ForgejoDefaultBranch
            enable_push = $true
            enable_force_push = $false
            apply_to_admins = $true
        }
        if ($created.StatusCode -ne 201) { throw "创建 main 保护规则失败，状态码：$($created.StatusCode)" }
        $response = $created
    } elseif ($response.StatusCode -ne 200) {
        throw "读取 main 保护规则失败，状态码：$($response.StatusCode)"
    }

    if ($response.Data.rule_name -ne $script:ForgejoDefaultBranch -or !$response.Data.enable_push -or !$response.Data.apply_to_admins) {
        throw 'Forgejo main 保护规则与预期不一致'
    }
}

# Forgejo 禁止 Token 删除自身，因此用仅驻留当前进程的管理员密码执行 Basic Auth 撤销。
function Remove-ForgejoAccessToken([string] $BaseUri, [string] $Token) {
    if (!$script:ForgejoAdminPassword -or !$script:ForgejoActiveTokenName) {
        throw '缺少撤销 Forgejo 临时 Token 所需的当前进程凭据'
    }
    $credential = [PSCredential]::new($script:ForgejoAdminUsername, $script:ForgejoAdminPassword)
    $uri = "$BaseUri$script:ForgejoApiPrefix/users/$script:ForgejoAdminUsername/tokens/$script:ForgejoActiveTokenName"
    try {
        $response = Invoke-WebRequest -Uri $uri -Method DELETE -Authentication Basic -Credential $credential `
            -AllowUnencryptedAuthentication -SkipHttpErrorCheck -ErrorAction Stop
    } catch {
        throw "撤销 Forgejo 临时 Token 请求失败：$($_.Exception.Message)"
    } finally {
        $credential = $null
        $Token = $null
    }
    if ($response.StatusCode -ne 204) { throw "撤销 Forgejo 临时 Token 失败，状态码：$($response.StatusCode)" }
    $script:ForgejoActiveTokenName = $null
    $script:ForgejoAdminPassword = $null
}

# 内置 SSH Server 当前只使用持久卷中的 RSA 主机公钥；路径或数量异常时拒绝静默换钥。
function Get-ForgejoHostPublicKey([string] $Container) {
    $key = (Invoke-Checked docker @('exec', $Container, 'sh', '-c', "test -f '$script:ForgejoHostKeyPath' && cat '$script:ForgejoHostKeyPath'")) -join "`n"
    $key = $key.Trim()
    if ($key -notmatch '^ssh-rsa\s+[A-Za-z0-9+/=]+(?:\s+.*)?$') {
        throw 'Forgejo SSH 主机公钥不存在或格式无效'
    }
    return $key
}

# 专用 known_hosts 首次写入后只接受完全一致的主机、端口和公钥，防止静默信任漂移。
function Ensure-ForgejoKnownHost([string] $Path, [int] $Port, [string] $HostPublicKey) {
    $trustedLine = "[127.0.0.1]:$Port $($HostPublicKey.Trim())`n"
    if ((Test-Path -LiteralPath $Path) -and [IO.File]::ReadAllText($Path) -ne $trustedLine) {
        throw 'SSH 主机公钥或端口变化，请核对持久卷；不会自动覆盖已有信任记录'
    }
    [IO.File]::WriteAllText($Path, $trustedLine)
}
