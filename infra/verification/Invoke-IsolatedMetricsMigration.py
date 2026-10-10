"""在独立备份副本验证三产品迁移；只调用正式管理入口、Flyway 和公开 HTTP。"""

import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(tempfile.mkdtemp(prefix="metrics-migration-"))
SECRET = uuid.uuid4().hex
TOKEN = uuid.uuid4().hex
CONTAINER = "migration-" + uuid.uuid4().hex[:12]
REDIS = CONTAINER + "-redis"
ENV = os.environ.copy() | {"POSTGRES_PASSWORD": SECRET, "MIGRATION_DB_PASSWORD": SECRET}
SERVICE = ROOT / "dbt-metricflow-service"
# 引擎就绪检查和子进程使用本仓库已安装的 dbt/MetricFlow。
ENV["PATH"] = str(SERVICE / ".venv/Scripts") + os.pathsep + ENV["PATH"]
ADMIN = SERVICE / ".venv/Scripts/dbt-service-admin.exe"
REPOSITORY = "https://git.example.test/migration/metrics.git"
SHA = "a" * 40
TOOLCHAIN = "isolated-migration-fixture"
IDS = {
    key: str(uuid.uuid4())
    for key in (
        "run",
        "release",
        "output",
        "old_query",
        "platform_release",
        "platform_query",
        "missing_release",
        "missing_branch",
        "branch",
        "agent_project",
        "session",
        "workspace",
        "change",
        "conflict_project",
        "conflict_session",
        "conflict_workspace",
        "conflict_change",
    )
}
PROCESSES = []
LOGS = []
EVIDENCE = {}


