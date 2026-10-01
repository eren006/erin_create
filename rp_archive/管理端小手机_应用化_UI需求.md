# 管理端小手机「应用化」UI 需求（给 GPT）

## 目标
管理员登录 `/p/admin` 后，现在是一个长列表（几个入口行 + 全体角色行）。改成**像手机桌面**：首页是一屏应用图标（App），点进去才是各自的功能页。只改 UI，**不改后端逻辑和路由**。

## 现有页面 → 对应 App（路由都已存在，直接链接）
| App | 路由（`url_for` 名） | 现状 |
|---|---|---|
| 角色 | `admin_phone_index` 的角色列表部分；点角色进 `admin_phone_inbox` / `admin_phone_character` | 现在直接铺在首页，要收进一个 App |
| 催回 | `admin_phone_urge`（`mode == 'admin_urge'`） | 新做，朴素列表，需要美化 |
| 设置 | `admin_phone_settings`（`mode == 'admin_settings'`）：发起官约/官电、批量发放、参数 | 已有 |
| 公开播报·点歌 | `player_phone_public` | 已有 |
| 朋友圈 | `player_moments` | 已有 |
| 指南 | `phone_guide` | 已有 |

首页右上角/顶部保留：退出按钮（POST `player_phone_logout`）、插件状态条（`plugin.text` / `plugin.level`，链到设置）。

## 要求
- 改动集中在 `templates/phone.html` 里 `mode == 'admin_index'` 一段、`phone_admin` 底栏（文件末尾 `bottom-dock`）、`admin_urge` 一段，样式写进现有 `<style>`。
- 颜色用主题变量（`--bg --line --mine --theirs --muted --text`），不要写死颜色；浅色/深色、手机宽度 375 都要好看。六套外观主题（`PHONE_THEMES`）下不能破相。
- App 图标：用 emoji 或内联 SVG，不引外部资源。可以带角标（例如催回图标上显示超时数，数据 `urge_rows|selectattr('over')|list|length`，需要的话在 `admin_phone_index` 路由里补一个变量，改动尽量小）。
- 子页面要有统一的返回条（`.bar` + `.back`，返回 `admin_phone_index`）；底栏可以简化成「桌面 / 退出」或去掉，由你决定，但 `mode` 高亮条件要同步。
- 不要动：表单字段名、`csrf` 隐藏域、`data-confirm` 确认弹窗逻辑、`/p/admin/*/op` 的路由与参数。
- 新增页面 mode 时必须同步 phone.html 里几处 `mode in (...)` 列表（见 `.claude/skills/phone/SKILL.md` 第 1 条），否则会缺底栏/主题。

## 验证
`rp_archive/tests/run_all.sh phone` 必须全过（`phone_admin_test.py`、`phone_admin_ops_test.py` 有断言页面文案，改文案前先看断言）；本机预览 `/p/admin` 手机宽度 + 浅/深色各看一眼。
