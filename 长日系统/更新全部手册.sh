#!/bin/bash
# 改完 生成指令手册.py 里的 SECTIONS 后，跑这一个脚本就够了：
# 先查有没有新指令忘记写文档，再把 PDF/HTML/Word 三份一起重新生成。
set -e
cd "$(dirname "$0")"

python3 check_manual_coverage.py || { echo "❌ 有指令还没写进手册，请先补全 SECTIONS 再重新生成"; exit 1; }

python3 生成指令手册.py
python3 生成指令手册_html.py
python3 生成指令手册_docx.py

echo "✅ PDF/HTML/Word 三份手册已全部更新"
