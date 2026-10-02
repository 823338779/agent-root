set -euo pipefail

# 从脚本位置定位桌面入口，允许在任意工作目录调用。
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python "$SCRIPT_DIR/app.py" "$@"
