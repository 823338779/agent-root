param(
    [Parameter(Mandatory)][string] $ConfigPath,
    [ValidateRange(30,3600)][int] $TimeoutSeconds=1900,
    [string] $OutputDirectory,
    [string] $ComparisonConfigPath,
    [ValidatePattern('^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$')][string] $ModelDirectory='models'
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'MetricsBranchConfig.ps1')
$config=Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json -AsHashtable
$checks=[Collections.Generic.List[object]]::new()
$identities=[Collections.Generic.List[object]]::new()
$scenario='preflight'
$preflight=$null
$run=[Guid]::NewGuid().ToString('N')
function Assert-Flow([bool]$Condition,[string]$Name) {
    $checks.Add(@{name=$Name;status=$(if($Condition){'PASS'}else{'FAIL'})})
    if(!$Condition){throw 'assertion_failed'}
}
function Invoke-Flow([string]$Component,[string]$Path,[string]$Method='GET',$Body=$null,[string]$Key=$null,[int]$ExpectedStatus=0) {
    $base=switch($Component){'agent'{$config.agentBaseUrl}'platform'{$config.metricPlatformBaseUrl}'service'{$config.dbtServiceBaseUrl}}
    $headers=Get-MetricsContractHeaders $config $Component
    if($Key){$headers['Idempotency-Key']=$Key}
    # 同步目录发现和查询可能包含真实物理执行，使用调用方指定的完整等待预算。
    $args=@{Uri=$base.TrimEnd('/')+$Path;Method=$Method;Headers=$headers;TimeoutSec=$TimeoutSeconds;MaximumRedirection=0;SkipHttpErrorCheck=$true}
    if($null-ne$Body){$args.ContentType='application/json';$args.Body=$Body|ConvertTo-Json -Depth 30 -Compress}
    try{$response=Invoke-WebRequest @args}catch{throw "${Component}_transport_failed"}
    if($response.StatusCode -notin @(200,201,202,204)){throw "${Component}_http_$($response.StatusCode)"}
    if($ExpectedStatus -and $response.StatusCode-ne$ExpectedStatus){throw "${Component}_http_$($response.StatusCode)"}
    if($response.RawContentLength-gt 4194304){throw 'response_too_large'}
    if($response.Content){return $response.Content|ConvertFrom-Json}
}
function Wait-Flow([scriptblock]$Read,[scriptblock]$Complete,[string]$Name) {
    $deadline=[DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do{
        $item=&$Read
        if(&$Complete $item){return $item}
        if([DateTime]::UtcNow-ge$deadline){throw "timeout_$Name"}
        Start-Sleep -Milliseconds 500
    }while($true)
}
function Get-Development([string]$Session){Invoke-Flow agent "/api/v1/agent-sessions/$Session/development"}
function Wait-Operation([string]$Session,$Operation){
    $result=Wait-Flow {Invoke-Flow agent "/api/v1/agent-sessions/$Session/development/operations/$($Operation.operationId)"} {
        param($o) $o.status -cin @('SUCCEEDED','FAILED','BLOCKED')
    } 'operation'
    $identities.Add(@{operationId=$result.operationId;status=$result.status;phase=$result.phase;errorCode=$result.error.code;pushedSha=$result.pushedSha;mergeSha=$result.mergeSha;buildIds=$result.buildIds})
    return $result
}
# 编辑必须经过正常消息和文件工具；不调用测试专用生产写入口。
function Edit-ThroughMessage([string]$Session,[string]$Path,[string]$Content,[string]$Type='CREATE') {
    $before=Get-Development $Session
    $instruction="读取git-repository-maintenance技能。仅在当前固定开发会话中执行文件编辑，不保存、不预览、不交付。操作类型 $Type，工程相对路径 $Path。读取当前文件列表/内容和修订，使用git_files_apply及正确expectedRevision。"
    if($Type-ne'DELETE'){$instruction+=" 文件完整内容（不要改写）：`n$Content"}
    Invoke-Flow agent "/api/v1/agent-sessions/$Session/messages" POST @{content=$instruction} ([Guid]::NewGuid().ToString())|Out-Null
    $view=Wait-Flow {Invoke-Flow agent "/api/v1/agent-sessions/$Session"} {param($v)$v.execution.status -cin @('done','failed','cancelled')} 'agent_edit'
    Assert-Flow ($view.execution.status-ceq'done') 'file_tool_execution_succeeded'
    $after=Get-Development $Session
    Assert-Flow ($after.local.revision-gt$before.local.revision) 'file_revision_advanced'
    if($Type-ne'DELETE'){
        $file=Invoke-Flow agent ("/api/v1/agent-sessions/$Session/development/file?path="+[Uri]::EscapeDataString($Path))
        Assert-Flow ($file.content-ceq$Content) 'full_file_bytes_preserved'
    }
}
function Save-Flow([string]$Session){
    $state=Get-Development $Session
    $op=Invoke-Flow agent "/api/v1/agent-sessions/$Session/development/save" POST @{idempotencyKey=[Guid]::NewGuid().ToString();expectedRevision=$state.local.revision;commitMessage='Integration source save'}
    $saved=Wait-Operation $Session $op
    Assert-Flow ($saved.status-ceq'SUCCEEDED' -and $saved.pushedSha-match'^[0-9a-f]{40,64}$') 'save_proves_push'
    return $saved
}
function Preview-Flow([string]$Session){
    $state=Get-Development $Session
    $op=Invoke-Flow agent "/api/v1/agent-sessions/$Session/development/preview" POST @{idempotencyKey=[Guid]::NewGuid().ToString();expectedRevision=$state.local.revision;commitMessage='Integration preview'}
    return Wait-Operation $Session $op
}
function Query-Flow([string]$BuildId,[hashtable]$Request){
    # 每次 POST 都重新执行，响应即本次完整的有界结果，不读取历史结果。
    $query=Invoke-Flow platform "/api/dbt/builds/$BuildId/queries" POST $Request -ExpectedStatus 200
    Assert-Flow ($query.buildId-ceq$BuildId -and $query.mode-ceq$Request.mode) 'query_fixed_build_succeeded'
    Assert-Flow (@($query.PSObject.Properties.Name|Where-Object {$_-cin@('queryId','state','nextOffset','returnedRows')}).Count-eq 0) 'query_has_no_persistent_identity'
    if($Request.mode-ceq'EXPLAIN'){
        Assert-Flow (![string]::IsNullOrWhiteSpace($query.sql)) 'synchronous_explain_has_compiled_sql'
    }else{
        Assert-Flow (@($query.columns).Count-gt 0 -and @($query.rows).Count-gt 0) 'synchronous_query_returned_physical_rows'
    }
    $identities.Add(@{buildId=$BuildId;mode=$Request.mode;resultTruncated=$query.resultTruncated})
}

try{
    $preflight=Test-MetricsContractPreflight $config
    Assert-Flow $preflight.Valid 'new_contract_ready'
    $scenario='shared_branch_save_preview'
    $sessions=@(1,2|ForEach-Object{
        (Invoke-Flow agent '/api/v1/agent-sessions' POST @{title="Contract integration $run $_";projectId=$config.agentProjectId;development=@{projectId=$config.agentProjectId;branchName=$config.branchName}}).conversationSessionId
    })
    $a=$sessions[0];$b=$sessions[1]
    Edit-ThroughMessage $a "macros/flow_a_$run.sql" "{# integration A $run #}`n"
    Edit-ThroughMessage $b "macros/flow_b_$run.sql" "{# integration B $run #}`n"
    Save-Flow $a|Out-Null;$save=Save-Flow $b
    $files=Invoke-Flow agent "/api/v1/agent-sessions/$b/development/files"
    Assert-Flow ($files.files-contains"macros/flow_a_$run.sql" -and $files.files-contains"macros/flow_b_$run.sql") 'both_sessions_changes_preserved'
    $preview=Preview-Flow $b
    Assert-Flow ($preview.status-ceq'SUCCEEDED') 'preview_operation_completed'
    $build=Invoke-Flow service "/builds/$($preview.buildIds[-1])"
    Assert-Flow ($build.commitSha-ceq$save.pushedSha -and $build.execution.environmentId-ceq$config.previewExecution.environmentId) 'preview_uses_pushed_sha'
    Assert-Flow ($build.initialDeployment.deploymentStatus-ceq'DEPLOYED') 'preview_deployment_completed'
    $scenario='fixed_catalog_and_four_modes'
    $catalog=Invoke-Flow platform "/api/dbt/builds/$($build.buildId)/catalog?limit=200"
    Assert-Flow ($catalog.buildId-ceq$build.buildId) 'catalog_fixed_build'
    $metric=@($catalog.items|Where-Object kind -eq 'METRIC')[0]
    $dataset=@($catalog.items|Where-Object {$_.capabilities-contains'PREVIEW'})[0]
    Assert-Flow ($null-ne$metric -and $null-ne$dataset) 'fixture_has_metric_and_dataset'
    # 选项发现同步返回固定构建和指标集合，不再创建任务或需要幂等键。
    $options=Invoke-Flow platform "/api/dbt/builds/$($build.buildId)/available-dimensions" POST @{metricResourceIds=@($metric.resourceId)} -ExpectedStatus 200
    Assert-Flow ($options.buildId-ceq$build.buildId -and @($options.metricResourceIds).Count-eq 1 -and $options.metricResourceIds[0]-ceq$metric.resourceId) 'options_fixed_build'
    Assert-Flow (@($options.PSObject.Properties.Name|Where-Object {$_-cin@('optionsTaskId','state','error')}).Count-eq 0) 'options_has_no_task_state'
    $dimension=@($options.dimensions|Where-Object {$_.dimensionType-ne'time'})[0]
    if(!$dimension){$dimension=@($options.dimensions)[0]}
    Assert-Flow ($null-ne$dimension) 'fixture_has_dimension'
    foreach($mode in @('QUERY','EXPLAIN','PREVIEW','DIMENSION_VALUES')){
        $query=@{mode=$mode;metricResourceIds=@($metric.resourceId);groupBy=@();filters=@();orderBy=@();limit=5}
        if($mode-ceq'PREVIEW'){$query.datasetResourceId=$dataset.resourceId;$query.metricResourceIds=@()}
        if($mode-ceq'DIMENSION_VALUES'){$query.dimensionOptionId=$dimension.optionId}
        Query-Flow $build.buildId $query
    }
    $scenario='confirmed_delivery'
    $scope=(Get-Development $b).deliveryScope
    $delivery=Invoke-Flow agent "/api/v1/agent-sessions/$b/development/deliver" POST @{idempotencyKey=[Guid]::NewGuid().ToString();expectedSourceSha=$scope.expectedSourceSha;expectedMainSha=$scope.expectedMainSha;confirmedScopeDigest=$scope.confirmedScopeDigest}
    $delivery=Wait-Operation $b $delivery
    Assert-Flow ($delivery.status-ceq'SUCCEEDED') 'delivery_operation_completed'
    $production=Invoke-Flow service "/builds/$($delivery.buildIds[-1])"
    Assert-Flow ($production.commitSha-ceq$delivery.mergeSha -and $production.execution.environmentId-ceq$config.productionExecution.environmentId) 'production_uses_merge_sha'
    Assert-Flow ($production.buildId-cne$build.buildId -and $production.initialDeployment.deploymentStatus-ceq'DEPLOYED') 'independent_production_deployed'
    # 历史构建查询仍固定预览身份，不随正式部署切换。
    Query-Flow $build.buildId @{mode='QUERY';metricResourceIds=@($metric.resourceId);groupBy=@();filters=@();orderBy=@();limit=5}
    $scenario='invalid_yaml_preserves_deployment'
    Edit-ThroughMessage $b "$ModelDirectory/invalid_$run.yml" 'invalid: ['
    Save-Flow $b|Out-Null
    $invalid=Preview-Flow $b
    Assert-Flow ($invalid.status-ceq'FAILED') 'invalid_yaml_build_failed_after_save'
    $current=(Get-Development $b).currentDeployment
    Assert-Flow ($current.activeBuildId-ceq$build.buildId) 'failed_build_keeps_old_deployment'
    Edit-ThroughMessage $b "$ModelDirectory/invalid_$run.yml" '' DELETE
    Save-Flow $b|Out-Null
    $scenario='new_deployment_keeps_historical_query'
    $secondPreview=Preview-Flow $b
    Assert-Flow ($secondPreview.status-ceq'SUCCEEDED' -and $secondPreview.buildIds[-1]-cne$build.buildId) 'second_preview_is_independent_build'
    $current=(Get-Development $b).currentDeployment
    Assert-Flow ($current.activeBuildId-ceq$secondPreview.buildIds[-1]) 'second_preview_is_current'
    Query-Flow $build.buildId @{mode='QUERY';metricResourceIds=@($metric.resourceId);groupBy=@();filters=@();orderBy=@();limit=5}
    $scenario='undeployed_branch_has_no_main_fallback'
    $newBranch="feature/unbuilt-$run"
    Invoke-Flow agent "/api/v1/agent-projects/$($config.agentProjectId)/branches" POST @{branchName=$newBranch;idempotencyKey=[Guid]::NewGuid().ToString()}|Out-Null
    Wait-Flow {Invoke-Flow agent "/api/v1/agent-projects/$($config.agentProjectId)/branches"} {param($page)@($page.items|Where-Object branchName -CEQ $newBranch).Count-eq 1} 'branch_creation'|Out-Null
    $unbuilt=Invoke-Flow platform ("/api/dbt/deployments/current?repository="+[Uri]::EscapeDataString($config.repository)+"&branchName="+[Uri]::EscapeDataString($newBranch)+"&environmentId=$($config.previewExecution.environmentId)")
    Assert-Flow ($null-eq$unbuilt.activeBuildId) 'undeployed_branch_is_empty'
    if($ComparisonConfigPath){
        $scenario='same_branch_across_repositories'
        $comparison=Get-Content -LiteralPath $ComparisonConfigPath -Raw|ConvertFrom-Json -AsHashtable
        $comparisonPreflight=Test-MetricsContractPreflight $comparison
        Assert-Flow ($comparisonPreflight.Valid -and $comparison.repository-cne$config.repository -and $comparison.branchName-ceq$config.branchName) 'comparison_repository_explicit'
        # 两个仓库同名分支、相同平台实例，第二仓库必须保持自身未部署事实。
        Assert-Flow ($comparison.metricPlatformBaseUrl-ceq$config.metricPlatformBaseUrl) 'same_platform_for_isolation'
        $isolated=Invoke-Flow platform ("/api/dbt/deployments/current?repository="+[Uri]::EscapeDataString($comparison.repository)+"&branchName="+[Uri]::EscapeDataString($comparison.branchName)+"&environmentId=$($comparison.previewExecution.environmentId)")
        Assert-Flow ($null-eq$isolated.activeBuildId -and $isolated.repository-ceq$comparison.repository) 'same_branch_repository_isolated'
    }
    $result=@{scenario='main_flow';status='PASS';evidence=@{protocolVersion='execution-snapshot';assertions=@($checks);identities=@($identities)}}
}catch{
    # 故障只输出步骤与稳定断言，不输出响应/正文/凭据。
    $code=$_.Exception.Message
    if($code-notmatch'^(assertion_failed|[a-z]+_(transport_failed|http_[0-9]{3})|response_too_large|timeout_[a-z_]+)$'){$code='unexpected_response'}
    $result=@{scenario=$scenario;status='FAIL';evidence=@{errorCode=$code;preflightErrors=$preflight.Errors;assertions=@($checks);identities=@($identities)}}
}
$json=$result|ConvertTo-Json -Depth 15
if($OutputDirectory){[IO.Directory]::CreateDirectory($OutputDirectory)|Out-Null;$json|Set-Content -Encoding utf8 (Join-Path $OutputDirectory 'flow-result.json')}
$json
if($result.status-ne'PASS'){exit 1}
