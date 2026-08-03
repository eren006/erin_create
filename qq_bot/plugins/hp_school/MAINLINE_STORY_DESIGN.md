# 一年级主线故事系统设计文档

## 1. 系统概述

**核心特性**
- 全服共享世界观的分支故事系统
- 每个学生独立触发和选择，集体结果决定故事走向
- 支持长故事（20+阶段，跨整学年）和短故事（5阶段，1周）
- 二年级继承一年级的故事结局，影响后续剧情
- 参与奖励（加隆）+ 故事驱动

---

## 2. 核心机制

### 2.1 触发机制
```
每日处理逻辑（定时任务，如凌晨1点执行）：
1. 遍历所有激活的故事
2. 对于每个已入学的学生（grade >= 1）：
   - 20%概率触发故事任务（同一个故事每个学生最多1次/天）
   - 如果学生未参与过该故事当前阶段，记录为"可选择"状态
   - 如果已参与，跳过

3. 检查阶段推进条件：
   - IF 参与人数 >= 阈值人数 OR 距上阶段开始时间 >= N天
     - 记录此阶段的最终结果（多数选择）
     - 推进到下一阶段
     - 重置参与计数器
```

### 2.2 选择统计
```
每次学生做出选择后：
1. 记录到 story_choices 表
2. 奖励 参与加隆（如 10加隆）
3. 检查是否达到推进条件
   - 如果达到：立即推进（不等待每日处理）
   - 同时推送通知："阶段已推进"
```

### 2.3 多数决规则
```
结算时计算：
- 统计所有选择的人数分布
- 选项A: 45人
- 选项B: 30人
- 选项C: 25人
→ A胜出，进入A路线的下一阶段

平票情况：
- 如果有并列最多，按字母序（A > B > C）或设定的优先级
```

### 2.4 阶段推进
```
推进条件（两者取其一）：
1. 参与人数 >= max(全校当前年级学生数 * 30%, 10)
   （最少10人也要能推进）
2. 距上阶段开始时间 >= N天（建议3-5天）

当推进时：
- phase += 1
- phase_started_at = now
- participated_count = 0
- last_result = {winning_choice, stats}
- 如果达到 max_phases，标记故事为 ended=true
```

---

## 3. 数据库设计

### 3.1 故事元数据表
```sql
CREATE TABLE IF NOT EXISTS mainline_stories (
    story_id TEXT PRIMARY KEY,           -- "year1_thirteenth_bell"
    title TEXT NOT NULL,                 -- "第十三声钟响"
    description TEXT,                    -- 故事简介
    enabled_grade INT NOT NULL,          -- 从哪一年级开始（1表示一年级）
    story_type TEXT NOT NULL,            -- "long" 或 "short"
    phase INT DEFAULT 0,                 -- 当前阶段（0=未开始, 1=进行中, etc）
    max_phases INT NOT NULL,             -- 总阶段数（5或20+）
    phase_started_at INTEGER,            -- 当前阶段开始时间戳
    participated_count INT DEFAULT 0,    -- 当前阶段参与人数
    trigger_threshold INT,               -- 触发阈值（人数）
    phase_duration_days INT DEFAULT 3,   -- 自动推进天数（若人数不足）
    active BOOLEAN DEFAULT 1,            -- 是否激活
    created_at INTEGER NOT NULL,
    ended_at INTEGER                     -- 故事结束时间
);
```

### 3.2 阶段配置表
```sql
CREATE TABLE IF NOT EXISTS mainline_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id TEXT NOT NULL,
    phase INT NOT NULL,                  -- 第几阶段
    title TEXT NOT NULL,                 -- "异象初现"
    description TEXT,                    -- 阶段描述
    prompt TEXT,                         -- 故事叙述文本
    options JSON NOT NULL,               -- [
                                         --   {"key": "A", "text": "报告教授", "next_phase": 2},
                                         --   {"key": "B", "text": "隐瞒真相", "next_phase": 2}
                                         -- ]
    result_text JSON,                    -- 各选项胜出时的结果文本
                                         -- {
                                         --   "A": "级长确认了异常钟声。",
                                         --   "B": "湿脚印停在实心墙前。"
                                         -- }
    FOREIGN KEY (story_id) REFERENCES mainline_stories(story_id),
    UNIQUE(story_id, phase)
);
```

