param()

$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$compose = Join-Path $workspace 'infra/compose/compose.yml'
$image = 'agent-platform-git:local'
$testName = 'agent-git-test-' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
$testRoot = Join-Path $workspace "tmp/$testName"
$dataVolume = "$testName-data"
$hostVolume = "$testName-host-keys"

function Invoke-Checked([string] $Program, [string[]] $Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program 执行失败，退出码 $LASTEXITCODE" }
}

# 先校验实际 Compose 接点，再在独立容器和卷中验证，绝不向使用中的指标仓库写测试提交。
$services = & docker compose -f $compose config --services
if ($LASTEXITCODE -ne 0 -or 'git' -notin $services) { throw 'Compose 缺少 git 服务' }
Invoke-Checked docker @('compose', '-f', $compose, 'build', 'git')
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$key = Join-Path $testRoot 'id_ed25519'
Invoke-Checked ssh-keygen @('-q', '-t', 'ed25519', '-N', '', '-f', $key)
$knownHosts = Join-Path $testRoot 'known_hosts'
$publicKey = "$key.pub"
$port = ''

function Start-TestContainer {
    $binding = if ($port) { "127.0.0.1:${port}:22" } else { '127.0.0.1::22' }
    Invoke-Checked docker @('run', '-d', '--name', $testName, '-p', $binding,
        '-v', "${dataVolume}:/srv/git", '-v', "${hostVolume}:/var/lib/git-host-keys",
        '--mount', "type=bind,source=$publicKey,target=/run/keys/authorized_keys,readonly", $image)
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $health = & docker inspect --format '{{.State.Health.Status}}' $testName
        if ($health -eq 'healthy') { return }
        Start-Sleep -Seconds 1
    }
    throw 'Git 测试容器未健康启动'
}

try {
    Start-TestContainer
    $port = ((& docker port $testName '22/tcp') -split ':')[-1].Trim()
    $hostKey = (& docker exec $testName cat /var/lib/git-host-keys/ssh_host_ed25519_key.pub).Trim()
    [IO.File]::WriteAllText($knownHosts, "[127.0.0.1]:$port $hostKey`n")
    $ssh = "ssh -F /dev/null -i `"$($key.Replace('\', '/'))`" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=`"$($knownHosts.Replace('\', '/'))`""
    $remote = "ssh://git@127.0.0.1:$port/srv/git/metrics.git"
    $clone = Join-Path $testRoot 'clone'
    Invoke-Checked git @('-c', "core.sshCommand=$ssh", 'clone', $remote, $clone)
    $initial = (& git -C $clone rev-parse HEAD).Trim()
    [IO.File]::WriteAllText((Join-Path $clone 'smoke.txt'), "Git Docker smoke test`n")
    Invoke-Checked git @('-C', $clone, 'add', 'smoke.txt')
    Invoke-Checked git @('-C', $clone, '-c', 'user.name=Git Service Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'Verify Git service')
    Invoke-Checked git @('-C', $clone, '-c', "core.sshCommand=$ssh", 'push', 'origin', 'main')
    $pushed = (& git -C $clone rev-parse HEAD).Trim()

    # 验证服务端保护确实生效，而非仅检查配置文本。
    foreach ($refspec in @("${initial}:refs/heads/main", ':refs/heads/main', 'HEAD:refs/heads/other')) {
        & git -C $clone -c "core.sshCommand=$ssh" push --force origin $refspec
        if ($LASTEXITCODE -eq 0) { throw "服务端错误地接受了受限推送：$refspec" }
    }
    & ssh -F NUL -i $key -p $port -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$knownHosts" git@127.0.0.1 id
    if ($LASTEXITCODE -eq 0) { throw 'Git 身份不应执行普通 shell 命令' }

    # 删除并重建容器，但复用独立测试卷，验证仓库及 SSH 信任关系跨容器生命周期保留。
    Invoke-Checked docker @('rm', '-f', $testName)
    Start-TestContainer
    $restoredKey = (& docker exec $testName cat /var/lib/git-host-keys/ssh_host_ed25519_key.pub).Trim()
    if ($restoredKey -ne $hostKey) { throw '重建容器后 SSH 主机密钥改变' }
    $remoteHead = (& git -C $clone -c "core.sshCommand=$ssh" ls-remote origin refs/heads/main)
    if ($LASTEXITCODE -ne 0 -or ($remoteHead -split '\s+')[0] -ne $pushed) { throw '重建后远端提交丢失' }
    Write-Output 'PASS：初始化、SSH clone/push、强推/删除/额外分支及 shell 拒绝、容器重建后数据与主机密钥保留。'
} finally {
    # 仅清理本次随机命名的测试容器和测试卷，不操作正式服务与已有 PostgreSQL 数据。
    & docker rm -f $testName 2>$null | Out-Null
    & docker volume rm $dataVolume $hostVolume 2>$null | Out-Null
}
