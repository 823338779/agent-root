"""核对两端独立保存的契约样例，防止仅靠旧 HTTP fixture 获得假阳性。"""

import json
from pathlib import Path

from dbt_metricflow_service.models import (
    builds,
    catalog,
    deployments,
    execution,
    queries,
)

# 跨产品校验只放在根工作区；各产品仍保留自己的测试资源及独立构建入口。
ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "dbt-metricflow-service/tests/fixtures/contract.json"
CONSUMERS = (
    ROOT / "data-agent-v2/backend/agent-dbt/src/test/resources/contracts/dbt.json",
    ROOT
    / "metric-platform/backend/metric-engine/src/test/resources/contracts/dbt.json",
)
MODEL_MODULES = (builds, catalog, deployments, execution, queries)
EXAMPLES = "examples"
MODEL = "model"
VALUE = "value"


def main() -> None:
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    # 先用实际服务模型验证权威样例，再确认消费者使用同一组输入输出边界。
    for example in authority[EXAMPLES]:
        model = next(
            getattr(module, example[MODEL])
            for module in MODEL_MODULES
            if hasattr(module, example[MODEL])
        )
        model.model_validate(example[VALUE])
    for path in CONSUMERS:
        if json.loads(path.read_text(encoding="utf-8")) != authority:
            raise SystemExit(f"FAIL：契约样例已落后于服务端：{path.relative_to(ROOT)}")
    print(
        f"PASS：服务端 {len(authority[EXAMPLES])} 个协议样例有效，两个调用方样例一致。"
    )


if __name__ == "__main__":
    main()