### 3.3 学生参与记录表
```sql
CREATE TABLE IF NOT EXISTS mainline_choices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid TEXT NOT NULL,
    story_id TEXT NOT NULL,
    phase INT NOT NULL,
    choice_key TEXT NOT NULL,            -- "A" / "B" / "C"
    chosen_at INTEGER NOT NULL,          -- 选择时间戳
    reward_galleons INT DEFAULT 10,      -- 奖励金额
    FOREIGN KEY (story_id) REFERENCES mainline_stories(story_id),
    UNIQUE(uid, story_id, phase)         -- 每个学生每个故事每个阶段只能选一次
);
```

### 3.4 阶段结果记录表
```sql
CREATE TABLE IF NOT EXISTS mainline_phase_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id TEXT NOT NULL,
    phase INT NOT NULL,
    winning_choice TEXT NOT NULL,        -- "A" / "B" / "C"
    stats JSON NOT NULL,                 -- {"A": 45, "B": 30, "C": 25}
    triggered_count INT,                 -- 该阶段参与人数
    push_message TEXT,                   -- 推送给全服的消息
    concluded_at INTEGER NOT NULL,       -- 结算时间
    FOREIGN KEY (story_id) REFERENCES mainline_stories(story_id),
    UNIQUE(story_id, phase)
);
```

### 3.5 故事结局记录表
```sql
CREATE TABLE IF NOT EXISTS mainline_endings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id TEXT NOT NULL,
    uid TEXT NOT NULL,
    ending_key TEXT NOT NULL,            -- "好结局_A路线" 等标签
    ending_text TEXT,                    -- 个性化结局文本
    choices_path JSON,                   -- [{"phase": 1, "choice": "A"}, ...]
    completed_at INTEGER NOT NULL,
    FOREIGN KEY (story_id) REFERENCES mainline_stories(story_id),
    UNIQUE(uid, story_id)
);
```

### 3.6 故事全局状态表
```sql
CREATE TABLE IF NOT EXISTS mainline_story_state (
    story_id TEXT NOT NULL,
    state_key TEXT NOT NULL,             -- professor_trust / evidence / echo_power 等
    state_value INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (story_id, state_key),
    FOREIGN KEY (story_id) REFERENCES mainline_stories(story_id)
);
```

阶段结算时读取胜出选项的 `effects` 并原子累加。布尔剧情旗标也存为 `0/1`，例如 `voluntary_memory` 和 `heard_echo`。

### 3.7 个人剧情标签表
```sql
CREATE TABLE IF NOT EXISTS mainline_personal_tags (
    uid TEXT NOT NULL,
    story_id TEXT NOT NULL,
    tag_key TEXT NOT NULL,               -- witness / explorer / echo_friend 等
    score INTEGER NOT NULL DEFAULT 0,    -- 每次个人选择累积倾向分
    awarded BOOLEAN NOT NULL DEFAULT 0,  -- 故事结束后是否成为正式标签
    PRIMARY KEY (uid, story_id, tag_key),
    FOREIGN KEY (story_id) REFERENCES mainline_stories(story_id)
);
```

选项配置可以同时包含全服效果 `effects` 与个人倾向 `personal_tags`。前者只在多数选择结算后应用一次，后者在每名玩家选择时立即记录：

```json
{
  "key": "C",
  "text": "把画像临摹下来",
  "effects": {"public_truth": 1},
  "personal_tags": {"witness": 2, "explorer": 1}
}
```

---

## 4. 业务逻辑模块

### 4.1 故事初始化
```python
def init_story_phase(story_id: str, phase: int) -> None:
    """在每个故事启动时初始化第一阶段"""
    # 从 mainline_phases 读取配置
    # 设置 mainline_stories.phase = 1
    # 设置 phase_started_at = now
```

### 4.2 每日触发处理
```python
def daily_trigger_check() -> None:
    """每日凌晨1点执行"""
    for story in get_active_stories():
        for student in get_students_by_grade(story.enabled_grade):
            if random.random() < 0.20:  # 20%概率
                if not has_choice_in_phase(student.uid, story.story_id, story.phase):
                    mark_as_eligible(student.uid, story.story_id, story.phase)
    
    # 检查所有故事是否应该推进
    for story in get_active_stories():
        check_and_advance_phase(story.story_id)
```

