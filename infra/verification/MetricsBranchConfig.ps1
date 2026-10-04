# 本工作区唯一受控指标仓库；会话和分支不能改变业务仓库身份。
$MetricsRepositoryId = 'agent-admin/metrics'

# 部署清单只保存业务身份与环境变量名，凭据始终从当前受控进程读取。
function Get-MetricsBranchCredential([string] $Name, [string] $Field) {
    if (!$Name -or $Name -notmatch '^[A-Z][A-Z0-9_]+$') { throw "配置缺失：$Field" }
    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { throw "配置缺失：$Field" }
    return $value
}

# 严格比较显式仓库业务身份，避免 SSH/HTTP 不同传输地址造成伪差异。
function Assert-MetricsBranchConfig([hashtable] $Configuration) {
    if ($Configuration.service.repositoryId -cne $MetricsRepositoryId) {
        throw 'service.repositoryId 必须为 agent-admin/metrics'
    }
    foreach ($field in @('projectId', 'repositoryId', 'subdir')) {
        if (!$Configuration.service[$field] -or $Configuration.agent[$field] -cne $Configuration.service[$field]) {
            throw "agent/service 配置不一致：$field"
        }
    }
    if ($Configuration.platform.mode -cne 'service-proxy') { throw 'platform.mode 必须为 service-proxy' }
    if ($Configuration.platform.legacyPublisherEnabled -ne $false) { throw 'platform.legacyPublisherEnabled 必须停用' }
    if ($Configuration.service.eventsEnabled -ne $true) { throw 'service.eventsEnabled 必须启用补偿扫描' }
    foreach ($capability in @('branch-development-v1', 'draft-validation-v2')) {
        if ($Configuration.service.capabilities -cnotcontains $capability) { throw "service.capabilities 缺少 $capability" }
    }

    # 只允许一个活动发布通知，且 push/delete 均交由服务核实实际远端。
    $hooks = @($Configuration.hooks | Where-Object { $_.active })
    if ($hooks.Count -ne 1) { throw 'hooks 必须只有一个活动发布目标' }
    $uri = $null
    if (![Uri]::TryCreate($hooks[0].url, [UriKind]::Absolute, [ref] $uri) -or
        $uri.Scheme -notin @('http', 'https') -or $uri.AbsolutePath -cne '/internal/git-branch-events' -or $uri.Query -or $uri.UserInfo) {
        throw 'hooks.url 必须指向服务 /internal/git-branch-events'
    }
    if ($hooks[0].events -notcontains 'push' -or $hooks[0].events -notcontains 'delete') { throw 'hooks.events 缺少 push/delete' }
    $secret = Get-MetricsBranchCredential $Configuration.service.secretEnvironment 'service.secretEnvironment'
    $hookSecret = Get-MetricsBranchCredential $hooks[0].secretEnvironment 'hooks.secretEnvironment'
    if ($secret -cne $hookSecret) { throw 'hooks.secretEnvironment 与 service.secretEnvironment 不一致' }
    $serviceToken = Get-MetricsBranchCredential $Configuration.service.tokenEnvironment 'service.tokenEnvironment'
    $agentToken = Get-MetricsBranchCredential $Configuration.agent.tokenEnvironment 'agent.tokenEnvironment'
    if ($serviceToken -cne $agentToken) { throw 'agent.tokenEnvironment 与 service.tokenEnvironment 不一致' }
}
