# 配套部署清单只有新版协议身份；不推断仓库，不执行网络或写操作。
function Get-MetricsBranchCredential([string] $Name, [string] $Field) {
    if (!$Name -or $Name -notmatch '^[A-Z][A-Z0-9_]+$') { throw "配置缺失：$Field" }
    $value=[Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) { throw "配置缺失：$Field" }
    return $value
}
function Assert-MetricsBranchConfig([hashtable] $Configuration) {
    $required=@('agentBaseUrl','metricPlatformBaseUrl','dbtServiceBaseUrl','agentProjectId','repository','branchName',
        'previewBinding','previewConfigVersion','previewSchemaName','productionBinding','productionConfigVersion','productionSchemaName',
        'dbtServiceTokenEnvironment','platformTokenEnvironment')
    $allowed=$required+@('agentTokenEnvironment')
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
    # schema 直接交给构建接口，必须与服务端固定 schema 的命名约束一致。
    foreach ($field in @('previewSchemaName','productionSchemaName')) {
        if ($Configuration[$field] -cnotmatch '^[a-z][a-z0-9_]{0,255}$') { throw "无效schema：$field" }
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
        @{name='service';base=$Configuration.dbtServiceBaseUrl;health='/health/ready';schema='/openapi.json';paths=@('/v3/builds','/v3/deployments/current','/v3/query','/v3/query/available-dimensions')},
        @{name='agent';base=$Configuration.agentBaseUrl;health='/actuator/health';schema='/api/v1/development/contract';paths=@('/api/v1/agent-sessions/{sessionId}/development/save','/api/v1/agent-sessions/{sessionId}/development/preview','/api/v1/agent-sessions/{sessionId}/development/deliver')},
        @{name='platform';base=$Configuration.metricPlatformBaseUrl;health='/actuator/health';schema='/api/v3/dbt/contract';paths=@('/api/v3/dbt/builds/{buildId}/catalog','/api/v3/dbt/builds/{buildId}/queries')}
    )
    foreach ($component in $specs) {
        try {
            $headers=Get-MetricsContractHeaders $Configuration $component.name
            $base=$component.base.TrimEnd('/')
            $health=& $Read ($base+$component.health) $headers
            if (!$health -or $health.status -notin @('UP','ready','ok')) { throw '健康状态未就绪' }
            $schema=& $Read ($base+$component.schema) $headers
            if ($component.name -ne 'service' -and $schema.protocolVersion -cne 'build-deployment-v3') { throw '协议版本不匹配' }
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
        foreach ($field in @('repository','previewBinding','previewConfigVersion','previewSchemaName','productionBinding','productionConfigVersion','productionSchemaName')) {
            if ($config.$field -cne $Configuration[$field]) { throw '配置不匹配' }
        }
    } catch { $errors.Add('agent: 项目仓库或环境配置版本不匹配') }
    return @{Valid=($errors.Count -eq 0);Errors=@($errors)}
}