### 4.3 推进阶段
```python
def check_and_advance_phase(story_id: str) -> bool:
    """检查是否满足推进条件"""
    story = get_story(story_id)
    grade_students = count_students_by_grade(story.enabled_grade)
    threshold = max(grade_students * 0.30, 10)
    days_elapsed = (now - story.phase_started_at) / 86400
    
    # 条件1：人数达到阈值
    if story.participated_count >= threshold:
        advance_phase(story_id)
        return True
    
    # 条件2：时间达到
    if days_elapsed >= story.phase_duration_days:
        advance_phase(story_id)
        return True
    
    return False

def advance_phase(story_id: str) -> None:
    """执行阶段推进"""
    story = get_story(story_id)
    
    # 计算本阶段胜出选项
    winning_choice = get_winning_choice(story_id, story.phase)
    stats = get_choice_stats(story_id, story.phase)
    
    # 记录结果
    save_phase_result(story_id, story.phase, winning_choice, stats)
    
    # 推进到下一阶段
    if story.phase < story.max_phases:
        update_story(story_id, {
            'phase': story.phase + 1,
            'phase_started_at': now,
            'participated_count': 0
        })
        # 推送通知给全服
        broadcast(f"【{story.title}】阶段推进：第{story.phase + 1}阶段开始")
    else:
        # 故事结束
        end_story(story_id)
```

### 4.4 学生选择处理
```python
def student_make_choice(uid: str, story_id: str, phase: int, choice_key: str) -> dict:
    """学生做出选择"""
    # 验证学生是否有权选择
    if not has_choice_for_phase(uid, story_id, phase):
        raise "你还没有接到这个任务"
    
    # 检查选择是否有效
    if choice_key not in get_valid_choices(story_id, phase):
        raise "无效的选择"
    
    # 保存选择
    save_choice(uid, story_id, phase, choice_key, 10)  # 10金币奖励
    
    # 增加参与计数
    increment_participated_count(story_id, phase)
    
    # 检查是否应该立即推进
    check_and_advance_phase(story_id)
    
    return {
        'reward': 10,
        'total_choices': get_choice_stats(story_id, phase)
    }
```

### 4.5 故事结束
```python
def end_story(story_id: str) -> None:
    """故事结束，计算个人结局"""
    story = get_story(story_id)
    
    for uid in get_story_participants(story_id):
        # 获取该学生的完整选择路径
        choices_path = get_student_choices_path(uid, story_id)
        
        # 根据选择路径确定结局key
        ending_key = calculate_ending_key(story_id, choices_path)
        
        # 生成个性化结局文本
        ending_text = render_ending_text(story_id, ending_key, uid)
        
        # 保存结局
        save_ending(uid, story_id, ending_key, ending_text, choices_path)
    
    # 标记故事为已结束
    update_story(story_id, {'active': False, 'ended_at': now})
```

---

## 5. QQ机器人命令接口

### 5.1 查看当前任务
```
/阶段任务
→ 列出当前正在进行的所有故事阶段
  ✓ 已选择：A (15人)
  ○ 未选择：B (0人) / C (0人)
  进度：23/80人参与
```

### 5.2 做出选择
```
/选择 钟声 A
→ "你已选择：叫醒级长。等待其他学生的选择……"
```

### 5.3 查看故事进度
```
/故事进度
→ 列出所有故事的阶段进度
  【第十三声钟响】 2/20 | 进行中
  【厨房里多出的一套餐具】 0/5 | 未开始
```

---

## 6. 网页展示设计

### 6.1 故事看板页面 (`/static/mainline.html`)
```
═══════════════════════════════════════
        🏰 霍格沃茨阶段任务看板
═══════════════════════════════════════

【活跃故事】
┌─ 第十三声钟响 (2/20 阶段)
│  ├─ 进度条: ██████░░░░░░░░░░░░░░░░ 30%
│  ├─ 当前阶段: 被抹去的画像
│  ├─ 选择结果: 
│  │  ○ 询问附近的画像 (45人) ← 领先
│  │  ○ 检查画框背面 (30人)
│  │  ○ 把画像临摹下来 (25人)
│  ├─ 推进条件: 45/80 人参与 (还需35人或3天后自动推进)
│  └─ [你的选择: 检查画框背面 ✓]
│
└─ 厨房里多出的一套餐具 (0/5 阶段)
   └─ 尚未开启...

【历史故事】
┌─ 学院竞争升级 ✓ (已完成 5/5)
│  └─ 结局: 学院杯争夺激烈 | 你选择了: A路线 | 完成于 2026-08-20
│
└─ 幽灵的悲鸣 ✓ (已完成 5/5)
   └─ 结局: 真相大白 | 你选择了: B路线 | 完成于 2026-08-25

```

