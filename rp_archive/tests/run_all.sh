#!/bin/bash
# 一次跑完 rp_archive/tests 下所有 *_test.py（每个都用临时库，不碰真实数据），按退出码判断通过与否。
# 用法（仓库根目录）：rp_archive/tests/run_all.sh        # 全跑
#                     rp_archive/tests/run_all.sh phone  # 只跑文件名里带 phone 的
# 改了网页手机 / 后台页面后跑一遍；测试失败多半是页面文案或结构变了而断言还是旧的，先看是不是真 bug，再改断言。
cd "$(dirname "$0")/../.." || exit 1
PY=rp_archive/venv/bin/python3; [ -x "$PY" ] || PY=python3
pass=0; fail=()
for f in rp_archive/tests/*${1}*_test.py; do
  if "$PY" "$f" >/tmp/rp_test_out.$$ 2>&1; then pass=$((pass+1)); echo "✅ $(basename "$f")"
  else fail+=("$(basename "$f")"); echo "❌ $(basename "$f")"; grep -A4 Traceback /tmp/rp_test_out.$$ | tail -6 | cut -c1-200; fi
done
rm -f /tmp/rp_test_out.$$
echo "—— 通过 $pass，失败 ${#fail[@]} ${fail[*]}"
[ ${#fail[@]} -eq 0 ]
