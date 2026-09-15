#!/bin/bash
# 推送 九霄仙门 代码到服务器（不覆盖数据库）
# 用法: ./deploy.sh          仅推代码+模板(默认,日常用这个)
#       ./deploy.sh --static 额外推 static/(图片等静态资源改了才需要)
#
# 目录用 tar.gz 打包成单文件传输,而不是 scp -r 逐个小文件传
# (Windows OpenSSH 对着一堆小文件走 scp -r 巨慢,每个文件都要单独握手+被
#  Defender 实时扫描;templates 63 个文件曾经量过要占掉部署耗时的大头。
#  远端已确认装了 bsdtar,tar.exe 是 Windows 10/Server 2019+ 自带的。)
set -e

SERVER="yulequan-server"
REMOTE_DIR="C:/Users/Administrator/jiuxiao_xianmen"
WIN_DIR="C:\Users\Administrator\jiuxiao_xianmen"
LOCAL_DIR="$(dirname "$0")"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo ">>> 推送 九霄仙门 到 $SERVER:$REMOTE_DIR"

scp "$LOCAL_DIR/app.py" "$LOCAL_DIR/game_data.py" "$LOCAL_DIR/run.py" \
    "$LOCAL_DIR/requirements.txt" "$LOCAL_DIR/schema.sql" "$SERVER:$REMOTE_DIR/"

# 打包成一个 tar.gz 单文件传过去,远端解压到 templates_new 再原地改名替换,
# 避免"先删旧目录再传新的"之间那个空窗期
# (曾经真的在这个窗口里接到过请求,报 TemplateNotFound)
push_dir() {
  local name="$1"
  echo ">>> 推送 $name/(打包 tar.gz 传输,再原地改名替换)..."
  COPYFILE_DISABLE=1 tar czf "$TMP_DIR/$name.tar.gz" -C "$LOCAL_DIR/$name" .
  scp "$TMP_DIR/$name.tar.gz" "$SERVER:$REMOTE_DIR/$name.tar.gz"
  ssh "$SERVER" "(if exist $WIN_DIR\\${name}_new rmdir /s /q $WIN_DIR\\${name}_new) & mkdir $WIN_DIR\\${name}_new & tar xzf $WIN_DIR\\$name.tar.gz -C $WIN_DIR\\${name}_new & del $WIN_DIR\\$name.tar.gz & (if exist $WIN_DIR\\${name}_old rmdir /s /q $WIN_DIR\\${name}_old) & ren $WIN_DIR\\$name ${name}_old & ren $WIN_DIR\\${name}_new $name & rmdir /s /q $WIN_DIR\\${name}_old"
}

push_dir templates

if [ "$1" == "--static" ]; then
  push_dir static
else
  echo ">>> 跳过 static/(图片等静态资源没变;要推就加 --static 参数)"
fi

echo ">>> 重启服务..."
if ! ssh "$SERVER" "nssm restart jiuxiaoxianmen"; then
  echo ">>> restart 失败(常见于服务还卡在 STOP_PENDING),改用 stop+start 兜底"
  ssh "$SERVER" "nssm stop jiuxiaoxianmen"
  ssh "$SERVER" "powershell -NoProfile -Command \"Start-Sleep -Seconds 4\""
  ssh "$SERVER" "nssm start jiuxiaoxianmen"
fi

echo ">>> 完成！"