### 6.2 个人结局详情页
```
【你的故事线】

第十三声钟响
────────
你的选择路径：
  阶段1 [午夜之后] → 选择 B (跟随脚印)
  阶段2 [被抹去的画像] → 选择 B (检查画框背面)
  阶段3 [楼梯尽头的门] → 选择 C (先用魔法测试门)
  阶段4 [没有名字的课桌] → 选择 C (不回答，先检查周围)
  
你的结局：
"你把那份不会褪色的记录夹进成长册。所有人都忘记空白画像上曾经写过什么，
但你仍能看见那行小字：谢谢你记得我。"

全校选择统计：
  A路线: 156人 (42%)
  B路线: 142人 (38%)
  C路线: 82人 (22%)

全校最终结局：无声的黎明 | 个人标签：记忆见证者
```

### 6.3 实时更新
- 故事阶段推进时，实时推送到QQ：
  ```
  【第十三声钟响】阶段推进！第2阶段开始
  多数选择：叫醒级长（45票）
  新任务已下发，请发送 /阶段任务 查看
  ```

---

## 7. 一年级长主线：《第十三声钟响》

### 7.1 故事定位

```python
story = {
    "story_id": "year1_thirteenth_bell",
    "title": "第十三声钟响",
    "enabled_grade": 1,
    "story_type": "long",
    "max_phases": 20,
    "trigger_threshold": None,
    "phase_duration_days": 3,
}
```

霍格沃茨的午夜钟本应只响十二次。新生入学后，少数学生却听见了第十三声；每次钟响，城堡里就有一样东西从众人的记忆中消失。被遗忘的事物并未真正消失，而是落进了城堡夹层中的“无名回廊”。

玩家在那里遇见只能出现在镜面和积水倒影中的少年“埃利奥特”。他声称自己曾是霍格沃茨学生，却被学校从历史中抹去，请求新生帮他找回名字。故事的核心悬念是：埃利奥特究竟是被学校牺牲的受害者，还是被封印在钟里的危险存在？

本故事不绑定原作具体年代和原作角色。教授统一使用职务称呼，避免与服务器时间线冲突。

### 7.2 核心角色

| 角色 | 表面身份 | 真相与功能 |
|------|----------|------------|
| 埃利奥特 | 被校史抹去的少年 | 真正的埃利奥特一年级时已经死亡；眼前的少年是城堡吸收众人思念后形成的“记忆回声” |
| 档案管理员 | 阻止学生查旧档案的教授 | 知道封印的一部分真相，代表秩序与安全，但并非完全诚实 |
| 米蕾 | 第一个忘记自己姓名的NPC新生 | 把抽象威胁变成玩家需要保护的具体同伴 |
| 无名画像 | 回廊入口处的空画框 | 保存真正埃利奥特留下的最后一段记忆，也是最终真相的见证者 |

### 7.3 全服状态变量

阶段胜出选项除了生成结果文本，还会改变以下状态。最终结局由累计状态决定，不能只由最后一次投票决定。

| 状态 | 初始值 | 含义 |
|------|--------|------|
| `professor_trust` | 0 | 教授是否愿意公开档案并协助学生 |
| `evidence` | 0 | 全校找到的有效证据数量 |
| `echo_power` | 0 | 记忆回声脱离封印的能力 |
| `public_truth` | 0 | 学生是否愿意让被掩盖的历史公开 |
| `seal_integrity` | 4 | 四件学院封印物的完整程度 |

建议将每阶段的状态变更写进选项配置：

```json
{"key": "A", "text": "叫醒级长", "effects": {"professor_trust": 1}}
```

### 7.4 第一幕：不存在的钟声（阶段1—5）

#### 阶段1：午夜之后

