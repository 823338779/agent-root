# 隔离集成环境，仅替代模型决策；所有文件工具、Git、数据库、HTTP及dbt/MetricFlow真实执行。
import hashlib
import http.client
import json
import os
import pathlib
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
import uuid
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
TASK = pathlib.Path(tempfile.mkdtemp(prefix="dbt-contract-"))
WORK = TASK / ("live-" + uuid.uuid4().hex[:10])
WORK.mkdir()
ENV = os.environ.copy()
ENV["PATH"] = (
    str(ROOT / "dbt-metricflow-service/.venv/Scripts") + os.pathsep + ENV["PATH"]
)
PY = str(ROOT / "dbt-metricflow-service/.venv/Scripts/python.exe")
procs = []
logs = ExitStack()
container = "contract-" + uuid.uuid4().hex[:12]
rediscontainer = container + "-redis"
SECRET = uuid.uuid4().hex
TOKEN = uuid.uuid4().hex
ENV["POSTGRES_PASSWORD"] = SECRET
exitcode = 0


def run(args, cwd=ROOT, env=ENV):
    p = subprocess.run(
        [str(a) for a in args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if p.returncode:
        (WORK / "command-failed.log").write_text(
            (p.stdout + "\n" + p.stderr)
            .replace(SECRET, "[REDACTED]")
            .replace(TOKEN, "[REDACTED]"),
            encoding="utf-8",
        )
        raise RuntimeError("command_failed:" + str(args[0]))
    return p.stdout.strip()


def start(args, name, env=ENV, cwd=ROOT):
    # 进程日志由全局ExitStack在finally关闭，生命周期覆盖子进程。
    log = logs.enter_context(open(WORK / (name + ".log"), "w", encoding="utf-8"))  # noqa: SIM115
    p = subprocess.Popen(
        [str(a) for a in args],
        env=env,
        cwd=cwd,
        stdout=log,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    procs.append(p)
    return p


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def api(base, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        base + path, data=None if body is None else json.dumps(body).encode(), headers=h
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def wait(base, path, seconds=120):
    end = time.time() + seconds
    while time.time() < end:
        try:
            return api(base, path)
        except (OSError, ValueError):
            time.sleep(0.5)
    raise RuntimeError("health_timeout:" + path)


def find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            result = find_key(v, key)
            if result is not None:
                return result
    if isinstance(obj, list):
        for v in obj:
            result = find_key(v, key)
            if result is not None:
                return result
    return None


def component_versions():
    # 记录实际工作区与已启动制品指纹，使未提交状态下的联调证据也可核对。
    components = {}
    artifacts = {
        "agent": (
            "data-agent-v2",
            "backend/agent-server/target/agent-server-0.1.0-SNAPSHOT.jar",
        ),
        "platform": (
            "metric-platform",
            "backend/metric-app/target/metric-app-0.1.0-SNAPSHOT.jar",
        ),
        "engine": ("dbt-metricflow-service", None),
    }
    for name, (directory, artifact) in artifacts.items():
        repository = ROOT / directory
        info = {"gitHead": run(["git", "rev-parse", "HEAD"], cwd=repository)}
        if artifact:
            info["artifactSha256"] = hashlib.sha256(
                (repository / artifact).read_bytes()
            ).hexdigest()
        components[name] = info
    return components


class Model(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        messages = data.get("messages", [])
        last = max(i for i, m in enumerate(messages) if m["role"] == "user")
        tail = messages[last:]
        prompt = tail[0]["content"]
        calls = [c for m in tail for c in m.get("tool_calls", [])]
        names = [c["function"]["name"] for c in calls]
        results = []
        for m in tail:
            if m["role"] == "tool":
                try:
                    results.append(json.loads(m["content"]))
                except json.JSONDecodeError:
                    continue
        typ = re.search(r"操作类型 (CREATE|UPDATE|DELETE)", prompt).group(1)
        path = re.search(r"工程相对路径 ([^。]+)", prompt).group(1)
        args = {}
        tool = None
        if "skill_read" not in names:
            tool = "skill_read"
            args = {"logical_id": "git-repository-maintenance"}
        elif "git_files_list" not in names:
            tool = "git_files_list"
            args = {"directory": "."}
        elif typ != "CREATE" and "git_file_read" not in names:
            tool = "git_file_read"
            args = {"path": path}
        elif "git_files_apply" not in names:
            revision = next(
                (
                    find_key(r, "revision")
                    for r in reversed(results)
                    if find_key(r, "revision") is not None
                ),
                None,
            )
            op = {"type": typ, "path": path}
            if typ != "CREATE":
                op["expectedSha256"] = next(
                    find_key(r, "sha256")
                    for r in reversed(results)
                    if find_key(r, "sha256")
                )
            if typ != "DELETE":
                op["content"] = prompt.split("文件完整内容（不要改写）：\n", 1)[1]
            tool = "git_files_apply"
            args = {"expectedRevision": revision, "operations": [op]}
        response = {
            "model": "fixture",
            "created_at": "2026-10-10T00:00:00Z",
            "done": True,
            "done_reason": "stop",
            "message": {"role": "assistant", "content": "文件编辑操作已完成。"},
        }
        if tool:
            response["message"] = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": uuid.uuid4().hex,
                        "function": {"name": tool, "arguments": args},
                    }
                ],
            }
        body = (json.dumps(response, ensure_ascii=False) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class EngineProxy(BaseHTTPRequestHandler):
    dropped = False

    def log_message(self, *a):
        pass

    def relay(self):
        # 同步查询可能执行完整 MetricFlow 命令，代理不能先于服务中断响应。
        connection = http.client.HTTPConnection("127.0.0.1", serviceport, timeout=1900)
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        connection.request(self.command, self.path, body, dict(self.headers))
        response = connection.getresponse()
        data = response.read()
        connection.close()
        # 引擎已经持久受理后丢掉第一次构建响应，Agent必须用原幂等键恢复。
        if (
            self.command == "POST"
            and self.path == "/builds"
            and response.status in (200, 202)
            and not EngineProxy.dropped
        ):
            EngineProxy.dropped = True
            (WORK / "build-response-lost.json").write_text(
                json.dumps(
                    {
                        "fault": "accepted_build_response_lost",
                        "buildId": json.loads(data)["buildId"],
                    }
                )
            )
            self.close_connection = True
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        self.send_response(response.status)
        self.send_header(
            "Content-Type", response.getheader("Content-Type", "application/json")
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = relay
    do_POST = relay


try:
    versions = component_versions()
    run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container,
            "-e",
            "POSTGRES_PASSWORD",
            "-p",
            "127.0.0.1::5432",
            "postgres:17-alpine",
        ]
    )
    pgport = run(["docker", "port", container, "5432/tcp"]).rsplit(":", 1)[1]
    for _ in range(80):
        try:
            run(["docker", "exec", container, "pg_isready", "-U", "postgres"])
            break
        except RuntimeError:
            time.sleep(0.3)
    for db in ("engine", "agent", "platform", "warehouse"):
        run(["docker", "exec", container, "createdb", "-U", "postgres", db])
    repo = WORK / "repository.git"
    # 只对本隔离进程把受控测试 URL 映射到真实本地 Git 仓库，不修改用户 Git 配置。
    repository = "https://fixture.invalid/repository.git"
    replica_repository = "https://fixture.invalid/replica.git"
    ENV.update(
        {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "url." + WORK.as_uri() + "/.insteadOf",
            "GIT_CONFIG_VALUE_0": "https://fixture.invalid/",
        }
    )
    seed = WORK / "seed"
    shutil.copytree(
        ROOT / "dbt-metricflow-service/tests/fixtures/postgres_platform", seed
    )
    # 模型与语义YAML均位于非默认目录，不能依赖硬编码models扫描。
    (seed / "models").rename(seed / "analytics")
    projectfile = seed / "dbt_project.yml"
    projectfile.write_text(
        projectfile.read_text().replace(
            "model-paths: [models]", "model-paths: [analytics]"
        )
    )
    with projectfile.open("a") as f:
        f.write("\ntarget-path: custom-target\n")
    run(["git", "init", "--bare", "--initial-branch=main", repo])
    run(["git", "init", "-b", "main"], seed)
    run(["git", "config", "user.name", "Contract Test"], seed)
    run(["git", "config", "user.email", "contract@example.invalid"], seed)
    run(["git", "add", "."], seed)
    run(["git", "commit", "-m", "isolated fixture"], seed)
    run(["git", "remote", "add", "origin", repo], seed)
    run(["git", "push", "origin", "main"], seed)
    run(["git", "push", "origin", "HEAD:refs/heads/feature/integration"], seed)
    serviceport, agentport, platformport, modelport = port(), port(), port(), port()
    service = f"http://127.0.0.1:{serviceport}"
    agent = f"http://127.0.0.1:{agentport}"
    platform = f"http://127.0.0.1:{platformport}"
    proxyport = port()
    proxy = ThreadingHTTPServer(("127.0.0.1", proxyport), EngineProxy)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", modelport), Model)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    serviceconfig = WORK / "service.yml"
    serviceconfig.write_text(
        json.dumps(
            {
                "EXECUTION_INSTANCES": {
                    "fixture": {
                        "type": "postgres",
                        "hosts": ["127.0.0.1"],
                        "port": int(pgport),
                    }
                },
                "EXECUTION_CREDENTIALS": {
                    "fixture": {
                        "userEnv": "DBT_ENV_SECRET_FIXTURE_USER",
                        "passwordEnv": "DBT_ENV_SECRET_FIXTURE_PASSWORD",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    def execution(schema):
        return {
            "environmentId": str(uuid.uuid4()),
            "configVersion": 1,
            "connection": {
                "type": "postgres",
                "instanceId": "fixture",
                "host": "127.0.0.1",
                "port": int(pgport),
                "path": None,
            },
            "credentialRef": "fixture",
            "catalog": "warehouse",
            "schema": schema,
            "threads": 2,
            "businessTimezone": "UTC",
        }

    preview, production = (
        execution("analytics_preview"),
        execution("analytics_production"),
    )
    serviceenv = ENV | {
        "SERVICE_CONFIG_FILE": str(serviceconfig),
        "SERVICE_DATABASE_URL": f"postgresql://postgres:{SECRET}@127.0.0.1:{pgport}/engine",
        "SERVICE_TEMP_ROOT": str(WORK / "runtime"),
        "SERVICE_TOKEN": TOKEN,
        "SERVICE_HOST": "127.0.0.1",
        "SERVICE_PORT": str(serviceport),
        "DBT_ENV_SECRET_FIXTURE_USER": "postgres",
        "DBT_ENV_SECRET_FIXTURE_PASSWORD": SECRET,
        "SERVICE_CONFIG_VERSION": "1",
    }
    admin = ROOT / "dbt-metricflow-service/.venv/Scripts/dbt-service-admin.exe"
    run([admin, "init-db"], env=serviceenv)
    start(
        [ROOT / "dbt-metricflow-service/.venv/Scripts/dbt-metricflow-service.exe"],
        "engine",
        serviceenv,
    )
    wait(service, "/health/ready")
    if os.environ.get("FIXTURE_ENGINE_ONLY") == "1":
        print("engine_fixture_ready", flush=True)
        raise SystemExit(0)
    run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            rediscontainer,
            "-p",
            "127.0.0.1::6379",
            "redis:7.4-alpine",
        ]
    )
    redisport = run(["docker", "port", rediscontainer, "6379/tcp"]).rsplit(":", 1)[1]
    common = {
        "SPRING_DATASOURCE_USERNAME": "postgres",
        "SPRING_DATASOURCE_PASSWORD": SECRET,
    }
    agentenv = (
        ENV
        | common
        | {
            "SERVER_PORT": str(agentport),
            "SPRING_DATASOURCE_URL": f"jdbc:postgresql://127.0.0.1:{pgport}/agent",
            "DATA_AGENT_GIT_ENABLED": "true",
            "DATA_AGENT_GIT_WORKSPACE_ROOT": str(WORK / "workspaces"),
            "DATA_AGENT_DBT_ENABLED": "true",
            "DATA_AGENT_DBT_BASE_URL": service,
            "DATA_AGENT_DBT_SERVICE_TOKEN": TOKEN,
            "DATA_AGENT_MODEL_PROVIDER": "ollama",
            "SPRING_AI_OLLAMA_BASE_URL": f"http://127.0.0.1:{modelport}",
            "SPRING_AI_OLLAMA_INIT_PULL_MODEL_STRATEGY": "never",
            "DATA_AGENT_CONTEXT_STRATEGY": "raw",
        }
    )
    agentenv["DATA_AGENT_DBT_BASE_URL"] = f"http://127.0.0.1:{proxyport}"
    # 包装真实Git进程，仅在远端已接收push后丢失成功应答；不改变Git操作本身。
    gitwrapper = WORK / "git-fault.py"
    gitexe = shutil.which("git")
    gitwrapper.write_text(
        f"""import json,pathlib,re,subprocess,sys
ROOT=pathlib.Path({str(WORK)!r})
# Agent 会清除继承的 Git 配置；仅测试启动器显式映射受控 fixture URL。
r=subprocess.run([{gitexe!r},'-c',{"url." + WORK.as_uri() + "/.insteadOf=https://fixture.invalid/"!r}]+sys.argv[1:],capture_output=True,check=False)
if r.returncode:
    with (ROOT/'git-command-errors.jsonl').open('a',encoding='utf-8') as log:
        log.write(json.dumps({{'arguments':sys.argv[1:],'error':r.stderr.decode('utf-8','replace')}})+'\\n')
kind='merge' if any(x.endswith(':refs/heads/main') for x in sys.argv) else 'push'
marker=ROOT/(kind+'-response-lost.json')
if r.returncode==0 and 'push' in sys.argv and not marker.exists():
    refspec=next(x for x in sys.argv if re.fullmatch(r'[0-9a-f]{{40,64}}:refs/heads/.+',x))
    sha,ref=refspec.split(':',1)
    marker.write_text(json.dumps({{'fault':'git_success_response_lost','sha':sha,'ref':ref}}))
    sys.stderr.write('connection lost after remote receipt')
    sys.exit(1)
sys.stdout.buffer.write(r.stdout)
sys.stderr.buffer.write(r.stderr)
sys.exit(r.returncode)
""",
        encoding="utf-8",
    )
    # 原生进程入口保留Git的^、引号和反斜线；不能经CMD解释Git参数。
    launcher = WORK / "GitFaultLauncher.cs"
    launcher.write_text(
        r"""
using System;
using System.Diagnostics;
using System.Text;
class GitFaultLauncher {
    static string Quote(string value) {
        var result = new StringBuilder("\"");
        int slashes = 0;
        foreach(char c in value) {
            if(c == '\\') { slashes++; continue; }
            result.Append('\\', c == '"' ? slashes * 2 + 1 : slashes);
            result.Append(c); slashes = 0;
        }
        result.Append('\\', slashes * 2); result.Append('"');
        return result.ToString();
    }
    static int Main(string[] args) {
        var command = new StringBuilder(Quote(Environment.GetEnvironmentVariable("CONTRACT_GIT_FAULT_SCRIPT")));
        foreach(var arg in args) command.Append(" ").Append(Quote(arg));
        var start = new ProcessStartInfo(Environment.GetEnvironmentVariable("CONTRACT_GIT_FAULT_PYTHON"), command.ToString());
        start.UseShellExecute = false; start.CreateNoWindow = true;
        start.RedirectStandardOutput = true; start.RedirectStandardError = true;
        using(var process = Process.Start(start)) {
            var stdout = process.StandardOutput.BaseStream.CopyToAsync(Console.OpenStandardOutput());
            var stderr = process.StandardError.BaseStream.CopyToAsync(Console.OpenStandardError());
            process.WaitForExit(); System.Threading.Tasks.Task.WaitAll(stdout, stderr);
            return process.ExitCode;
        }
    }
}
""",
        encoding="utf-8",
    )
    gitlauncher = WORK / "git-fault.exe"
    compiler = (
        pathlib.Path(os.environ["WINDIR"])
        / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    )
    run([compiler, "/nologo", "/target:exe", "/out:" + str(gitlauncher), launcher])
    agentenv["CONTRACT_GIT_FAULT_PYTHON"] = PY
    agentenv["CONTRACT_GIT_FAULT_SCRIPT"] = str(gitwrapper)
    # 在真实历史对象上自检参数完整性，再允许Agent使用故障入口。
    tree = run([gitlauncher, "rev-parse", "HEAD^{tree}"], seed, agentenv)
    if not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise RuntimeError("git_launcher_output_invalid")
    agentenv["DATA_AGENT_GIT_EXECUTABLE"] = str(gitlauncher)
    start(
        [
            "java",
            "-jar",
            ROOT
            / "data-agent-v2/backend/agent-server/target/agent-server-0.1.0-SNAPSHOT.jar",
            f"--spring.ai.ollama.base-url=http://127.0.0.1:{modelport}",
            "--spring.ai.ollama.init.pull-model-strategy=never",
        ],
        "agent",
        agentenv,
    )
    wait(agent, "/actuator/health")
    platformenv = (
        ENV
        | common
        | {
            "SERVER_PORT": str(platformport),
            "SPRING_DATASOURCE_URL": f"jdbc:postgresql://127.0.0.1:{pgport}/platform",
            "DBT_SERVICE_BASE_URI": service,
            "DBT_SERVICE_TOKEN": TOKEN,
            "METRIC_PLATFORM_BUILD_HISTORY_POLL_MS": "300",
            "MANAGEMENT_HEALTH_REDIS_ENABLED": "false",
            "METRIC_PLATFORM_IDENTITY_AUTH_BOOTSTRAP_PASSWORD": SECRET,
        }
    )
    platformenv["SPRING_APPLICATION_JSON"] = json.dumps(
        {
            "metric-platform": {
                "identity-auth": {"bootstrap": {"password": SECRET}},
                "build-history": {"poll-ms": 300},
            },
            "spring": {
                "data": {
                    "redis": {
                        "host": "127.0.0.1",
                        "port": int(redisport),
                        "password": "",
                    }
                }
            },
        }
    )
    platformcmd = [
        "java",
        "-jar",
        ROOT
        / "metric-platform/backend/metric-app/target/metric-app-0.1.0-SNAPSHOT.jar",
    ]
    platformprocess = start(platformcmd, "platform", platformenv)
    wait(platform, "/actuator/health")
    access = api(
        platform, "/api/v1/auth/token", {"username": "admin", "password": SECRET}
    )["accessToken"]
    project = api(
        agent, "/api/v1/agent-projects", {"name": "Isolated contract fixture"}
    )["projectId"]
    request = urllib.request.Request(
        agent + f"/api/v1/agent-projects/{project}/development-config",
        method="PUT",
        data=json.dumps(
            {
                "repository": repository,
                "previewExecution": preview,
                "productionExecution": production,
                "expectedVersion": 0,
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(request).close()
    config = {
        "agentBaseUrl": agent,
        "metricPlatformBaseUrl": platform,
        "dbtServiceBaseUrl": service,
        "agentProjectId": project,
        "repository": repository,
        "branchName": "feature/integration",
        "previewExecution": preview,
        "productionExecution": production,
        "dbtServiceTokenEnvironment": "CONTRACT_ENGINE_TOKEN",
        "platformTokenEnvironment": "CONTRACT_PLATFORM_TOKEN",
    }
    configpath = WORK / "config.json"
    configpath.write_text(json.dumps(config))
    flowenv = ENV | {"CONTRACT_ENGINE_TOKEN": TOKEN, "CONTRACT_PLATFORM_TOKEN": access}
    # 第二真实仓库保留同名分支，验证自然键不会串到首个仓库的部署。
    replica = WORK / "replica.git"
    run(["git", "clone", "--bare", repo, replica])
    secondproject = api(
        agent, "/api/v1/agent-projects", {"name": "Repository isolation fixture"}
    )["projectId"]
    secondbody = {
        "repository": replica_repository,
        "previewExecution": preview,
        "productionExecution": production,
        "expectedVersion": 0,
    }
    urllib.request.urlopen(
        urllib.request.Request(
            agent + f"/api/v1/agent-projects/{secondproject}/development-config",
            method="PUT",
            data=json.dumps(secondbody).encode(),
            headers={"Content-Type": "application/json"},
        )
    ).close()
    comparisonpath = WORK / "comparison.json"
    comparisonpath.write_text(
        json.dumps(
            config | {"agentProjectId": secondproject, "repository": replica_repository}
        )
    )
    (TASK / "active-fixture.json").write_text(
        json.dumps(
            {
                "work": str(WORK),
                "container": container,
                "agent": agent,
                "platform": platform,
                "service": service,
                "config": str(configpath),
                "model": "deterministic Ollama fixture",
            }
        )
    )
    print("fixture_ready:" + str(WORK), flush=True)
    log = logs.enter_context(open(WORK / "flow.log", "w", encoding="utf-8"))  # noqa: SIM115
    flow = subprocess.run(
        [
            "pwsh",
            "-NoProfile",
            "-File",
            str(ROOT / "infra/verification/Test-MetricsBranchFlow.ps1"),
            "-ConfigPath",
            str(configpath),
            "-ComparisonConfigPath",
            str(comparisonpath),
            "-ModelDirectory",
            "analytics",
            "-OutputDirectory",
            str(WORK),
        ],
        env=flowenv,
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    print("flow_exit:" + str(flow.returncode), flush=True)
    exitcode = flow.returncode
    if flow.returncode == 0:
        from urllib.parse import urlencode

        evidence = json.loads(
            (WORK / "flow-result.json").read_text(encoding="utf-8-sig")
        )
        injections = [
            name
            for name in (
                "push-response-lost.json",
                "merge-response-lost.json",
                "build-response-lost.json",
            )
            if (WORK / name).is_file()
        ]
        if len(injections) != 3:
            raise RuntimeError("fault_injections_incomplete")
        # 对比首次远端成功的身份，不能仅凭最终状态成功推断恢复没有重复副作用。
        facts = evidence["evidence"]["identities"]
        receipts = {
            name: json.loads((WORK / (name + "-response-lost.json")).read_text())
            for name in ("push", "merge", "build")
        }
        if receipts["push"]["sha"] not in [fact.get("pushedSha") for fact in facts]:
            raise RuntimeError("push_recovery_changed_identity")
        if receipts["merge"]["sha"] not in [fact.get("mergeSha") for fact in facts]:
            raise RuntimeError("merge_recovery_changed_identity")
        if receipts["build"]["buildId"] not in [
            build_id for fact in facts for build_id in fact.get("buildIds", [])
        ]:
            raise RuntimeError("build_recovery_changed_identity")
        history = {"items": []}
        for snapshot in (preview, production):
            page = api(
                service,
                "/builds?"
                + urlencode(
                    {
                        "environmentId": snapshot["environmentId"],
                        "repository": repository,
                        "limit": 200,
                    }
                ),
                token=TOKEN,
            )
            history["items"].extend(page["items"])
        if len(history["items"]) != 4:
            raise RuntimeError("unexpected_extra_build")
        # 停止平台期间，Agent及引擎继续独立工作；重启后从服务实时读取历史，不依赖changefeed检查点。
        sessions = api(agent, "/api/v1/agent-sessions")
        session = find_key(sessions, "conversationSessionId")
        state = api(agent, f"/api/v1/agent-sessions/{session}/development")
        platformprocess.terminate()
        platformprocess.wait(timeout=30)
        operation = api(
            agent,
            f"/api/v1/agent-sessions/{session}/development/preview",
            {
                "idempotencyKey": uuid.uuid4().hex,
                "expectedRevision": state["local"]["revision"],
                "commitMessage": "Platform offline reconciliation",
            },
        )
        deadline = time.time() + 180
        while time.time() < deadline:
            operation = api(
                agent,
                f"/api/v1/agent-sessions/{session}/development/operations/"
                + operation["operationId"],
            )
            if operation["status"] in ("SUCCEEDED", "FAILED", "BLOCKED"):
                break
            time.sleep(0.5)
        if operation["status"] != "SUCCEEDED":
            raise RuntimeError("offline_platform_preview_failed")
        platformprocess = start(platformcmd, "platform-restarted", platformenv)
        wait(platform, "/actuator/health")
        deadline = time.time() + 30
        while time.time() < deadline:
            restored = api(
                platform,
                "/api/dbt/builds?"
                + urlencode(
                    {
                        "environmentId": preview["environmentId"],
                        "repository": repository,
                        "limit": 200,
                    }
                ),
                token=access,
            )
            if operation["buildIds"][-1] in [b["buildId"] for b in restored["items"]]:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("platform_history_not_read")
        evidence["evidence"]["faultInjections"] = injections
        evidence["evidence"]["recoveredReceipts"] = receipts
        evidence["evidence"]["platformRestartObservedBuildId"] = operation["buildIds"][
            -1
        ]
        evidence["evidence"]["actualComponents"] = [
            "real Git",
            "real PostgreSQL",
            "real dbt/MetricFlow",
            "real Redis",
            "deterministic model fixture",
        ]
        evidence["evidence"]["componentVersions"] = versions
        # 浏览器使用独占端口访问真实平台；禁用包含登录凭据的trace/截图产物。
        browserenv = ENV | {
            "DBT_POSTGRES_E2E": "1",
            "DBT_POSTGRES_E2E_PLATFORM_URL": platform,
            "DBT_POSTGRES_E2E_FRONTEND_PORT": str(port()),
            "DBT_POSTGRES_E2E_OUTPUT_DIR": str(WORK / "browser-results"),
            "DBT_POSTGRES_E2E_USER": "admin",
            "DBT_POSTGRES_E2E_PASSWORD": SECRET,
            "DBT_POSTGRES_E2E_BUILD_ID": operation["buildIds"][-1],
        }
        browser = start(
            [
                "npm.cmd",
                "run",
                "test:e2e",
                "--",
                "--config=playwright.postgres.config.ts",
            ],
            "browser",
            browserenv,
            cwd=ROOT / "metric-platform/frontend",
        )
        if browser.wait(timeout=300):
            raise RuntimeError("real_browser_failed")
        evidence["evidence"]["realBrowser"] = "PASS"
        (WORK / "coordinated-result.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("coordinated_faults_and_live_history:PASS", flush=True)
    # 退出检查只在新版服务预检成功后执行。
    with open(WORK / "regression.log", "w", encoding="utf-8") as log:
        regression = subprocess.run(
            [
                "pwsh",
                "-NoProfile",
                "-File",
                str(ROOT / "infra/verification/Test-MetricsBranchRegression.ps1"),
                "-ConfigPath",
                str(configpath),
            ],
            env=flowenv,
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    print("regression_exit:" + str(regression.returncode), flush=True)
    exitcode = max(exitcode, regression.returncode)
except (
    OSError,
    ValueError,
    RuntimeError,
    LookupError,
    subprocess.SubprocessError,
    http.client.HTTPException,
) as failure:
    exitcode = 1
    print(
        "fixture_failed:" + type(failure).__name__ + ":" + str(failure)[:120],
        flush=True,
    )
finally:
    # Windows终止父进程不会终止dbt、MetricFlow及浏览器子进程，按本脚本持有的PID清理整棵树。
    for p in reversed(procs):
        if p.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
    for p in procs:
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()
    logs.close()
    subprocess.run(
        ["docker", "rm", "-f", container],
        capture_output=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    subprocess.run(
        ["docker", "rm", "-f", rediscontainer],
        capture_output=True,
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    print("fixture_stopped:" + str(WORK), flush=True)
raise SystemExit(exitcode)
