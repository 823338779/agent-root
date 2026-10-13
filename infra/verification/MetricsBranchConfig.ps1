# 配套部署清单只有新版协议身份；不推断仓库，不执行网络或写操作。
function Get-MetricsBranchCredential([string] $Name, [string] $Field) {
    if (!$Name -or $Name -notmatch '^[A-Z][A-Z0-9_]+$') { throw "配置缺失：$Field" }
    $value=[Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { throw "配置缺失：$Field" }
    return $value
}
function Assert-MetricsBranchConfig([hashtable] $Configuration) {
    $required=@('agentBaseUrl','metricPlatformBaseUrl','dbtServiceBaseUrl','agentProjectId','repository','branchName',
        'dbtServiceTokenEnvironment','platformTokenEnvironment')
    $allowed=$required+@('agentTokenEnvironment','previewExecution','productionExecution')
    foreach ($key in $Configuration.Keys) {
        if ($key -cnotin $allowed) { throw "不接受旧配置或未知字段：$key" }
    }
    foreach ($field in $required) {
        if ($Configuration[$field] -isnot [string] -or [string]::IsNullOrWhiteSpace($Configuration[$field])) { throw "配置缺失：$field" }
    }
    foreach ($field in @('agentBaseUrl','metricPlatformBaseUrl','dbtServiceBaseUrl')) {
        $uri=$null
        if (![Uri]::TryCreate($Configuration[$field],[UriKind]::Absolute,[ref]$uri) -or
            $uri.Scheme -notin @('http','https') -or $uri.UserInfo -or $uri.Query -or $uri.Fragment) { throw "无效服务地址：$field" }
    }
    # 完整快照必填；基础设施映射与 secret 是否可用由服务端再次核验。
    foreach ($field in @('previewExecution','productionExecution')) {
        $snapshot=$Configuration[$field]
        $identity=[Guid]::Empty
        if (!$snapshot -or ![Guid]::TryParse([string]$snapshot.environmentId,[ref]$identity) -or
            $snapshot.configVersion -lt 1 -or $snapshot.threads -lt 1 -or $snapshot.threads -gt 32) { throw "无效快照：$field" }
        foreach ($identifier in @('catalog','schema')) {
            if ($snapshot[$identifier] -cnotmatch '^[a-z][a-z0-9_]{0,62}$') { throw "无效快照：$field.$identifier" }
        }
        if (!$snapshot.credentialRef -or !$snapshot.businessTimezone -or !$snapshot.connection.instanceId -or
            $snapshot.connection.type -notin @('starrocks','postgres','duckdb')) { throw "无效快照：$field" }
        $allowedSnapshot=@('environmentId','configVersion','connection','credentialRef','catalog','schema','threads','businessTimezone')
        if (@($snapshot.Keys | Where-Object {$_ -cnotin $allowedSnapshot}).Count) { throw "未知快照字段：$field" }
    }
    if ($Configuration.branchName -ceq 'main' -or $Configuration.branchName -match '^refs/|^[-/]|[\x00-\x20~^:?*\[\\]|\.\.|@\{|[/.]$') {
        throw 'branchName 必须为非 main 的真实 Git 短分支名'
    }
    foreach ($field in @('dbtServiceTokenEnvironment','platformTokenEnvironment','agentTokenEnvironment')) {
        if ($Configuration.ContainsKey($field)) { Get-MetricsBranchCredential $Configuration[$field] $field | Out-Null }
    }
}
# Header只由组件自己的配置生成；不复用上游或其他服务凭据。
function Get-MetricsContractHeaders([hashtable] $Configuration, [string] $Component) {
    $field=switch ($Component) { 'agent' {'agentTokenEnvironment'} 'platform' {'platformTokenEnvironment'} 'service' {'dbtServiceTokenEnvironment'} default {throw '未知组件'} }
    $headers=@{Accept='application/json'}
    if ($Configuration[$field]) { $headers.Authorization='Bearer '+(Get-MetricsBranchCredential $Configuration[$field] $field) }
    return $headers
}
function Invoke-MetricsContractRead([string] $Url,[hashtable] $Headers) {
    try { return Invoke-RestMethod -Uri $Url -Headers $Headers -Method Get -TimeoutSec 20 -MaximumRedirection 0 }
    catch { throw '服务读取失败，检查对应组件的网络、身份及协议版本' }
}
# 仅GET预检；任何组件缺少新版路径或固定配置不一致都禁止闭环写入。
function Test-MetricsContractPreflight([hashtable] $Configuration,[scriptblock] $Read={param($u,$h) Invoke-MetricsContractRead $u $h}) {
    Assert-MetricsBranchConfig $Configuration
    $errors=[Collections.Generic.List[string]]::new()
    $specs=@(
        @{name='service';base=$Configuration.dbtServiceBaseUrl;health='/health/ready';schema='/openapi.json';paths=@('/builds','/deployments/current','/query','/query/available-dimensions')},
        @{name='agent';base=$Configuration.agentBaseUrl;health='/actuator/health';schema='/api/v1/development/contract';paths=@('/api/v1/agent-sessions/{sessionId}/development/save','/api/v1/agent-sessions/{sessionId}/development/preview','/api/v1/agent-sessions/{sessionId}/development/deliver')},
        @{name='platform';base=$Configuration.metricPlatformBaseUrl;health='/actuator/health';schema='/api/dbt/contract';paths=@('/api/dbt/builds/{buildId}/catalog','/api/dbt/builds/{buildId}/queries')}
    )
    foreach ($component in $specs) {
        try {
            $headers=Get-MetricsContractHeaders $Configuration $component.name
            $base=$component.base.TrimEnd('/')
            $health=& $Read ($base+$component.health) $headers
            if (!$health -or $health.status -notin @('UP','ready','ok')) { throw '健康状态未就绪' }
            $schema=& $Read ($base+$component.schema) $headers
            if ($component.name -ne 'service' -and $schema.protocolVersion -cne 'execution-snapshot') { throw '协议版本不匹配' }
            foreach ($path in $component.paths) {
                $hasPath=$false
                if($schema.paths -is [System.Collections.IDictionary]){
                    $hasPath=$schema.paths.Keys -ccontains $path
                }elseif($schema.paths){
                    $hasPath=$schema.paths.PSObject.Properties.Name -ccontains $path
                }
                if(!$hasPath){throw '缺少新版schema路径'}
            }
        } catch { $errors.Add($component.name+': 健康或新版 schema 不匹配') }
    }
    try {
        $path=$Configuration.agentBaseUrl.TrimEnd('/')+'/api/v1/agent-projects/'+[Uri]::EscapeDataString($Configuration.agentProjectId)+'/development-config'
        $config=& $Read $path (Get-MetricsContractHeaders $Configuration 'agent')
        if ($config.repository -cne $Configuration.repository) { throw '仓库不匹配' }
        foreach ($environment in @('previewExecution','productionExecution')) {
            foreach ($field in @('environmentId','configVersion','credentialRef','catalog','schema','threads','businessTimezone')) {
                if ($config.$environment.$field -cne $Configuration[$environment][$field]) { throw '执行快照不匹配' }
            }
            foreach ($field in @('type','instanceId','host','port','path')) {
                if ($config.$environment.connection.$field -cne $Configuration[$environment].connection[$field]) { throw '连接快照不匹配' }
            }
        }
    } catch { $errors.Add('agent: 项目仓库或环境配置版本不匹配') }
    return @{Valid=($errors.Count -eq 0);Errors=@($errors)}
}