宵禁后，玩家听见钟楼敲出第十三声。寝室里的其他人毫无反应，走廊尽头却出现一串湿脚印。

- A「叫醒级长」：`professor_trust +1`，安全地获得“钟声并非人人能听见”的线索。
- B「跟随脚印」：`evidence +1`，看见脚印在一面实心墙前消失。
- C「记下时间，等待下一次」：`evidence +1`，发现钟声比真正的午夜晚十三分钟。

#### 阶段2：被抹去的画像

墙前原本挂着一幅画像，现在只剩空白画布。其他学生坚持那里从来没有画像，只有玩家还记得画中曾有一个男孩。

- A「询问附近的画像」：获得“它不该再醒来”的警告，`professor_trust +1`。
- B「拆下画框检查背面」：找到刻痕“E. W.”，`evidence +1`。
- C「把画像临摹下来」：保留一份不会随记忆消失的证据，`public_truth +1`。

#### 阶段3：楼梯尽头的门

第十三声再次响起，一道平时不存在的门出现在移动楼梯尽头。

- A「立刻进去」：进入无名回廊，`echo_power +1`。
- B「留下标记并返回找人」：`professor_trust +1`。
- C「先用魔法测试门」：确认门由记忆而非实体构成，`evidence +1`。

#### 阶段4：没有名字的课桌

回廊中有一张刻满四大学院姓名的旧课桌，中央的名字被反复刮去。触碰桌面时，倒影中的少年第一次开口：“你还记得我吗？”

- A「问他是谁」：少年自称埃利奥特，`echo_power +1`。
- B「恢复被刮去的刻痕」：得到残缺姓氏，`evidence +1`。
- C「不回答，先检查周围」：找到四种颜色的封印蜡，`evidence +1`。

#### 阶段5：第一份共同证词

全校交换线索。多数选择决定第一幕公开给所有人的证据，另外两项成为以后可补获的隐藏线索。

- A「把事情报告教授」：回廊被封闭，`professor_trust +2`、`seal_integrity +1`。
- B「接受埃利奥特的请求」：得到半张学生证，`echo_power +2`、`evidence +1`。
- C「成立学生调查小组」：保留全部现有记录，`public_truth +2`、`evidence +1`。

### 7.5 第二幕：被删除的学生（阶段6—10）

#### 阶段6：倒影中的请求

埃利奥特请求玩家找回完整姓名，并承诺让所有被遗忘的东西回来。

- A「答应帮助」：`echo_power +2`。
- B「要求他先证明身份」：得到一段旧校歌记忆，`evidence +1`。
- C「拒绝并通知教授」：`professor_trust +1`、`seal_integrity +1`。

#### 阶段7：四院各执一词

四大学院保存的旧记录互相矛盾。玩家只会先看到本学院版本，鼓励不同学院交换情报。

- 格兰芬多记录称埃利奥特为救人闯入钟塔。
- 拉文克劳记录称他主动研究危险的记忆魔法。
- 赫奇帕奇记录称他在事故前长期受到孤立。
- 斯莱特林记录称校方要求四院共同销毁档案。

选择“交换记录”增加 `public_truth`，选择“独自比对”增加 `evidence`，选择“交给教授”增加 `professor_trust`。

#### 阶段8：被遗忘的一天

玩家醒来后失去了整整一天的记忆，口袋里却有自己写的纸条：“不要让他敲第二次钟。”

- A「相信纸条」：`seal_integrity +1`。
- B「相信埃利奥特的解释」：`echo_power +2`。
- C「重走昨天的路线」：恢复自己藏起的证据，`evidence +2`。

#### 阶段9：教授的禁令

档案管理员封闭回廊，却拒绝解释学校为何删去一名学生。

- A「遵守禁令并私下交涉」：`professor_trust +2`。
- B「夜间潜入档案室」：`evidence +2`、`professor_trust -1`。
- C「公开要求学校说明」：`public_truth +2`、`professor_trust -1`。

#### 阶段10：死去又长大的学生

众人终于拼出档案：埃利奥特一年级入学宴当晚已经死亡，记录里却还有一个“埃利奥特”继续在校生活了七年。

- A「追查死亡记录」：`evidence +2`。
- B「追查后七年的记录」：`echo_power +1`、`evidence +1`。
- C「询问城堡里的幽灵」：`public_truth +1`、`professor_trust +1`。