def command(args, *, env=ENV, data=None, name="command", text=True):
    # 凭据只通过环境变量传递，失败详情仅保存脱敏副本。
    result = subprocess.run(
        [str(value) for value in args],
        cwd=ROOT,
        env=env,
        input=data,
        capture_output=True,
        check=False,
        timeout=180,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        detail = (result.stdout + result.stderr).decode("utf-8", "replace")
        (WORK / (name + ".log")).write_text(
            detail.replace(SECRET, "[REDACTED]").replace(TOKEN, "[REDACTED]"),
            encoding="utf-8",
        )
        raise RuntimeError(name + " failed; see isolated log")
    return result.stdout.decode("utf-8", "replace").strip() if text else result.stdout


def record(name, condition, **evidence):
    if not condition:
        raise AssertionError(name)
    EVIDENCE[name] = evidence or True
    print(name, "PASS", flush=True)


def connect(database):
    return psycopg2.connect(
        host="127.0.0.1", port=PGPORT, user="postgres", password=SECRET, dbname=database
    )


def sql(database, statement, values=None):
    with connect(database) as connection, connection.cursor() as cursor:
        cursor.execute(statement, values)
        return cursor.fetchall() if cursor.description else []


def scalar(database, statement, values=None):
    return sql(database, statement, values)[0][0]


def digest(value):
    return hashlib.sha256(value).hexdigest()


def write_json(name, value):
    path = WORK / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start(args, env, name):
    log = (WORK / (name + ".log")).open("w", encoding="utf-8")
    LOGS.append(log)
    process = subprocess.Popen(
        [str(value) for value in args],
        cwd=WORK,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    PROCESSES.append(process)
    return process


def api(base, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        base + path,
        headers=headers,
        data=None if body is None else json.dumps(body).encode(),
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def wait_http(base, path, seconds=120):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            return api(base, path)
        except (OSError, ValueError):
            time.sleep(0.3)
    raise RuntimeError("service readiness timeout")


def flyway(database, product, target=None):
    # 产品 SQL 完整交给现有 Flyway 依赖处理，脚本不重实现迁移版本管理。
    location = (
        ROOT
        / product
        / "backend"
        / ("agent-persistence" if product == "data-agent-v2" else "metric-persistence")
        / "src/main/resources/db/migration"
    )
    command(
        [
            "java",
            "--class-path",
            str(WORK / "flyway-libs/*"),
            WORK / "MigrationFlyway.java",
            f"jdbc:postgresql://127.0.0.1:{PGPORT}/{database}",
            "filesystem:" + location.as_posix(),
            target or "latest",
        ],
        name="flyway-" + database,
    )


def admin(*args):
    return json.loads(command([ADMIN, *args], env=SERVICE_ENV, name="service-admin"))


def sealed_snapshot(database):
    rows = sql(
        database,
        "select set_id::text,relative_path,content,raw_sha256,codec from runtime_artifact_file order by set_id,relative_path",
    )
    return [(row[0], row[1], digest(bytes(row[2])), row[3], row[4]) for row in rows]


def references(database):
    return sql(
        database,
        "select release_id::text,native_id,creator_run_id::text,binding_json from runtime_release_relation order by release_id,native_id",
    )


try:
    # 专用容器中只写合成历史数据；旧库不启动任何受理进程。
    command(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            CONTAINER,
            "-e",
            "POSTGRES_PASSWORD",
            "-p",
            "127.0.0.1::5432",
            "postgres:17-alpine",
        ]
    )
    PGPORT = int(command(["docker", "port", CONTAINER, "5432/tcp"]).rsplit(":", 1)[1])
    for attempt in range(80):
        try:
            sql("postgres", "select 1")
            break
        except psycopg2.OperationalError:
            time.sleep(0.3)
    for database in ("engine_old", "agent_old", "platform_old", "warehouse_old"):
        command(["docker", "exec", CONTAINER, "createdb", "-U", "postgres", database])

    # 固定已打包产物快照；无需运行 Agent Maven，也不与并行构建争用输出。
    for product, module, filename in (
        ("data-agent-v2", "agent-server", "agent.jar"),
        ("metric-platform", "metric-app", "platform.jar"),
    ):
        shutil.copyfile(
            ROOT
            / product
            / "backend"
            / module
            / "target"
            / (module + "-0.1.0-SNAPSHOT.jar"),
            WORK / filename,
        )
    libs = WORK / "flyway-libs"
    libs.mkdir()
    with zipfile.ZipFile(WORK / "platform.jar") as archive:
        for name in archive.namelist():
            if name.startswith("BOOT-INF/lib/") and name.endswith(".jar"):
                (libs / Path(name).name).write_bytes(archive.read(name))
    (WORK / "MigrationFlyway.java").write_text(
        """import org.flywaydb.core.Flyway;
class MigrationFlyway {
  public static void main(String[] args) {
    var config = Flyway.configure().dataSource(args[0], "postgres", System.getenv("MIGRATION_DB_PASSWORD")).locations(args[1]);
    if (!args[2].equals("latest")) config.target(args[2]);
    config.load().migrate();
  }
}
""",
        encoding="utf-8",
    )
    flyway("agent_old", "data-agent-v2", "14")
    flyway("platform_old", "metric-platform", "14")
    # 服务维护的五个归档 SQL 即旧正式 schema，不能导入服务 Python 实现来伪造升级。
    for migration in sorted(
        (SERVICE / "src/dbt_metricflow_service/storage/migrations").glob("*.sql")
    ):
        sql("engine_old", migration.read_text(encoding="utf-8"))

    catalog = {
        "schemaVersion": 1,
        "projectId": "legacy-metrics",
        "releaseId": IDS["release"],
        "relations": [],
        "relationBindings": [],
        "resources": [
            {
                "resourceId": "metric.revenue",
                "nativeId": "metric.legacy.revenue",
                "name": "revenue",
                "displayName": "历史收入",
                "kind": "METRIC",
                "capabilities": ["QUERY"],
                "nativeDetails": {},
                "attributes": {
                    "metricType": "simple",
                    "definitionSummary": "fixture",
                    "inputMetricIds": [],
                    "datasetIds": [],
                    "timeConfig": {},
                },
            }
        ],
    }
    content = json.dumps(catalog, ensure_ascii=False).encode()
    config = {
        "remote": REPOSITORY,
        "profileBindingId": "fixture",
        "businessTimezone": "Asia/Shanghai",
    }
    sql(
        "engine_old",
        "insert into runtime_project(project_id,binding_config) values('legacy-metrics',%s),('missing-source','{}')",
        (Json(config),),
    )
    sql(
        "engine_old",
        "insert into runtime_branch(branch_id,project_id,git_ref,mode,status,config_version,binding_config) values(%s,'legacy-metrics','refs/heads/main','PRODUCTION','ACTIVE','1',%s),(%s,'missing-source','refs/heads/main','PRODUCTION','ACTIVE','1','{}')",
        (IDS["branch"], Json(config), IDS["missing_branch"]),
    )
    sql(
        "engine_old",
        "insert into runtime_job(job_id,kind,project_id,branch_id,request_fingerprint,config_version,toolchain_version,profile_binding_id,status,phase,run_lifecycle,deadline_at,finished_at) values(%s,'BUILD_RUN','legacy-metrics',%s,'fixture','1',%s,'fixture','SUCCEEDED','COMPLETE','ACTIVE',now(),now())",
        (IDS["run"], IDS["branch"], TOOLCHAIN),
    )
    sql(
        "engine_old",
        "insert into runtime_artifact_set(set_id,project_id,kind,catalog_json) values(%s,'legacy-metrics','EXECUTION',%s)",
        (IDS["output"], Json(catalog)),
    )
    for name, payload in (
        ("target/published_catalog.json", content),
        ("target/manifest.json", b'{"metadata":{"sealed":"unchanged"}}'),
    ):
        sql(
            "engine_old",
            "insert into runtime_artifact_file(set_id,relative_path,content,codec,raw_sha256,raw_size,stored_size) values(%s,%s,%s,'raw',%s,%s,%s)",
            (
                IDS["output"],
                name,
                psycopg2.Binary(payload),
                digest(payload),
                len(payload),
                len(payload),
            ),
        )
    sql(
        "engine_old",
        "update runtime_artifact_set set state='SEALED',sealed_at=now(),created_at=now()-interval '2 days' where set_id=%s",
        (IDS["output"],),
    )
    sql(
        "engine_old",
        "update runtime_job set output_set_id=%s where job_id=%s",
        (IDS["output"], IDS["run"]),
    )
    sql(
        "engine_old",
        "insert into runtime_release(release_id,project_id,branch_id,sequence,idempotency_key,request_json,run_id,artifact_set_id,state,catalog_digest,published_at) values(%s,'legacy-metrics',%s,1,'old-release',%s,%s,%s,'PUBLISHED',%s,now())",
        (
            IDS["release"],
            IDS["branch"],
            Json({"commitSha": SHA}),
            IDS["run"],
            IDS["output"],
            digest(content),
        ),
    )
    sql(
        "engine_old",
        "insert into runtime_release(release_id,project_id,branch_id,sequence,idempotency_key,request_json,state) values(%s,'missing-source',%s,1,'missing','{}','FAILED')",
        (IDS["missing_release"], IDS["missing_branch"]),
    )
    sql(
        "engine_old",
        "update runtime_branch set active_release_id=%s,latest_release_id=%s where branch_id=%s",
        (IDS["release"], IDS["release"], IDS["branch"]),
    )
    sql(
        "engine_old",
        "insert into runtime_release_relation(release_id,native_id,creator_run_id,binding_json) values(%s,'model.legacy.orders',%s,%s)",
        (
            IDS["release"],
            IDS["run"],
            Json(
                {
                    "database": "warehouse",
                    "schema": "sealed_build",
                    "identifier": "orders",
                }
            ),
        ),
    )
    sql(
        "engine_old",
        "insert into runtime_job(job_id,kind,project_id,branch_id,parent_run_id,request_fingerprint,request_json,config_version,toolchain_version,status,deadline_at,finished_at) values(%s,'METRIC_QUERY','legacy-metrics',%s,%s,'historical-query','{}','1',%s,'SUCCEEDED',now(),now())",
        (IDS["old_query"], IDS["branch"], IDS["run"], TOOLCHAIN),
    )
    sql(
        "warehouse_old",
        "create schema sealed_build; create table sealed_build.orders(id integer primary key, amount numeric(30,9)); insert into sealed_build.orders values(1,1234567890.123456789),(2,2.000000001)",
    )
    sql(
        "platform_old",
        "insert into semantic_project(project_id,repository_id,project_subdir,profile_binding_id) values('legacy-metrics','legacy-repository','.','fixture')",
    )
    sql(
        "platform_old",
        "insert into semantic_release(release_id,project_id,release_sequence,target_commit_sha,build_source_sha,project_digest,config_version,idempotency_key,state,runtime_run_id) values(%s,'legacy-metrics',1,%s,%s,'sealed-digest','1',%s,'PUBLISHED',%s)",
        (IDS["platform_release"], SHA, SHA, str(uuid.uuid4()), IDS["run"]),
    )
    sql(
        "platform_old",
        "insert into semantic_query(query_id,project_id,release_id,idempotency_key,runtime_query_id,mode,status,result_locator) values(%s,'legacy-metrics',%s,%s,%s,'QUERY','COMPLETED','sealed://historical-query')",
        (
            IDS["platform_query"],
            IDS["platform_release"],
            str(uuid.uuid4()),
            IDS["old_query"],
        ),
    )
    sql(
        "agent_old",
        "insert into tenant(tenant_id,name) values('tenant_local','Local') on conflict do nothing",
    )
    sql(
        "agent_old",
        "insert into conversation_project(tenant_id,project_id,name) values('tenant_local',%s,'迁移演练')",
        (IDS["agent_project"],),
    )
    sql(
        "agent_old",
        "insert into conversation_session(tenant_id,conversation_session_id,title,project_id) values('tenant_local',%s,'迁移会话',%s)",
        (IDS["session"], IDS["agent_project"]),
    )
    sql(
        "agent_old",
        "insert into git_workspace(workspace_id,conversation_session_id,repository_id,status,git_ref,storage_key) values(%s,%s,'legacy-repository','READY','refs/heads/main','unpublished-workspace')",
        (IDS["workspace"], IDS["session"]),
    )
    sql(
        "agent_old",
        "insert into git_session_workspace(conversation_session_id,workspace_id) values(%s,%s)",
        (IDS["session"], IDS["workspace"]),
    )
    sql(
        "agent_old",
        "insert into git_change(change_id,workspace_id,conversation_session_id,repository_id,status,commit_id) values(%s,%s,%s,'legacy-repository','PUSHED',%s)",
        (IDS["change"], IDS["workspace"], IDS["session"], SHA),
    )
    unpublished = WORK / "agent-local/unpublished-workspace/model.sql"
    # 独立冲突项目进入真实备份，验证真实迁移禁用后不影响正常项目。
    sql(
        "agent_old",
        "insert into conversation_project(tenant_id,project_id,name) values('tenant_local',%s,'来源冲突演练')",
        (IDS["conflict_project"],),
    )
    sql(
        "agent_old",
        "insert into conversation_session(tenant_id,conversation_session_id,title,project_id) values('tenant_local',%s,'冲突会话',%s)",
        (IDS["conflict_session"], IDS["conflict_project"]),
    )
    sql(
        "agent_old",
        "insert into git_workspace(workspace_id,conversation_session_id,repository_id,status,git_ref,storage_key) values(%s,%s,'legacy-repository','READY','refs/heads/main','conflict-workspace')",
        (IDS["conflict_workspace"], IDS["conflict_session"]),
    )
    sql(
        "agent_old",
        "insert into git_session_workspace(conversation_session_id,workspace_id) values(%s,%s)",
        (IDS["conflict_session"], IDS["conflict_workspace"]),
    )
    sql(
        "agent_old",
        "insert into git_change(change_id,workspace_id,conversation_session_id,repository_id,status,commit_id) values(%s,%s,%s,'legacy-repository','PUSHED',%s)",
        (
            IDS["conflict_change"],
            IDS["conflict_workspace"],
            IDS["conflict_session"],
            SHA,
        ),
    )
    unpublished.parent.mkdir(parents=True)
    unpublished.write_bytes(b"-- not pushed\nselect 19 as local_only\n")
    unpublished_hash = digest(unpublished.read_bytes())
    original_sealed = sealed_snapshot("engine_old")
    original_refs = references("engine_old")
    physical_rows = sql(
        "warehouse_old", "select id,amount::text from sealed_build.orders order by id"
    )
    record(
        "old_writers_stopped_and_tasks_drained",
        scalar(
            "engine_old",
            "select count(*) from runtime_job where status in ('QUEUED','RUNNING')",
        )
        == 0,
    )

    # 备份与恢复使用 PostgreSQL 正式工具；后续所有迁移只作用于恢复副本。
    for product in ("engine", "agent", "platform", "warehouse"):
        backup = command(
            [
                "docker",
                "exec",
                CONTAINER,
                "pg_dump",
                "-Fc",
                "-U",
                "postgres",
                product + "_old",
            ],
            text=False,
        )
        (WORK / (product + ".dump")).write_bytes(backup)
        command(["docker", "exec", CONTAINER, "createdb", "-U", "postgres", product])
        command(
            [
                "docker",
                "exec",
                "-i",
                CONTAINER,
                "pg_restore",
                "-U",
                "postgres",
                "-d",
                product,
            ],
            data=backup,
        )
    shutil.copytree(WORK / "agent-local", WORK / "agent-local-backup")
    record(
        "backup_copy_restored",
        sealed_snapshot("engine") == original_sealed
        and sql(
            "warehouse", "select id,amount::text from sealed_build.orders order by id"
        )
        == physical_rows,
    )
    config_file = WORK / "service.yaml"
    config_file.write_text("{}\n", encoding="utf-8")
    profiles = WORK / "profiles"
    profiles.mkdir()
    # 即使新查询进入 worker，也只能读取隔离仓库，不能加载用户默认 dbt profile。
    (profiles / "profiles.yml").write_text(
        json.dumps(
            {
                "fixture": {
                    "target": "postgres",
                    "outputs": {
                        "postgres": {
                            "type": "postgres",
                            "host": "127.0.0.1",
                            "port": PGPORT,
                            "user": "postgres",
                            "password": "{{ env_var('MIGRATION_DB_PASSWORD') }}",
                            "dbname": "warehouse",
                            "schema": "sealed_build",
                            "threads": 1,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    SERVICE_ENV = ENV | {
        "SERVICE_CONFIG_FILE": str(config_file),
        "DBT_PROFILES_DIR": str(profiles),
        "SERVICE_DATABASE_URL": f"postgresql://postgres:{SECRET}@127.0.0.1:{PGPORT}/engine",
        "SERVICE_TEMP_ROOT": str(WORK / "runtime"),
        "SERVICE_TOKEN": TOKEN,
        "SERVICE_TOOLCHAIN_VERSION": TOOLCHAIN,
        "SERVICE_CONFIG_VERSION": "1",
    }
    admin("migrate")
    flyway("platform", "metric-platform")
    flyway("agent", "data-agent-v2")
    conflict = write_json(
        "conflicting-bindings.json",
        {"legacy-metrics": "https://git.example.test/wrong.git"},
    )
    bindings = write_json("history-bindings.json", {"legacy-metrics": REPOSITORY})
    record(
        "service_source_conflict_blocks_writes",
        bool(admin("migrate-history", "--bindings", conflict)["conflicts"])
        and scalar("engine", "select count(*) from engine_build") == 0,
    )
    dry = admin("migrate-history", "--bindings", bindings, "--dry-run")
    record(
        "service_dry_run_no_mutation",
        scalar("engine", "select count(*) from engine_build") == 0
        and IDS["missing_release"] in dry["sourceIncomplete"],
    )
    first = admin("migrate-history", "--bindings", bindings)
    report = write_json("service-history-report.json", first)
    build_id = first["mapping"][IDS["release"]]
    before_count = scalar("engine", "select count(*) from engine_change")
    repeated = admin("migrate-history", "--bindings", bindings)
    record(
        "service_repeat_stable",
        first == repeated
        and scalar("engine", "select count(*) from engine_change") == before_count,
        buildId=build_id,
    )
    incremental_release = str(uuid.uuid4())
    sql(
        "engine",
        "insert into runtime_release(release_id,project_id,branch_id,sequence,idempotency_key,request_json,state) values(%s,'missing-source',%s,2,'incremental','{}','FAILED')",
        (incremental_release, IDS["missing_branch"]),
    )
    incremental = admin("migrate-history", "--bindings", bindings)
    record(
        "incremental_migration_keeps_prior_identities",
        all(incremental["mapping"][old] == new for old, new in first["mapping"].items())
        and incremental_release in incremental["mapping"]
        and incremental == admin("migrate-history", "--bindings", bindings),
    )
    alias = write_json(
        "legacy-platform-identities.json",
        {
            "projectId": "legacy-metrics",
            "legacyReleaseId": IDS["platform_release"],
            "runId": IDS["run"],
            "queries": [
                {"legacyQueryId": IDS["platform_query"], "queryId": IDS["old_query"]}
            ],
        },
    )
    admin("import-publication", "--file", alias, "--dry-run")
    admin("import-publication", "--file", alias)
    admin("import-publication", "--file", alias)
    record(
        "verified_platform_identity_link",
        scalar(
            "engine",
            "select target_id::text from runtime_legacy_identity where kind='RELEASE' and legacy_id=%s",
            (IDS["platform_release"],),
        )
        == IDS["release"],
    )
    evidence = "service-history-report.json#sha256=" + digest(report.read_bytes())
    # 平台函数没有独立dry-run参数；在真实事务执行后回滚，核对关联未写入。
    with connect("platform") as connection, connection.cursor() as cursor:
        cursor.execute(
            "select import_legacy_build_mapping(%s,%s,%s,%s)",
            (IDS["platform_release"], build_id, REPOSITORY, evidence),
        )
        connection.rollback()
    record(
        "platform_mapping_dry_run_no_mutation",
        scalar("platform", "select count(*) from legacy_build_mapping") == 0
        and scalar(
            "platform",
            "select build_id from semantic_query where query_id=%s",
            (IDS["platform_query"],),
        )
        is None,
    )
    for _ in range(2):
        scalar(
            "platform",
            "select import_legacy_build_mapping(%s,%s,%s,%s)",
            (IDS["platform_release"], build_id, REPOSITORY, evidence),
        )
    query_identity = sql(
        "platform",
        "select release_id::text,runtime_query_id::text,build_id::text,result_locator from semantic_query where query_id=%s",
        (IDS["platform_query"],),
    )[0]
    record(
        "platform_history_attribution_preserved",
        query_identity
        == (
            IDS["platform_release"],
            IDS["old_query"],
            build_id,
            "sealed://historical-query",
        )
        and scalar("platform", "select count(*) from legacy_build_mapping") == 1,
    )

    # Agent 迁移使用正式一次性 runner，来源配置明确且本地未推送正文不参与迁移。
    development_config = {
        "repository": REPOSITORY,
        "previewBinding": "fixture",
        "previewConfigVersion": "1",
        "productionBinding": "fixture",
        "productionConfigVersion": "1",
        "version": 1,
    }
    sql(
        "agent",
        "insert into development_project(project_id,repository,config_json,version,enabled) values(%s,%s,%s,1,true)",
        (IDS["agent_project"], REPOSITORY, json.dumps(development_config)),
    )
    sql(
        "agent",
        "insert into development_project(project_id,repository,config_json,version,enabled) values(%s,%s,%s,1,true)",
        (IDS["conflict_project"], REPOSITORY, json.dumps(development_config)),
    )
    agent_request = write_json(
        "agent-mapping.json",
        {
            "projectId": IDS["agent_project"],
            "repositoryMappings": {"legacy-repository": REPOSITORY},
        },
    )
    AGENT_ENV = ENV | {
        "SPRING_DATASOURCE_URL": f"jdbc:postgresql://127.0.0.1:{PGPORT}/agent",
        "SPRING_DATASOURCE_USERNAME": "postgres",
        "SPRING_DATASOURCE_PASSWORD": SECRET,
        "DATA_AGENT_GIT_ENABLED": "false",
        "DATA_AGENT_DBT_ENABLED": "false",
        "DATA_AGENT_CONTEXT_STRATEGY": "raw",
        "DATA_AGENT_MODEL_PROVIDER": "ollama",
        "SPRING_AI_OLLAMA_INIT_PULL_MODEL_STRATEGY": "never",
        "DATA_AGENT_GIT_WORKSPACE_ROOT": str(WORK / "agent-local"),
    }

    def agent_migrate(dry_run, request_file=agent_request):
        output = command(
            [
                "java",
                "-jar",
                WORK / "agent.jar",
                "--spring.main.web-application-type=none",
                "--data-agent.development.migration.enabled=true",
                "--data-agent.development.migration.input=" + str(request_file),
                "--data-agent.development.migration.dry-run=" + str(dry_run).lower(),
            ],
            env=AGENT_ENV,
            name="agent-migration",
        )
        return next(
            json.loads(line)["developmentMigration"]
            for line in output.splitlines()
            if line.startswith('{"developmentMigration"')
        )

    agent_conflict_file = write_json(
        "agent-conflicting-mapping.json",
        {
            "projectId": IDS["conflict_project"],
            "repositoryMappings": {
                "legacy-repository": "https://git.example.test/wrong.git"
            },
        },
    )
    agent_conflict = agent_migrate(False, agent_conflict_file)
    record(
        "agent_source_conflict_disables_only_conflicting_project",
        not agent_conflict["dryRun"]
        and agent_conflict["items"]
        == [
            {
                "workspaceId": IDS["conflict_workspace"],
                "sessionId": IDS["conflict_session"],
                "status": "UNRESOLVED_REPOSITORY",
            }
        ]
        and sql(
            "agent",
            "select enabled,diagnostic from development_project where project_id=%s",
            (IDS["conflict_project"],),
        )
        == [(False, "UNRESOLVED_REPOSITORY")]
        and sql(
            "agent",
            "select enabled,diagnostic from development_project where project_id=%s",
            (IDS["agent_project"],),
        )
        == [(True, None)]
        and scalar("agent", "select count(*) from development_session") == 0,
    )
    agent_dry = agent_migrate(True)
    record(
        "agent_dry_run_no_mutation",
        agent_dry["dryRun"]
        and scalar("agent", "select count(*) from development_session") == 0,
    )
    agent_migrate(False)
    stable_session = sql(
        "agent",
        "select id,storage_key,pushed_sha,baseline_sha from development_session where session_id=%s",
        (IDS["session"],),
    )
    agent_migrate(False)
    record(
        "agent_repeat_stable_and_local_files_preserved",
        stable_session
        == sql(
            "agent",
            "select id,storage_key,pushed_sha,baseline_sha from development_session where session_id=%s",
            (IDS["session"],),
        )
        and stable_session[0][2:] == (SHA, SHA)
        and digest(unpublished.read_bytes()) == unpublished_hash,
    )
    record(
        "sealed_bytes_and_physical_references_preserved",
        sealed_snapshot("engine") == original_sealed
        and references("engine") == original_refs
        and sql(
            "warehouse", "select id,amount::text from sealed_build.orders order by id"
        )
        == physical_rows,
        changedArtifactHashCount=0,
        physicalReferenceCount=len(original_refs),
    )
    record(
        "referenced_artifacts_survive_gc",
        admin("gc", "--older-than-hours", "0")["deleted"] == 0
        and sealed_snapshot("engine") == original_sealed,
    )

    # 引擎先就绪，再启动 Agent 和平台；HTTP只验证迁移身份/封存目录与新查询归因。
    service_port, agent_port, platform_port = free_port(), free_port(), free_port()
    service_url, agent_url, platform_url = [
        "http://127.0.0.1:" + str(port)
        for port in (service_port, agent_port, platform_port)
    ]
    start(
        [SERVICE / ".venv/Scripts/dbt-metricflow-service.exe"],
        SERVICE_ENV | {"SERVICE_HOST": "127.0.0.1", "SERVICE_PORT": str(service_port)},
        "service",
    )
    wait_http(service_url, "/health/ready")
    start(
        ["java", "-jar", WORK / "agent.jar"],
        AGENT_ENV | {"SERVER_PORT": str(agent_port)},
        "agent",
    )
    wait_http(agent_url, "/actuator/health")
    agent_projects = api(agent_url, "/api/v1/agent-projects")
    record(
        "agent_project_readback_matches_migrated_source",
        any(
            item["projectId"] == IDS["agent_project"]
            and item["repository"] == REPOSITORY
            and item["developmentConfigured"]
            for item in agent_projects["items"]
        ),
    )
    command(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            REDIS,
            "-p",
            "127.0.0.1::6379",
            "redis:7.4-alpine",
        ]
    )
    redis_port = int(command(["docker", "port", REDIS, "6379/tcp"]).rsplit(":", 1)[1])
    platform_env = ENV | {
        "SERVER_PORT": str(platform_port),
        "SPRING_DATASOURCE_URL": f"jdbc:postgresql://127.0.0.1:{PGPORT}/platform",
        "SPRING_DATASOURCE_USERNAME": "postgres",
        "SPRING_DATASOURCE_PASSWORD": SECRET,
        "DBT_SERVICE_BASE_URI": service_url,
        "DBT_SERVICE_TOKEN": TOKEN,
        "AGENT_BASE_URI": agent_url,
    }
    platform_env["SPRING_APPLICATION_JSON"] = json.dumps(
        {
            "spring": {
                "data": {
                    "redis": {"host": "127.0.0.1", "port": redis_port, "password": ""}
                }
            },
            "metric-platform": {
                "identity-auth": {"bootstrap": {"password": SECRET}},
                "build-history": {"poll-ms": 300},
            },
        }
    )
    start(["java", "-jar", WORK / "platform.jar"], platform_env, "platform")
    wait_http(platform_url, "/actuator/health")
    login = api(
        platform_url, "/api/v1/auth/token", {"username": "admin", "password": SECRET}
    )
    access = login["accessToken"]
    build = api(service_url, "/v3/builds/" + build_id, token=TOKEN)
    catalog_page = api(
        platform_url, "/api/v3/dbt/builds/" + build_id + "/catalog", token=access
    )
    record(
        "three_products_start_and_catalog_is_readable",
        build["buildId"] == build_id
        and catalog_page["buildId"] == build_id
        and len(catalog_page["items"]) == 1,
    )
    deadline = time.time() + 45
    while time.time() < deadline:
        history = api(platform_url, "/api/v3/dbt/builds", token=access)
        if any(row["buildId"] == build_id for row in history["items"]):
            break
        time.sleep(0.3)
    record(
        "platform_replays_migrated_history",
        any(row["buildId"] == build_id for row in history["items"]),
    )
    accepted = api(
        platform_url,
        "/api/v3/dbt/builds/" + build_id + "/queries",
        {
            "idempotencyKey": "migration-attribution",
            "mode": "EXPLAIN",
            "metricResourceIds": ["metric.revenue"],
        },
        access,
    )
    audit = sql(
        "platform",
        "select build_id::text,user_id::text from build_query_audit where query_id=%s",
        (accepted["queryId"],),
    )[0]
    identity = api(platform_url, "/api/v1/auth/me", token=access)
    record(
        "new_query_attributed_to_build_and_authenticated_user",
        audit == (build_id, identity["identityId"]),
        queryId=accepted["queryId"],
        buildId=build_id,
    )
    record(
        "old_backup_is_untouched",
        sealed_snapshot("engine_old") == original_sealed
        and scalar("engine_old", "select version from runtime_schema_version") == 5
        and scalar(
            "platform_old",
            "select runtime_query_id::text from semantic_query where query_id=%s",
            (IDS["platform_query"],),
        )
        == IDS["old_query"]
        and scalar(
            "agent_old",
            "select commit_id from git_change where change_id=%s",
            (IDS["change"],),
        )
        == SHA,
    )
    EVIDENCE["limitations"] = [
        "使用合成旧数据及真实pg_dump备份副本，不是生产窗口",
        "新查询仅验证真实HTTP受理和归因；真实MetricFlow执行结果由I2验收",
    ]
    EVIDENCE["versions"] = {
        "service": command(["git", "-C", SERVICE, "rev-parse", "HEAD"]),
        "agentJarSha256": digest((WORK / "agent.jar").read_bytes()),
        "platformJarSha256": digest((WORK / "platform.jar").read_bytes()),
    }
    write_json(
        "evidence.json",
        {
            "scenario": "isolated_backup_migration",
            "status": "PASSED",
            "evidence": EVIDENCE,
        },
    )
    print("migration_rehearsal PASS", str(WORK), flush=True)
except Exception as error:  # noqa: BLE001 — 顶层边界记录脱敏错误，禁止凭据进入控制台。
    EVIDENCE["failure"] = (
        (type(error).__name__ + ": " + str(error))
        .replace(SECRET, "[REDACTED]")
        .replace(TOKEN, "[REDACTED]")
    )
    write_json(
        "evidence.json",
        {
            "scenario": "isolated_backup_migration",
            "status": "FAILED",
            "evidence": EVIDENCE,
        },
    )
    print("migration_rehearsal FAILED", EVIDENCE["failure"], flush=True)
    raise SystemExit(1) from None
finally:
    for process in reversed(PROCESSES):
        # 只处理仍在运行的自持进程；Windows必须同时回收dbt/MetricFlow子进程。
        if process.poll() is not None:
            continue
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)
    for log in LOGS:
        log.close()
    # 仅删除本脚本创建且名字固定到随机ID的两个容器，不触碰共享数据卷。
    for container in (REDIS, CONTAINER):
        subprocess.run(
            ["docker", "rm", "-f", container],
            capture_output=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    print("migration_evidence_directory", str(WORK), flush=True)
