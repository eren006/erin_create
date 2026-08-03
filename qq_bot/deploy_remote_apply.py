"""增量部署压缩包在 Windows 服务器上的清理步骤，仅由 deploy.sh 临时调用。"""

from pathlib import Path

base = Path(__file__).resolve().parent
delete_list = base / "__deploy_delete__.txt"

if delete_list.exists():
    for raw in delete_list.read_text(encoding="utf-8").splitlines():
        relative = raw.strip().replace("\\", "/")
        if not relative:
            continue
        target = (base / relative).resolve()
        try:
            target.relative_to(base)
        except ValueError as exc:
            raise RuntimeError(f"拒绝删除项目目录之外的路径：{relative}") from exc
        if target.is_file():
            target.unlink()
    delete_list.unlink()