### 7.6 第三幕：钟里的东西（阶段11—15）

#### 阶段11：七年的借名者

真正的埃利奥特死于意外。朋友们不肯接受他的死亡，强烈的思念被城堡魔法吸收，形成了一个以为自己就是埃利奥特的记忆回声。

- A「承认回声也是生命」：`echo_power +1`、`public_truth +1`。
- B「认定它只是魔法残留」：`seal_integrity +1`。
- C「暂不判断，继续取证」：`evidence +2`。

#### 阶段12：借来的记忆

回声承认自己一直偷取学生记忆来填补人格，却声称那些记忆最后都会归还。

- A「要求它立即归还」：若 `evidence >= 8`，成功归还一部分并使 `echo_power -1`；否则失败。
- B「允许它暂时保留」：`echo_power +2`。
- C「提出用自愿分享的记忆代替」：`public_truth +1`，开启和平结局必要条件 `voluntary_memory = true`。

#### 阶段13：忘记名字的人

NPC新生米蕾忘记了自己的姓名、学院和朋友。回声承诺，只要学校给它一个正式名字，它就会归还米蕾的记忆。

- A「接受交易」：米蕾暂时恢复，`echo_power +2`。
- B「拒绝交易并保护米蕾」：`seal_integrity +1`、`professor_trust +1`。
- C「假意接受并设置陷阱」：若 `evidence >= 9` 则 `echo_power -1`，否则 `seal_integrity -1`。

#### 阶段14：四件封印物

四院分别保管钟锤、齿轮、铭牌和摆锤。投票决定全校集中保护哪一件，其他封印物受到攻击。

- A「集中防守钟塔」：`seal_integrity +1`。
- B「用假封印物诱敌」：高证据时 `echo_power -1`，低证据时 `seal_integrity -1`。
- C「主动开启一条缝与回声谈判」：`echo_power +1`，开启和平结局必要条件 `heard_echo = true`。

#### 阶段15：钟塔失守

回声利用玩家最害怕失去的记忆制造幻象。阶段文本根据个人此前选择变化：常向教授求助者看见“你永远不能独立”；常独自调查者看见“没人会相信你”。

- A「呼唤同伴确认彼此记忆」：`public_truth +2`。
- B「依靠教授布置的锚定咒」：`professor_trust +2`、`seal_integrity +1`。
- C「独自进入钟内寻找核心」：`evidence +2`、`echo_power +1`。

### 7.7 第四幕：谁有资格被记住（阶段16—20）

#### 阶段16：学校隐瞒的理由

档案管理员公开真相：当年的教授删除记录不是为了惩罚埃利奥特，而是防止回声获得完整身份后离开钟塔。但学校也借“安全”掩盖了自己的失职。

- A「接受解释，优先解决危机」：`professor_trust +2`。
- B「要求危机后公开全部档案」：`public_truth +2`。
- C「不再相信学校」：`public_truth +1`、`professor_trust -2`。

#### 阶段17：真正的最后愿望

无名画像播放真正埃利奥特留下的记忆：“别让任何东西替我活下去；但如果它已经会害怕，也别因我杀死它。”

- A「记住真正的埃利奥特」：`evidence +1`、`public_truth +1`。
- B「把选择权交给回声」：`echo_power +2`。
- C「让所有受害者共同决定」：`public_truth +2`。

#### 阶段18：全校审判

这是最终立场投票，但只形成“结局倾向”，不能覆盖前18阶段积累的状态。

- A「摧毁回声」：倾向 `destroy`。
- B「重新封印」：倾向 `seal`。
- C「给它一个新名字」：倾向 `rebirth`。

#### 阶段19：必须支付的代价

根据阶段18的多数意见显示不同任务：

- 摧毁路线：选择保留谁的记忆；参与者会失去关于回廊的一部分记忆。
- 封印路线：选择由画像、幽灵或自愿者成为守钟人。
- 新生路线：全校从候选名称中投票，并决定是否公开学校旧案。

若路线不满足必要状态，行动会失败并自动转入最可行的结局。例如新生路线要求 `evidence >= 10`、`public_truth >= 8`、`voluntary_memory = true`、`heard_echo = true`。

#### 阶段20：第十三声之后

