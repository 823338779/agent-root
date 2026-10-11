"""旧历史迁移入口已退出；拒绝在不支持迁移的服务上创建验收环境。"""

# 服务端只支持初始化新库，不应先创建容器或伪造旧构建身份再尝试迁移。
UNSUPPORTED_MIGRATION = (
    "dbt-service 已移除 migrate/migrate-history，不支持旧历史数据迁移。"
    "请保留旧数据库和产物备份，按 dbt-metricflow-service/README.md 使用新库及 init-db，"
    "再运行 Invoke-IsolatedMetricsBranchFlow.py 验证新协议。"
)

if __name__ == "__main__":
    raise SystemExit(UNSUPPORTED_MIGRATION)
