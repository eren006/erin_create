"""对角巷商店目录：扫帚/零食/宠物/装备四类。

扫帚和装备是"计划性大额消费"，常驻不刷新，方便玩家攒钱奔着目标买。
宠物和零食是"看到喜欢的就买"的轻量消费，池子铺得比较大，每次只随机开放一部分，
每3小时刷新一轮（见 shop.py 的轮换逻辑），逛对角巷才会有惊喜感。

扫帚的 effect 是魁地奇四维属性加成；零食/饮料的 effect 是回复体力值；
宠物纯图鉴收藏，没有机制效果；装备先占位，等决斗系统做出来后再给 effect 赋真正含义。
"""

# (item_key, name, category, price, description, effect)
ITEMS: list[tuple[str, str, str, int, str, dict]] = [
    # ── 扫帚：不同档位側重不同属性，不是单纯"越贵越强"的线性替代，常驻不刷新 ──
    (
        "broom_cleansweep11",
        "横扫五千星",
        "扫帚",
        60,
        "入门级，胜在便宜，均衡但不突出。",
        {"speed": 1, "collision": 1, "stamina": 1, "accuracy": 1, "durability": 8},
    ),
    (
        "broom_comet260",
        "彗星260",
        "扫帚",
        150,
        "偏速度型，找球手/追球手抢跑位置的首选。",
        {"speed": 3, "collision": 1, "stamina": 0, "accuracy": 1, "durability": 10},
    ),
    (
        "broom_nimbus2000",
        "光轮2000",
        "扫帚",
        300,
        "操控精准，偏准头，追球手的进阶之选。",
        {"speed": 2, "collision": 1, "stamina": 1, "accuracy": 3, "durability": 12},
    ),
    (
        "broom_firebolt",
        "火弩箭",
        "扫帚",
        600,
        "顶级赛用扫帚，四项全面拉满，贵得有道理。",
        {"speed": 3, "collision": 2, "stamina": 2, "accuracy": 3, "durability": 15},
    ),
    # ── 装备：决斗用品，先占位，等决斗系统做出来再接效果，常驻不刷新 ──
    ("gear_dueling_gloves", "决斗手套", "装备", 40, "决斗俱乐部的基本装备（效果等决斗系统上线后生效）。", {}),
    # ── 零食/饮料：池子铺大一点，每3小时随机开放一部分 ──
    ("snack_pumpkin_pasty", "南瓜饼", "零食", 5, "朴实无华，饱腹又回体力。", {"restore_stamina": 2}),
    ("snack_chocolate_frog", "巧克力蛙", "零食", 8, "会跳一下的巧克力，送礼体面。", {"restore_stamina": 3}),
    ("snack_honeydukes_assortment", "蜜蜂公爵什锦礼盒", "零食", 15, "送礼首选，效果也最好。", {"restore_stamina": 5}),
    ("snack_fizzing_whizzbee", "酸嘶嘶糖", "零食", 7, "吃完会飘那么几秒。", {"restore_stamina": 3}),
    ("snack_liquorice_wand", "甘草魔杖糖", "零食", 6, "长得像魔杖的糖，学生间的经典款。", {"restore_stamina": 2}),
    ("drink_pumpkin_fizz", "南瓜汽水", "零食", 6, "带气泡的南瓜汁，比原味更提神。", {"restore_stamina": 2}),
    ("drink_butterbeer", "黄油啤酒", "零食", 10, "霍格莫德的招牌饮料，暖乎乎的。", {"restore_stamina": 4}),
    ("drink_iced_pumpkin_juice", "冰镇南瓜汁", "零食", 8, "夏天/图书馆突击复习的续命神器。", {"restore_stamina": 3}),
    ("drink_pepperup_fizz", "提神冒烟饮料", "零食", 12, "喝完耳朵会冒一会儿烟，但真的提神。", {"restore_stamina": 5}),
    ("drink_firewhisky_cocoa", "火焰威士忌味热可可", "零食", 14, "挂名而已，不含酒精，暖到发烫。", {"restore_stamina": 5}),
    # ── 宠物：纯图鉴收藏，不加数值，池子铺大一点，每3小时随机开放一部分 ──
    ("pet_cat_orange", "橘猫", "宠物", 90, "传说中的猫界顶流，胖乎乎的，看着就没脑子。", {}),
    ("pet_cat_tabby", "狸花猫", "宠物", 60, "土生土长，皮实好养。", {}),
    ("pet_cat_british_shorthair", "英国短毛猫", "宠物", 110, "圆脸圆眼睛，性格温顺。", {}),
    ("pet_cat_ragdoll", "布偶猫", "宠物", 150, "毛长得很夸张，抱起来跟布偶一样。", {}),
    ("pet_cat_black", "黑猫", "宠物", 80, "巫师圈的传统审美，低调神秘。", {}),
    ("pet_cat_calico", "三花猫", "宠物", 100, "花色复杂，据说都是母的。", {}),
    ("pet_cat_siamese", "暹罗猫", "宠物", 95, "话多，叫声像婴儿哭。", {}),
    ("pet_cat_sphynx", "无毛猫", "宠物", 130, "长得有点吓人，但很粘人。", {}),
    ("pet_cat_scottish_fold", "苏格兰折耳猫", "宠物", 140, "耳朵折下来，表情常年很崩溃。", {}),
    ("pet_cat_maine_coon", "缅因猫", "宠物", 160, "体型巨大，猫中巨人。", {}),
    ("pet_owl_tawny", "灰林鸮", "宠物", 100, "最常见的信使猫头鹰，靠谱耐用。", {}),
    ("pet_owl_snowy", "雪鸮", "宠物", 200, "全身雪白，特别拉风，价格也拉风。", {}),
    ("pet_owl_barn", "仓鸮", "宠物", 120, "脸盘像心形，送信速度快。", {}),
    ("pet_owl_long_eared", "长耳鸮", "宠物", 110, "头顶两撮毛，看着常年很生气。", {}),
    ("pet_owl_little", "纵纹腹小鸮", "宠物", 90, "体型迷你，飞得却不慢。", {}),
    ("pet_owl_eagle", "雕鸮", "宠物", 220, "体型最大，气场十足，站你肩上会压肩。", {}),
    ("pet_owl_barred", "横斑腹小鸮", "宠物", 85, "圆滚滚，眼神常年很呆滞。", {}),
    ("pet_owl_eagle_rare", "猛鸮", "宠物", 250, "很少见，据说很难买到，纯纯炫耀款。", {}),
    ("pet_toad", "蟾蜍", "宠物", 30, "不知道为什么会有人选它，但总有人选。", {}),
    ("pet_rat", "老鼠", "宠物", 25, "便宜大碗，就是有点上不了台面。", {}),
    # ── 礼物：送人涨好感度用，affection是送出后对方对你的好感涨幅。
    #    stock是全服共享库存（不是每人一份），卖完要等下一轮刷新，越贵的越稀缺越难抢 ──
    ("gift_quill", "孔雀羽毛笔", "礼物", 10, "写作业用得上，实用主义的小心意。", {"affection": 3, "stock": 30}),
    ("gift_ink_colour_change", "变色墨水", "礼物", 14, "写下的字会随心情变颜色，上课偷偷玩的好东西。", {"affection": 4, "stock": 25}),
    ("gift_chocolate_frog_card", "稀有巫师卡", "礼物", 20, "巧克力蛙里最难抽到的那张，收集党会尖叫。", {"affection": 6, "stock": 20}),
    ("gift_sneakoscope", "窥镜", "礼物", 30, "身边有人使坏就会转圈发光，实用又贴心。", {"affection": 9, "stock": 15}),
    ("gift_quidditch_scarf", "魁地奇围巾", "礼物", 35, "织着学院颜色，看球赛时围着最合适。", {"affection": 10, "stock": 15}),
    ("gift_music_box", "会唱歌的八音盒", "礼物", 50, "打开会哼一段跑调的小曲，很难不笑。", {"affection": 15, "stock": 10}),
    ("gift_dress_robes", "正式长袍", "礼物", 70, "参加舞会穿的那种，暗示意味很明显。", {"affection": 20, "stock": 8}),
    ("gift_silver_locket", "银质怀表挂坠", "礼物", 90, "打开来能放一张会动的照片。", {"affection": 25, "stock": 6}),
    ("gift_spellbook_rare", "绝版魔咒书", "礼物", 110, "书店里再也找不到第二本，懂的人会很懂。", {"affection": 30, "stock": 5}),
    ("gift_enchanted_rose", "永不凋谢的玫瑰", "礼物", 150, "施了魔法的玫瑰，摆多久都不会谢。", {"affection": 40, "stock": 4}),
    ("gift_snowglobe_hogwarts", "霍格沃茨水晶球", "礼物", 180, "摇一摇，城堡上空就开始下雪。", {"affection": 48, "stock": 3}),
    ("gift_star_pendant", "星空吊坠", "礼物", 250, "坠子里装着一小片会动的星空，贵得很有道理。", {"affection": 60, "stock": 2}),
    # ── 恶作剧：买来整别人的，命中后对方的名字后面会跟着一条状态，持续几小时，常驻不刷新 ──
    (
        "prank_flame_head",
        "火焰头药水",
        "恶作剧",
        20,
        "对方接下来几小时顶着一头夸张的火焰，走到哪儿都显眼。",
        {"status_label": "带着一头夸张的火焰头", "duration_hours": 3},
    ),
    (
        "prank_long_ears",
        "长耳朵软糖",
        "恶作剧",
        15,
        "对方会长出一对兔子似的长耳朵，甩都甩不掉。",
        {"status_label": "长着一对兔子长耳朵", "duration_hours": 2},
    ),
    (
        "prank_croaking_curse",
        "呱呱蛙音粉",
        "恶作剧",
        18,
        "对方接下来说话会带着蛙叫声，自己听着都想笑。",
        {"status_label": "说话带着呱呱蛙音", "duration_hours": 2},
    ),
    # ── 烹饪材料：key 必须跟 kitchen.py 里配方的 ingredients key 完全一致，否则买了也没法做菜 ──
    ("mat_egg", "鸡蛋", "烹饪材料", 8, "新鲜鸡蛋，烹饪的基础材料。", {}),
    ("mat_butter", "黄油", "烹饪材料", 10, "精制黄油，用处广泛。", {}),
    ("mat_flour", "面粉", "烹饪材料", 6, "面粉，可以做不少面食。", {}),
    ("mat_sugar", "糖", "烹饪材料", 7, "白砂糖，烘焙必备。", {}),
    ("mat_milk", "牛奶", "烹饪材料", 9, "新鲜牛奶，营养又好喝。", {}),
    ("mat_honey", "蜂蜜", "烹饪材料", 12, "优质蜂蜜，不仅好吃还有药用。", {}),
    ("mat_salt", "盐", "烹饪材料", 3, "食盐，再便宜不过。", {}),
    ("mat_chocolate", "巧克力", "烹饪材料", 15, "上等可可巧克力，用来烘焙很不错。", {}),
    ("mat_cream", "奶油", "烹饪材料", 11, "淡奶油，甜点的灵魂。", {}),
    ("mat_herbs", "香草", "烹饪材料", 5, "新鲜香草，做菜时提味。", {}),
    # ── 布料：马金夫人长袍店做衣服用的原料，常驻不轮换，价格压得低，
    # 保证成衣卖出去稳赚——见 plugins/hp_school/tailor.py ──
    ("fabric_cotton", "棉布", "布料", 4, "最基础的布料，哪里都用得上。", {}),
    ("fabric_linen", "亚麻布", "布料", 5, "透气耐用，夏装常用。", {}),
    ("fabric_wool", "羊毛呢", "布料", 6, "厚实保暖，冬装首选。", {}),
    ("fabric_hemp", "麻布", "布料", 3, "最便宜的布料，粗糙但结实。", {}),
    ("fabric_corduroy", "灯芯绒", "布料", 6, "一道道纹理，摸起来很有质感。", {}),
    ("fabric_chiffon", "雪纺", "布料", 7, "轻薄飘逸，做长裙很好看。", {}),
    ("fabric_silk", "丝绸", "布料", 10, "顺滑有光泽，价格也不便宜。", {}),
    ("fabric_satin", "缎面", "布料", 9, "光泽感强，礼服常用。", {}),
    ("fabric_velvet", "天鹅绒", "布料", 12, "厚实又有光泽，斗篷的经典选择。", {}),
    ("fabric_lace", "蕾丝", "布料", 8, "镂空花纹，做点缀最合适。", {}),
    ("fabric_leather", "皮革", "布料", 11, "耐磨结实，适合做外套。", {}),
    ("fabric_mink_fur", "貂皮", "布料", 18, "又软又暖，看着就贵气。", {}),
    ("fabric_gold_thread", "金线", "布料", 15, "绣花点缀用，一点点就很显眼。", {}),
    ("fabric_silver_thread", "银线", "布料", 13, "比金线低调，同样华丽。", {}),
    ("fabric_pearl_button", "珍珠纽扣", "布料", 10, "小小一颗，画龙点睛。", {}),
    ("fabric_feather_trim", "羽毛饰片", "布料", 9, "镶在领口或袖口，添几分灵动。", {}),
    ("fabric_enchanted_thread", "魔法丝线", "布料", 16, "会自己微微发光的丝线。", {}),
    ("fabric_warm_fleece", "保暖绒毛", "布料", 7, "蓬松柔软，摸起来很舒服。", {}),
    ("fabric_waxed_cloth", "防水蜡布", "布料", 8, "刷过蜡的布料，下雨天不怕湿。", {}),
    ("fabric_stain_resist", "抗污魔法布", "布料", 12, "施过咒的布料，弄脏了轻轻一擦就干净。", {}),
    ("fabric_dragon_hide", "龙皮革", "布料", 25, "传说中最耐用的皮革，价格惊人。", {}),
    ("fabric_phoenix_thread", "凤凰羽线", "布料", 28, "带着一点点温热的触感，据说很难买到。", {}),
    ("fabric_unicorn_thread", "独角兽鬃毛线", "布料", 26, "在光下会泛出淡淡银光。", {}),
    ("fabric_shifting_silk", "幻形丝绸", "布料", 22, "颜色会随心情微微变化的神奇丝绸。", {}),
    ("fabric_spider_silk", "蜘蛛丝", "布料", 20, "细密坚韧，来源最好别多问。", {}),
    # ── 纪念品：只能靠活动获得，不放进CATEGORIES里，对角巷逛不到；
    # effect.unpurchasable=True 双重保险，就算有人知道确切名字也买不了 ──
    (
        "trophy_gnome_king", "地精之王的银质奖杯", "纪念品", 0,
        "二年级抓地精比赛冠军才有的荣誉奖杯，对角巷买不到。", {"unpurchasable": True},
    ),
    (
        "trophy_creature_keeper", "海格亲笔签名的驯兽手册", "纪念品", 0,
        "三年级照料神奇生物活动冠军才有的纪念品，对角巷买不到。", {"unpurchasable": True},
    ),
    # ── 限定宠物：跟纪念品一样不放进CATEGORIES里，对角巷逛不到，
    # 只能靠"照料神奇生物"活动小概率偶遇；category单独用"限定宠物"
    # 而不是"宠物"，这样才不会被拿去正常商店货架轮换展示 ──
    (
        "pet_niffler", "尼福勒", "限定宠物", 0,
        "爱亮晶晶的小东西，藏钱藏得比谁都溜。三年级照料神奇生物活动限定，对角巷买不到。",
        {"unpurchasable": True},
    ),
    (
        "pet_unicorn_foal", "独角兽驹", "限定宠物", 0,
        "浑身泛着银光的幼崽，只肯亲近心地纯良的人。三年级照料神奇生物活动限定，对角巷买不到。",
        {"unpurchasable": True},
    ),
    (
        "pet_bowtruckle", "护树罗锅", "限定宠物", 0,
        "瘦得像树枝一样的小家伙，脾气有点倔。三年级照料神奇生物活动限定，对角巷买不到。",
        {"unpurchasable": True},
    ),
]

ITEMS_BY_KEY = {item[0]: item for item in ITEMS}
ITEMS_BY_NAME = {item[1]: item for item in ITEMS}
CATEGORIES = ("扫帚", "零食", "宠物", "装备", "礼物", "恶作剧", "烹饪材料", "布料")
ROTATING_CATEGORIES = ("零食", "宠物")  # 这两类每3小时随机开放一部分，其余常驻


def find(name_or_key: str) -> tuple[str, str, str, int, str, dict] | None:
    return ITEMS_BY_KEY.get(name_or_key) or ITEMS_BY_NAME.get(name_or_key)


def list_by_category(category: str) -> list[tuple[str, str, str, int, str, dict]]:
    return [item for item in ITEMS if item[2] == category]