结算全服世界结局、个人身份标签和二年级继承变量。午夜钟声再次响起；这一次，它究竟停在十二声、传来沉闷的第十三声，还是响起一个从未听过的新音色，由全校一整年的选择决定。

### 7.8 全服结局

#### 结局A：无声的黎明（`destroy`）

回声被摧毁，第十三声永久消失。学校恢复安全，但所有参与者都遗失了一部分事件记忆。空白画像下多出一句只有“记忆见证者”能看见的话：“谢谢你记得我。”

#### 结局B：守钟人（`seal`）

回声被再次封印，一名由全校选择的守钟人留在钟塔。二年级仍可在特定夜晚进入无名回廊，但封印会随时间减弱。

#### 结局C：无名者的新生（`rebirth`）

回声放弃冒用埃利奥特的身份，以全校赋予的新名字成为独立的魔法生命，并归还偷走的记忆。学校必须承认自己掩盖过历史。该结局最温暖，但给二年级留下“归还的记忆是否完整”的风险。

### 7.9 个人身份标签

个人标签由玩家自己的选择累计，与全服结局并存。一名玩家最多获得一个主标签和一个隐藏标签。

| 标签 | 判定倾向 | 二年级影响 |
|------|----------|------------|
| 教授的眼睛 | 多次报告异常、保护封印 | 教授信任事件与档案室权限 |
| 回廊探索者 | 多次独立调查并找到证据 | 可发现隐藏通道和额外线索 |
| 秘密保管人 | 选择隐瞒，但从未出卖同伴 | NPC会托付私人秘密 |
| 记忆见证者 | 保存记录并支持公开历史 | 能识别被篡改的文字或记忆 |
| 回声之友 | 始终把回声视为生命 | 无论全服结局为何，都能听见微弱钟声 |
| 冷静裁决者 | 先取证再表态，较少极端选择 | 最终判定时获得额外真相文本 |
| 敲钟者 | 曾主动增强回声或解除封印 | 获得强力但有风险的记忆魔法事件 |
| 守钟人候选 | 支持封印且愿意承担代价 | 解锁钟塔夜巡支线 |

### 7.10 配套短故事

- 《厨房里多出的一套餐具》（5阶段）：每晚自动出现一套餐具，对应一名被钟声遗忘的学生；奖励厨房声望并补充米蕾线索。
- 《不会说谎的幽灵》（5阶段）：幽灵只能复述别人说过的话，玩家要从互相矛盾的证词中找到旧事故真相；奖励 `evidence` 补偿机会。

---

## 8. 二年级继承机制

```python
def init_year2_context(uid: str) -> dict:
    """二年级初始化时读取一年级故事结局"""
    endings = get_all_story_endings_for_student(uid)
    
    return {
        "year1_world_ending": get_world_ending("year1_thirteenth_bell"),
        "year1_personal_tags": get_personal_tags(uid, "year1_thirteenth_bell"),
        "year1_key_choices": get_key_choices(uid, "year1_thirteenth_bell"),
        "unlock_contexts": [
            # destroy：记忆缺口与空白画像事件
            # seal：钟塔夜巡与封印松动事件
            # rebirth：回声NPC与错误记忆事件
            # 再根据个人标签开放教授、探索、见证者等专属选项
        ]
    }
```

---

## 9. 实现清单

- [ ] 数据库表创建
- [ ] 故事配置加载系统
- [ ] 每日触发定时任务
- [ ] 选择处理和统计逻辑
- [ ] 阶段推进判断和执行
- [ ] QQ命令接口（/阶段任务、/选择、/故事进度）
- [ ] 网页展示（故事看板、个人结局详情）
- [ ] 推送通知系统
- [ ] 二年级继承逻辑
- [ ] 测试脚本（模拟选择分布、推进时间等）

---

## 10. 配置参考值

| 参数 | 值 | 说明 |
|------|-----|------|
| 日触发概率 | 20% | 每个学生每天有1/5的概率收到任务 |
| 人数阈值 | max(一年级人数×30%, 10) | 最少10人即可推进 |
| 自动推进天数 | 3-5 | 若人数不足，5天自动推进 |
| 参与奖励 | 10加隆 | 每次选择奖励 |
| 长故事阶段 | 20+ | 跨整学年 |
| 短故事阶段 | 5 | 1周内完成 |
