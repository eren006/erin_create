"""厨房养成系统：烹饪食物、收集配方、积累经验。"""

from __future__ import annotations

import json
import random
import re

from plugins.hp_core import storage as core_storage
from plugins.hp_core.storage import get_conn

from . import storage

COOK_STAMINA_COST = 8  # 每次烹饪消耗8点厨房活力
DAILY_LIMIT = 5  # 每天最多5次
STAMINA_MAX = 40
STAMINA_REGEN_INTERVAL = 25 * 60  # 25分钟恢复8点活力
STAMINA_REGEN_AMOUNT = 8

DISASTERS = ("黑烟滚滚", "食物焦黑一片", "汤汁溅得到处都是", "莫名其妙变成了糊状")

# 烹饪材料清单（通常来自禁林采集或商店）
KITCHEN_MATERIALS = {
    "mat_egg": ("鸡蛋", "基础材料"),
    "mat_butter": ("黄油", "基础材料"),
    "mat_salt": ("盐", "基础材料"),
    "mat_bread": ("面包", "基础材料"),
    "mat_milk": ("牛奶", "基础材料"),
    "mat_honey": ("蜂蜜", "基础材料"),
    "mat_flour": ("面粉", "基础材料"),
    "mat_sugar": ("糖", "基础材料"),
    "mat_cheese": ("芝士", "进阶材料"),
    "mat_chocolate": ("巧克力", "进阶材料"),
    "mat_cream": ("奶油", "进阶材料"),
    "mat_chicken": ("鸡肉", "食材"),
    "mat_fish": ("鱼肉", "食材"),
    "mat_herbs": ("香草", "调料"),
    "mat_vegetable": ("蔬菜", "食材"),
    "mat_water": ("水", "基础材料"),
    "mat_tomato": ("番茄", "食材"),
    "mat_pasta": ("意大利面", "食材"),
    "mat_potato": ("土豆", "食材"),
    "mat_meat": ("肉", "食材"),
    "mat_lettuce": ("莴苣", "蔬菜"),
    "mat_bun": ("面包胚", "食材"),
    "mat_oats": ("燕麦", "基础材料"),
    "mat_mushroom": ("蘑菇", "食材"),
    "mat_beans": ("豆子", "食材"),
    "mat_clam": ("蛤蜊", "食材"),
    "mat_lentil": ("扁豆", "食材"),
    "mat_apple": ("苹果", "水果"),
    "mat_mascarpone": ("马斯卡彭芝士", "进阶材料"),
    "mat_coffee": ("咖啡", "饮料"),
    "mat_cocoa": ("可可", "饮料"),
    "mat_cream_cheese": ("奶油芝士", "进阶材料"),
    "mat_almond_flour": ("杏仁粉", "进阶材料"),
    "mat_powdered_sugar": ("糖粉", "进阶材料"),
    "mat_food_color": ("食用色素", "进阶材料"),
    "mat_cinnamon": ("肉桂", "调料"),
    "mat_oil": ("油", "基础材料"),
    "mat_lemon": ("柠檬", "水果"),
    "mat_beef": ("牛肉", "食材"),
    "mat_carrot": ("胡萝卜", "蔬菜"),
    "mat_curry": ("咖喱", "调料"),
    "mat_rice": ("米", "基础材料"),
    "mat_bacon": ("培根", "食材"),
    "mat_lamb": ("羊肉", "食材"),
    "mat_rosemary": ("迷迭香", "香草"),
    "mat_garlic": ("大蒜", "调料"),
    "mat_nuts": ("坚果", "食材"),
    "mat_fruit": ("水果", "食材"),
    "mat_wine": ("葡萄酒", "饮料"),
    "mat_spices": ("香料", "调料"),
    "mat_yogurt": ("酸奶", "进阶材料"),
    "mat_ginger": ("生姜", "调料"),
    "mat_chamomile": ("洋甘菊", "草药"),
    "mat_star_anise": ("八角", "调料"),
    "mat_lavender": ("薰衣草", "草药"),
    "mat_corn": ("玉米", "食材"),
    "mat_butterbeer_base": ("黄油啤酒基", "特殊材料"),
    "mat_rice_flour": ("米粉", "基础材料"),
    "mat_filling": ("馅料", "进阶材料"),
    "mat_phoenix_feather": ("凤凰羽毛", "魔法材料"),
    "mat_dragon_scale": ("龙鳞", "魔法材料"),
    "mat_moonstone": ("月光石", "魔法材料"),
    "mat_starfruit": ("星果", "魔法材料"),
    "mat_basilisk_fang": ("蛇怪毒牙", "魔法材料"),
    "mat_moonflower": ("月光花", "魔法材料"),
    "mat_pearl": ("珍珠", "魔法材料"),
    "mat_seaweed": ("海草", "魔法材料"),
    "mat_spring_water": ("泉水", "魔法材料"),
    "mat_unicorn_tears": ("独角兽泪", "魔法材料"),
    "mat_starlight": ("星光", "魔法材料"),
    "mat_golden_egg": ("黄金蛋", "魔法材料"),
    "mat_dragon_blood": ("龙血", "魔法材料"),
    "mat_fire_pepper": ("火辣椒", "魔法材料"),
    "mat_unicorn_hair": ("独角兽毛", "魔法材料"),
    "mat_hot_pepper": ("辣椒", "调料"),
}

# 配方库：120+ 食物配方
# 分类：breakfast(早餐)、main(主食)、soup(汤)、dessert(甜点)、magic(魔法美食)、beverage(饮品)、snack(点心)

RECIPES = {
    # === 早餐（breakfast）===
    "scrambled_eggs": {
        "name": "炒鸡蛋", "category": "breakfast", "grade": 1, "exp": 8,
        "ingredients": {"mat_egg": 2, "mat_butter": 1, "mat_salt": 1},
        "effect": "恢复5点厨房活力；下次课堂表现+1",
        "steps": (
            ("鸡蛋打入碗中。", ("直接倒入", "分离蛋白", "打散混合"), 2),
            ("黄油在平底锅里融化。", ("立刻倒入蛋液", "等黄油变棕色", "关火再加"), 0),
            ("鸡蛋逐渐凝固。", ("炒至完全干身", "保留奶油质感", "立刻盛出"), 1),
        ),
    },
    "toast": {
        "name": "吐司", "category": "breakfast", "grade": 1, "exp": 6,
        "ingredients": {"mat_bread": 1, "mat_butter": 1},
        "effect": "恢复4点厨房活力",
        "steps": (
            ("面包放入烤箱。", ("大火烤", "小火烤", "中火烤"), 2),
            ("面包开始变黄。", ("继续烤至焦黄", "立刻取出", "再烤一会"), 0),
            ("涂黄油。", ("趁热涂", "冷却后涂", "不涂"), 0),
        ),
    },
    "porridge": {
        "name": "麦片粥", "category": "breakfast", "grade": 1, "exp": 10,
        "ingredients": {"mat_oats": 1, "mat_milk": 2, "mat_honey": 1},
        "effect": "恢复6点厨房活力；下次禁林采集+1材料",
        "steps": (
            ("水烧开。", ("加牛奶", "加燕麦", "加蜂蜜"), 1),
            ("燕麦吸水膨胀。", ("小火慢煮", "继续大火", "立刻关火"), 0),
            ("加蜂蜜。", ("加很多", "加一点", "不加"), 1),
        ),
    },
    "pancakes": {
        "name": "松饼", "category": "breakfast", "grade": 2, "exp": 15,
        "ingredients": {"mat_flour": 2, "mat_egg": 2, "mat_milk": 1, "mat_honey": 1},
        "effect": "恢复7点厨房活力；心情+1",
        "steps": (
            ("面糊混合。", ("混至无颗粒", "保留一些颗粒", "使劲混"), 0),
            ("平底锅烤。", ("中火", "大火", "小火"), 0),
            ("涂蜂蜜。", ("趁热涂", "冷却后涂", "不涂"), 2),
        ),
    },
    "omelette": {
        "name": "煎蛋卷", "category": "breakfast", "grade": 2, "exp": 12,
        "ingredients": {"mat_egg": 3, "mat_butter": 1, "mat_cheese": 1},
        "effect": "恢复6点厨房活力；下次课堂表现+2",
        "steps": (
            ("黄油融化。", ("小火", "中火", "大火"), 1),
            ("倒入蛋液。", ("一次倒入", "分次倒入", "慢慢倒"), 0),
            ("加芝士。", ("趁热加", "半凝时加", "完全凝固后加"), 0),
        ),
    },
    "french_toast": {
        "name": "法式吐司", "category": "breakfast", "grade": 2, "exp": 11,
        "ingredients": {"mat_bread": 2, "mat_egg": 2, "mat_milk": 1, "mat_cinnamon": 1},
        "effect": "恢复7点厨房活力；心情+1",
        "steps": (
            ("鸡蛋液。", ("加肉桂粉", "不加", "加很多"), 0),
            ("浸面包。", ("快速浸", "充分浸", "轻轻浸"), 1),
            ("煎至。", ("金黄", "焦黄", "微黄"), 0),
        ),
    },
    "waffle": {
        "name": "华夫饼", "category": "breakfast", "grade": 2, "exp": 13,
        "ingredients": {"mat_flour": 2, "mat_egg": 2, "mat_butter": 1, "mat_honey": 1},
        "effect": "恢复6点厨房活力；禁林采集+1材料",
        "steps": (
            ("面糊浓度。", ("稀", "适中", "浓"), 1),
            ("烤盘温度。", ("高温", "中温", "低温"), 0),
            ("涂蜂蜜。", ("很多", "适量", "不涂"), 0),
        ),
    },
    "granola": {
        "name": "格兰诺拉麦片", "category": "breakfast", "grade": 3, "exp": 18,
        "ingredients": {"mat_oats": 2, "mat_honey": 1, "mat_nuts": 1, "mat_oil": 1},
        "effect": "恢复8点厨房活力；烹饪经验+10%",
        "steps": (
            ("烘焙温度。", ("150度", "180度", "120度"), 1),
            ("搅拌均匀。", ("充分搅", "轻轻搅", "不搅"), 0),
            ("冷却。", ("热时装瓶", "半温装瓶", "完全冷却"), 0),
        ),
    },

    # === 主食（main）===
    "roasted_chicken": {
        "name": "烤鸡", "category": "main", "grade": 3, "exp": 25,
        "ingredients": {"mat_chicken": 1, "mat_salt": 1, "mat_herbs": 1},
        "effect": "恢复8点厨房活力；学院杯加成+1",
        "steps": (
            ("鸡上撒盐和香草。", ("轻轻撒", "尽力撒", "不撒"), 0),
            ("放入烤箱。", ("200度", "150度", "250度"), 0),
            ("烤至金黄。", ("略微焦色", "完全金黄", "还很浅"), 1),
        ),
    },
    "pasta": {
        "name": "意大利面", "category": "main", "grade": 2, "exp": 20,
        "ingredients": {"mat_pasta": 1, "mat_tomato": 2, "mat_herbs": 1},
        "effect": "恢复6点厨房活力；魔药经验+5%",
        "steps": (
            ("水烧开。", ("加盐", "不加", "加糖"), 0),
            ("煮意面。", ("10分钟", "5分钟", "15分钟"), 0),
            ("混合酱汁。", ("大力搅拌", "轻轻混合", "不混"), 1),
        ),
    },
    "fish_n_chips": {
        "name": "炸鱼薯条", "category": "main", "grade": 3, "exp": 22,
        "ingredients": {"mat_fish": 1, "mat_potato": 2, "mat_salt": 1},
        "effect": "恢复7点厨房活力；禁林采集经验+5%",
        "steps": (
            ("鱼裹粉。", ("厚粉衣", "薄粉衣", "不裹"), 1),
            ("油炸。", ("热油", "温油", "冷油"), 0),
            ("撒盐。", ("很多盐", "少盐", "不撒"), 2),
        ),
    },
    "burger": {
        "name": "汉堡", "category": "main", "grade": 2, "exp": 18,
        "ingredients": {"mat_bun": 1, "mat_meat": 1, "mat_lettuce": 1, "mat_tomato": 1},
        "effect": "恢复6点厨房活力；体力恢复+2",
        "steps": (
            ("组合顺序。", ("面包-肉-菜", "肉-面包-菜", "菜-肉-面包"), 0),
            ("压紧。", ("用力压", "轻轻压", "不压"), 1),
            ("切成两半。", ("对角切", "竖着切", "不切"), 2),
        ),
    },
    "grilled_fish": {
        "name": "烤鱼", "category": "main", "grade": 3, "exp": 20,
        "ingredients": {"mat_fish": 2, "mat_lemon": 1, "mat_herbs": 1},
        "effect": "恢复8点厨房活力；下次禁林冒险+10HP",
        "steps": (
            ("腌制。", ("加盐", "加柠檬", "加香草"), 0),
            ("烤温度。", ("200度", "180度", "220度"), 1),
            ("烤时间。", ("15分钟", "20分钟", "10分钟"), 1),
        ),
    },
    "beef_stew": {
        "name": "炖牛肉", "category": "main", "grade": 3, "exp": 24,
        "ingredients": {"mat_beef": 2, "mat_potato": 2, "mat_carrot": 1, "mat_water": 3},
        "effect": "恢复10点厨房活力；下次课堂表现+1",
        "steps": (
            ("先煎肉。", ("大火煎", "小火", "不煎"), 0),
            ("加菜。", ("马上加", "半小时后", "一小时后"), 1),
            ("火候。", ("文火", "中火", "大火"), 0),
        ),
    },
    "chicken_curry": {
        "name": "咖喱鸡", "category": "main", "grade": 3, "exp": 22,
        "ingredients": {"mat_chicken": 1, "mat_curry": 1, "mat_cream": 1, "mat_rice": 2},
        "effect": "恢复8点厨房活力；学院杯加成+2",
        "steps": (
            ("爆香。", ("先炒香料", "先煎鸡", "同时加"), 0),
            ("加咖喱。", ("早加", "中途加", "最后加"), 1),
            ("加奶油。", ("很多", "少量", "不加"), 0),
        ),
    },
    "spaghetti_carbonara": {
        "name": "意大利奶油面", "category": "main", "grade": 3, "exp": 25,
        "ingredients": {"mat_pasta": 1, "mat_egg": 2, "mat_bacon": 1, "mat_cheese": 1},
        "effect": "恢复9点厨房活力；下次课堂表现+2",
        "steps": (
            ("熟度。", ("Al dente", "软", "很软"), 0),
            ("蛋液温度。", ("蛋黄", "全蛋", "蛋白"), 1),
            ("混合。", ("快速拌", "慢速拌", "不拌"), 0),
        ),
    },
    "roasted_vegetables": {
        "name": "烤蔬菜", "category": "main", "grade": 2, "exp": 10,
        "ingredients": {"mat_vegetable": 2, "mat_oil": 1, "mat_salt": 1},
        "effect": "恢复6点厨房活力；体力恢复+1",
        "steps": (
            ("切大小。", ("大块", "小块", "中块"), 1),
            ("油量。", ("很多油", "少油", "适量"), 1),
            ("烤温。", ("200度", "180度", "220度"), 0),
        ),
    },
    "lamb_chops": {
        "name": "羊排", "category": "main", "grade": 3, "exp": 23,
        "ingredients": {"mat_lamb": 2, "mat_rosemary": 1, "mat_garlic": 1},
        "effect": "恢复9点厨房活力；禁林采集+2材料",
        "steps": (
            ("腌料。", ("迷迭香先", "大蒜先", "同时"), 0),
            ("烤温度。", ("高温快烤", "中温", "低温慢烤"), 2),
            ("熟度。", ("三分熟", "五分熟", "全熟"), 1),
        ),
    },

    # === 汤类（soup）===
    "vegetable_soup": {
        "name": "蔬菜汤", "category": "soup", "grade": 1, "exp": 12,
        "ingredients": {"mat_vegetable": 2, "mat_water": 2, "mat_salt": 1},
        "effect": "恢复7点厨房活力；清除疲劳",
        "steps": (
            ("蔬菜切块。", ("大块", "小块", "碎末"), 0),
            ("水烧开。", ("加蔬菜", "等等再加", "不加"), 0),
            ("盐调味。", ("加多", "加少", "不加"), 1),
        ),
    },
    "pumpkin_soup": {
        "name": "南瓜汤", "category": "soup", "grade": 2, "exp": 16,
        "ingredients": {"mat_pumpkin": 2, "mat_cream": 1, "mat_salt": 1},
        "effect": "恢复8点厨房活力；心情+2",
        "steps": (
            ("南瓜煮软。", ("小火慢煮", "大火快煮", "微火"), 0),
            ("加奶油。", ("倒入", "滴入", "不加"), 1),
            ("搅拌。", ("混至顺滑", "保留颗粒", "不搅"), 0),
        ),
    },
    "bone_broth": {
        "name": "骨汤", "category": "soup", "grade": 3, "exp": 20,
        "ingredients": {"mat_bone": 2, "mat_water": 3, "mat_herbs": 1},
        "effect": "恢复10点厨房活力；下次禁林冒险+15HP",
        "steps": (
            ("骨头焯水。", ("热水焯", "冷水焯", "直接煮"), 1),
            ("小火炖。", ("2小时", "1小时", "3小时"), 0),
            ("过筛。", ("细筛", "粗筛", "不筛"), 1),
        ),
    },
    "mushroom_soup": {
        "name": "蘑菇汤", "category": "soup", "grade": 2, "exp": 14,
        "ingredients": {"mat_mushroom": 2, "mat_cream": 1, "mat_water": 2},
        "effect": "恢复7点厨房活力；魔药经验+5%",
        "steps": (
            ("蘑菇处理。", ("切片", "整个", "碎末"), 0),
            ("炒香。", ("充分炒", "轻轻炒", "不炒"), 1),
            ("加奶油。", ("早加", "晚加", "不加"), 0),
        ),
    },
    "minestrone": {
        "name": "意大利蔬菜汤", "category": "soup", "grade": 2, "exp": 16,
        "ingredients": {"mat_vegetable": 3, "mat_tomato": 1, "mat_beans": 1, "mat_water": 3},
        "effect": "恢复8点厨房活力；下次课堂表现+1",
        "steps": (
            ("切菜。", ("细切", "块状", "碎末"), 1),
            ("顺序。", ("一起放", "分次放", "反序放"), 0),
            ("煮时间。", ("30分钟", "20分钟", "40分钟"), 1),
        ),
    },
    "clam_chowder": {
        "name": "蛤蜊浓汤", "category": "soup", "grade": 3, "exp": 21,
        "ingredients": {"mat_clam": 2, "mat_potato": 1, "mat_cream": 1, "mat_water": 2},
        "effect": "恢复9点厨房活力；下次禁林冒险+15HP",
        "steps": (
            ("贝类。", ("新鲜", "冷冻", "罐装"), 0),
            ("奶油。", ("多", "少", "适量"), 1),
            ("咸度。", ("咸", "淡", "适中"), 2),
        ),
    },
    "lentil_soup": {
        "name": "扁豆汤", "category": "soup", "grade": 2, "exp": 13,
        "ingredients": {"mat_lentil": 2, "mat_vegetable": 1, "mat_water": 3},
        "effect": "恢复7点厨房活力；烹饪经验+8%",
        "steps": (
            ("浸泡。", ("浸过夜", "快速浸", "不浸"), 0),
            ("火候。", ("文火", "中火", "大火"), 0),
            ("时间。", ("30分钟", "45分钟", "20分钟"), 1),
        ),
    },

    # === 甜点（dessert）===
    "chocolate_cake": {
        "name": "巧克力蛋糕", "category": "dessert", "grade": 3, "exp": 28,
        "ingredients": {"mat_flour": 2, "mat_egg": 3, "mat_chocolate": 2, "mat_sugar": 1},
        "effect": "恢复6点厨房活力；心情+2；烹饪经验+10%",
        "steps": (
            ("面糊打发。", ("充分打发", "轻轻混合", "用力搅"), 0),
            ("加巧克力。", ("融化后加", "块状加", "粉末加"), 1),
            ("烤温度。", ("180度", "160度", "200度"), 0),
        ),
    },
    "cookies": {
        "name": "饼干", "category": "dessert", "grade": 2, "exp": 14,
        "ingredients": {"mat_flour": 1, "mat_butter": 1, "mat_sugar": 1, "mat_egg": 1},
        "effect": "恢复5点厨房活力；心情+1",
        "steps": (
            ("黄油软化。", ("充分软化", "部分软化", "冷硬"), 0),
            ("混面糊。", ("至顺滑", "保留颗粒", "过度混合"), 1),
            ("烤时间。", ("10分钟", "15分钟", "5分钟"), 0),
        ),
    },
    "ice_cream": {
        "name": "冰淇淋", "category": "dessert", "grade": 2, "exp": 16,
        "ingredients": {"mat_cream": 2, "mat_milk": 1, "mat_sugar": 1},
        "effect": "恢复5点厨房活力；心情+2；体感温度降低",
        "steps": (
            ("混合材料。", ("充分混合", "轻轻混合", "分层"), 0),
            ("冷冻。", ("4小时", "2小时", "6小时"), 1),
            ("搅打。", ("中途搅打", "不搅打", "多次搅打"), 1),
        ),
    },
    "tart": {
        "name": "果挞", "category": "dessert", "grade": 3, "exp": 24,
        "ingredients": {"mat_flour": 1, "mat_egg": 2, "mat_cream": 1, "mat_fruit": 1},
        "effect": "恢复7点厨房活力；心情+2；下次课堂表现+1",
        "steps": (
            ("烤挞皮。", ("先烤", "最后烤", "不烤"), 0),
            ("馅料。", ("混至顺滑", "保留块状", "过度搅"), 1),
            ("烤箱。", ("170度25分钟", "180度20分钟", "160度30分钟"), 0),
        ),
    },
    "apple_pie": {
        "name": "苹果派", "category": "dessert", "grade": 3, "exp": 26,
        "ingredients": {"mat_apple": 2, "mat_flour": 2, "mat_sugar": 1, "mat_butter": 1},
        "effect": "恢复7点厨房活力；心情+3",
        "steps": (
            ("派皮。", ("黄油粉", "混合面粉", "揉光滑"), 0),
            ("馅料。", ("糖多", "糖少", "不加糖"), 1),
            ("烤温。", ("200度", "180度", "220度"), 1),
        ),
    },
    "tiramisu": {
        "name": "提拉米苏", "category": "dessert", "grade": 3, "exp": 27,
        "ingredients": {"mat_mascarpone": 1, "mat_egg": 2, "mat_coffee": 1, "mat_cocoa": 1},
        "effect": "恢复8点厨房活力；心情+3；烹饪经验+12%",
        "steps": (
            ("蛋液。", ("蛋黄", "全蛋", "蛋白"), 0),
            ("咖啡。", ("浸透", "轻浸", "不浸"), 1),
            ("冷冻。", ("一夜", "几小时", "半小时"), 1),
        ),
    },
    "cheesecake": {
        "name": "芝士蛋糕", "category": "dessert", "grade": 3, "exp": 29,
        "ingredients": {"mat_cream_cheese": 2, "mat_egg": 3, "mat_sugar": 1},
        "effect": "恢复8点厨房活力；心情+3；下次课堂表现+1",
        "steps": (
            ("奶油芝士。", ("充分软化", "半软", "冷硬"), 0),
            ("混合。", ("充分混", "轻混", "分层"), 1),
            ("烤温。", ("160度", "180度", "150度"), 0),
        ),
    },
    "brownies": {
        "name": "布朗尼蛋糕", "category": "dessert", "grade": 2, "exp": 18,
        "ingredients": {"mat_chocolate": 2, "mat_egg": 2, "mat_flour": 1, "mat_butter": 1},
        "effect": "恢复6点厨房活力；心情+2；魔药经验+5%",
        "steps": (
            ("巧克力。", ("融化好", "颗粒状", "完全融合"), 1),
            ("混合。", ("过度混", "适度混", "轻混"), 1),
            ("烤时间。", ("25分钟", "35分钟", "15分钟"), 0),
        ),
    },
    "macaron": {
        "name": "马卡龙", "category": "dessert", "grade": 4, "exp": 35,
        "ingredients": {"mat_almond_flour": 1, "mat_powdered_sugar": 1, "mat_egg": 2, "mat_food_color": 1},
        "effect": "恢复7点厨房活力；心情+3；烹饪经验+15%",
        "steps": (
            ("蛋白。", ("充分打发", "软峰", "硬峰"), 2),
            ("混合。", ("过度搅", "充分搅", "轻轻搅"), 1),
            ("烤温。", ("140度", "160度", "120度"), 0),
        ),
    },
    "fudge": {
        "name": "软糖", "category": "dessert", "grade": 2, "exp": 13,
        "ingredients": {"mat_chocolate": 1, "mat_cream": 1, "mat_sugar": 1},
        "effect": "恢复5点厨房活力；心情+2；烹饪经验+5%",
        "steps": (
            ("糖浆浓度。", ("稀", "浓", "极浓"), 1),
            ("巧克力融入。", ("细致混合", "粗糙混合", "分层"), 0),
            ("冷却。", ("快速冷却", "缓慢冷却", "常温"), 1),
        ),
    },

    # === 魔法美食（magic）===
    "courage_stew": {
        "name": "勇士汤", "category": "magic", "grade": 4, "exp": 35,
        "ingredients": {"mat_phoenix_feather": 1, "mat_dragon_scale": 1, "mat_herbs": 2},
        "effect": "下次禁林冒险护盾+20；恢复9点厨房活力",
        "steps": (
            ("凤凰羽毛入汤。", ("先入", "后入", "不入"), 0),
            ("龙鳞。", ("完整投入", "磨成粉", "烧焦"), 1),
            ("熬制。", ("文火", "大火", "中火"), 0),
        ),
    },
    "wisdom_jam": {
        "name": "聪慧果酱", "category": "magic", "grade": 4, "exp": 32,
        "ingredients": {"mat_moonstone": 1, "mat_starfruit": 2, "mat_honey": 1},
        "effect": "下次计分课程表现+2；烹饪经验+15%",
        "steps": (
            ("月光石研磨。", ("细粉", "粗粉", "块状"), 0),
            ("果实。", ("完整", "切碎", "碾碎"), 2),
            ("混合时间。", ("趁热", "冷却后", "半温"), 1),
        ),
    },
    "invisibility_tea": {
        "name": "隐身茶", "category": "magic", "grade": 5, "exp": 48,
        "ingredients": {"mat_basilisk_fang": 1, "mat_moonflower": 2, "mat_water": 2},
        "effect": "饮用后隐身1小时；禁林探险隐匿度大幅提升",
        "steps": (
            ("龙蛇牙。", ("完整投入", "碎末", "研磨"), 1),
            ("月光花。", ("新鲜", "干燥", "粉末"), 0),
            ("水温。", ("沸水", "温水", "冷水"), 2),
        ),
    },
    "focus_potion": {
        "name": "专注药茶", "category": "magic", "grade": 3, "exp": 28,
        "ingredients": {"mat_star_anise": 1, "mat_lavender": 1, "mat_honey": 1},
        "effect": "下次制作成功率+20%；恢复7点厨房活力",
        "steps": (
            ("八角入茶。", ("整个", "碎末", "烘焙"), 0),
            ("薰衣草。", ("新鲜", "干燥", "粉末"), 1),
            ("冲泡。", ("8分钟", "5分钟", "10分钟"), 1),
        ),
    },
    "healing_broth": {
        "name": "治疗高汤", "category": "magic", "grade": 4, "exp": 38,
        "ingredients": {"mat_phoenix_feather": 1, "mat_unicorn_hair": 1, "mat_bone": 2},
        "effect": "饮用恢复20HP；下次禁林冒险恢复+10HP",
        "steps": (
            ("凤凰羽毛。", ("先投", "后投", "不投"), 1),
            ("独角兽毛。", ("完整", "切段", "碾碎"), 0),
            ("火候。", ("文火", "大火", "中火"), 0),
        ),
    },
    "phoenix_nest": {
        "name": "凤凰巢", "category": "magic", "grade": 4, "exp": 40,
        "ingredients": {"mat_phoenix_feather": 2, "mat_golden_egg": 1, "mat_honey": 2},
        "effect": "下次禁林冒险+30HP；恢复10点厨房活力；心情+2",
        "steps": (
            ("凤凰羽毛。", ("烧焦", "轻轻烘", "冷用"), 1),
            ("黄金蛋。", ("整个", "打碎", "磨粉"), 0),
            ("蜂蜜。", ("很多", "少量", "适量"), 2),
        ),
    },
    "dragon_breath_soup": {
        "name": "龙息汤", "category": "magic", "grade": 5, "exp": 50,
        "ingredients": {"mat_dragon_scale": 1, "mat_dragon_blood": 1, "mat_fire_pepper": 2},
        "effect": "饮用后20分钟内魔法抗性+50%；恢复10点厨房活力",
        "steps": (
            ("龙鳞。", ("完整投入", "研磨", "烧焦"), 0),
            ("龙血。", ("新鲜", "冷冻", "干粉"), 1),
            ("辣椒。", ("很多", "少量", "适量"), 2),
        ),
    },
    "mermaid_delight": {
        "name": "美人鱼的喜悦", "category": "magic", "grade": 4, "exp": 38,
        "ingredients": {"mat_pearl": 1, "mat_seaweed": 2, "mat_spring_water": 2},
        "effect": "水下呼吸1小时；恢复9点厨房活力；心情+2",
        "steps": (
            ("珍珠。", ("完整", "碎末", "粉末"), 0),
            ("海草。", ("新鲜", "干燥", "粉末"), 1),
            ("泉水。", ("冷泉", "温泉", "热泉"), 1),
        ),
    },
    "unicorn_tears_jelly": {
        "name": "独角兽泪果冻", "category": "magic", "grade": 5, "exp": 55,
        "ingredients": {"mat_unicorn_tears": 2, "mat_starlight": 1, "mat_honey": 1},
        "effect": "一次性满血回复；恢复10点厨房活力；心情+3",
        "steps": (
            ("泪水。", ("新鲜", "冷冻", "干粉"), 0),
            ("星光。", ("直接加", "融化加", "粉末"), 1),
            ("凝固。", ("室温", "冰冷", "加热"), 1),
        ),
    },
    "phoenix_flame_cake": {
        "name": "凤凰之火蛋糕", "category": "magic", "grade": 4, "exp": 42,
        "ingredients": {"mat_phoenix_feather": 1, "mat_hot_pepper": 2, "mat_egg": 3, "mat_flour": 2},
        "effect": "吃后4小时内火焰魔法伤害+40%；恢复8点厨房活力",
        "steps": (
            ("凤凰羽毛。", ("烧焦", "轻烘", "生用"), 1),
            ("辣椒。", ("鲜辣", "干辣", "粉末"), 0),
            ("火候。", ("炉火", "魔火", "缓火"), 1),
        ),
    },

    # === 饮品（beverage）===
    "hot_chocolate": {
        "name": "热巧克力", "category": "beverage", "grade": 1, "exp": 8,
        "ingredients": {"mat_chocolate": 1, "mat_milk": 2, "mat_sugar": 1},
        "effect": "恢复5点厨房活力；心情+1",
        "steps": (
            ("巧克力融化。", ("水浴融化", "直接融化", "隔热融化"), 0),
            ("加热牛奶。", ("温热", "烫手", "微温"), 1),
            ("混合。", ("快速搅", "慢速搅", "不搅"), 2),
        ),
    },
    "pumpkin_juice": {
        "name": "南瓜汁", "category": "beverage", "grade": 1, "exp": 10,
        "ingredients": {"mat_pumpkin": 1, "mat_water": 1},
        "effect": "恢复6点厨房活力；心情+1",
        "steps": (
            ("南瓜切块。", ("大块", "小块", "碎末"), 1),
            ("榨汁。", ("充分榨", "轻轻榨", "不榨"), 0),
            ("过筛。", ("细筛", "粗筛", "不筛"), 0),
        ),
    },
    "butterbeer": {
        "name": "黄油啤酒", "category": "beverage", "grade": 2, "exp": 14,
        "ingredients": {"mat_butterbeer_base": 1, "mat_butter": 1, "mat_cream": 1},
        "effect": "恢复7点厨房活力；心情+2；下次课堂表现+1",
        "steps": (
            ("黄油融化。", ("温热融化", "冷融", "高温融"), 0),
            ("混合。", ("充分乳化", "轻轻混合", "分层"), 0),
            ("顶部。", ("加奶油", "不加", "加很多"), 2),
        ),
    },
    "mead": {
        "name": "蜜酒", "category": "beverage", "grade": 3, "exp": 18,
        "ingredients": {"mat_honey": 2, "mat_water": 3, "mat_herbs": 1},
        "effect": "恢复8点厨房活力；心情+2；禁林采集经验+8%",
        "steps": (
            ("蜂蜜溶解。", ("温水", "热水", "冷水"), 1),
            ("发酵时间。", ("1周", "2周", "3周"), 1),
            ("过滤。", ("细筛", "粗筛", "不筛"), 0),
        ),
    },
    "ginger_tea": {
        "name": "生姜茶", "category": "beverage", "grade": 1, "exp": 9,
        "ingredients": {"mat_ginger": 1, "mat_honey": 1, "mat_water": 1},
        "effect": "恢复5点厨房活力；清除寒冷",
        "steps": (
            ("生姜。", ("新鲜", "干燥", "粉末"), 0),
            ("水温。", ("沸水", "温水", "冷水"), 1),
            ("蜂蜜。", ("多", "少", "适量"), 1),
        ),
    },
    "chamomile_tea": {
        "name": "洋甘菊茶", "category": "beverage", "grade": 2, "exp": 11,
        "ingredients": {"mat_chamomile": 1, "mat_honey": 1, "mat_water": 1},
        "effect": "恢复6点厨房活力；心情+2；睡眠质量提升",
        "steps": (
            ("花朵。", ("新鲜", "干燥", "碎末"), 1),
            ("浸泡。", ("5分钟", "10分钟", "3分钟"), 1),
            ("温度。", ("热", "温", "冷"), 0),
        ),
    },
    "fruit_punch": {
        "name": "果汁混合", "category": "beverage", "grade": 2, "exp": 12,
        "ingredients": {"mat_fruit": 3, "mat_sugar": 1, "mat_water": 1},
        "effect": "恢复6点厨房活力；心情+1；体力恢复+2",
        "steps": (
            ("水果选择。", ("甜的", "酸的", "混合"), 1),
            ("糖量。", ("多", "少", "适量"), 1),
            ("饮用。", ("热饮", "温饮", "冷饮"), 2),
        ),
    },
    "mulled_wine": {
        "name": "热红酒", "category": "beverage", "grade": 2, "exp": 13,
        "ingredients": {"mat_wine": 2, "mat_spices": 1, "mat_honey": 1},
        "effect": "恢复7点厨房活力；心情+2；暖身驱寒",
        "steps": (
            ("香料。", ("磨粉", "整个", "碎末"), 0),
            ("加热。", ("轻轻热", "充分热", "烧开"), 1),
            ("蜂蜜。", ("多", "少", "适量"), 0),
        ),
    },
    "smoothie": {
        "name": "果昔", "category": "beverage", "grade": 2, "exp": 10,
        "ingredients": {"mat_fruit": 2, "mat_yogurt": 1, "mat_honey": 1},
        "effect": "恢复6点厨房活力；下次课堂表现+1",
        "steps": (
            ("水果处理。", ("新鲜", "冷冻", "混合"), 1),
            ("酸奶。", ("普通", "希腊", "果味"), 0),
            ("搅打。", ("充分搅", "轻搅", "不搅"), 0),
        ),
    },

    # === 点心小食（snack）===
    "nuts": {
        "name": "坚果", "category": "snack", "grade": 1, "exp": 5,
        "ingredients": {"mat_nuts": 1, "mat_salt": 1},
        "effect": "恢复3点厨房活力；快速补充",
        "steps": (
            ("烘焙。", ("轻烤", "重烤", "生吃"), 0),
            ("撒盐。", ("多盐", "少盐", "不撒"), 1),
            ("冷却。", ("完全冷却", "半温", "趁热"), 2),
        ),
    },
    "candy": {
        "name": "糖果", "category": "snack", "grade": 2, "exp": 12,
        "ingredients": {"mat_sugar": 2, "mat_honey": 1, "mat_flavoring": 1},
        "effect": "恢复4点厨房活力；心情+1；快速小补",
        "steps": (
            ("糖浆温度。", ("140°C", "160°C", "120°C"), 1),
            ("趁热。", ("立刻倒入", "半凝时倒", "完全冷却"), 0),
            ("切割。", ("快刀", "慢刀", "手撕"), 0),
        ),
    },
    "popcorn": {
        "name": "爆米花", "category": "snack", "grade": 1, "exp": 7,
        "ingredients": {"mat_corn": 1, "mat_butter": 1, "mat_salt": 1},
        "effect": "恢复4点厨房活力；心情+1",
        "steps": (
            ("油温。", ("高温", "中温", "低温"), 0),
            ("放入玉米。", ("一次性", "分次", "慢慢放"), 1),
            ("调味。", ("趁热撒", "冷却后撒", "不撒"), 0),
        ),
    },
    "croissant": {
        "name": "羊角面包", "category": "snack", "grade": 3, "exp": 20,
        "ingredients": {"mat_flour": 2, "mat_butter": 2, "mat_salt": 1},
        "effect": "恢复6点厨房活力；心情+1；魔药经验+5%",
        "steps": (
            ("层数。", ("少层", "多层", "标准"), 1),
            ("黄油。", ("冷黄油", "软黄油", "常温"), 0),
            ("烤温。", ("200度", "180度", "220度"), 0),
        ),
    },
    "donut": {
        "name": "甜甜圈", "category": "snack", "grade": 2, "exp": 14,
        "ingredients": {"mat_flour": 1, "mat_egg": 1, "mat_sugar": 1, "mat_oil": 1},
        "effect": "恢复5点厨房活力；心情+2",
        "steps": (
            ("面团。", ("软", "硬", "适中"), 2),
            ("油温。", ("高温", "中温", "低温"), 0),
            ("糖衣。", ("多", "少", "不加"), 1),
        ),
    },
    "biscuit": {
        "name": "饼干（黄油）", "category": "snack", "grade": 2, "exp": 12,
        "ingredients": {"mat_flour": 1, "mat_butter": 1, "mat_sugar": 1},
        "effect": "恢复5点厨房活力；心情+1；禁林采集+1%经验",
        "steps": (
            ("黄油。", ("软化好", "半软", "冷硬"), 0),
            ("面糊。", ("光滑", "颗粒", "粗糙"), 0),
            ("烤时。", ("10分钟", "15分钟", "5分钟"), 1),
        ),
    },
    "pretzel": {
        "name": "椒盐脆饼", "category": "snack", "grade": 2, "exp": 11,
        "ingredients": {"mat_flour": 1, "mat_salt": 1, "mat_egg": 1},
        "effect": "恢复5点厨房活力；下次课堂表现+1",
        "steps": (
            ("形状。", ("传统扭", "棒状", "脆饼"), 0),
            ("苏打水。", ("浸过", "不浸", "轻浸"), 1),
            ("盐量。", ("多", "少", "适量"), 1),
        ),
    },
    "mochi": {
        "name": "麻糬", "category": "snack", "grade": 2, "exp": 13,
        "ingredients": {"mat_rice_flour": 1, "mat_sugar": 1, "mat_filling": 1},
        "effect": "恢复5点厨房活力；心情+2；烹饪经验+6%",
        "steps": (
            ("粉类。", ("糯米粉", "普通粉", "混合"), 0),
            ("馅料。", ("豆沙", "果味", "坚果"), 1),
            ("烤/煮。", ("蒸", "烤", "煮"), 1),
        ),
    },
}

RECIPES_BY_NAME = {r["name"]: key for key, r in RECIPES.items()}
FOOD_ITEMS = {f"food_{key}": recipe["name"] for key, recipe in RECIPES.items()}

TITLE_NAMES = {
    "kitchen_novice": "厨房新手",
    "kitchen_apprentice": "学徒厨师",
    "kitchen_enthusiast": "烹饪爱好者",
    "kitchen_collector": "配方收集家",
    "kitchen_researcher": "美食研究者",
    "kitchen_master": "烹饪大师",
    "kitchen_expert": "霍格沃茨名厨",
}

TITLE_REQUIREMENTS = {
    "kitchen_novice": "成功烹饪第一份食物",
    "kitchen_apprentice": "累计成功烹饪5次",
    "kitchen_enthusiast": "学会15个配方",
    "kitchen_collector": "学会50个配方",
    "kitchen_researcher": "学会所有魔法美食配方",
    "kitchen_master": "任意配方成功率达80%",
    "kitchen_expert": "累计成功烹饪100次",
}


class KitchenError(Exception):
    pass


def find_recipe(value: str):
    key = value if value in RECIPES else RECIPES_BY_NAME.get(value)
    return (key, RECIPES[key]) if key else None


def item_name(item_key: str) -> str | None:
    return FOOD_ITEMS.get(item_key)


def get_session(uid: str):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM kitchen_sessions WHERE uid=?", (uid,)).fetchone()
    finally:
        conn.close()


def _render_session(row, resumed: bool = False) -> dict:
    recipe = RECIPES[row["recipe_key"]]
    prompt, options, _ = recipe["steps"][row["step"]]
    return {
        "recipe": recipe["name"],
        "step": row["step"] + 1,
        "total_steps": len(recipe["steps"]),
        "prompt": prompt,
        "options": options,
        "resumed": resumed,
    }


def start(uid: str, recipe_input: str) -> dict:
    existing = get_session(uid)
    if existing:
        return _render_session(existing, True)

    found = find_recipe(recipe_input.strip())
    if not found:
        raise KitchenError("没有这个配方。发送「/烹饪配方」查看已知配方。")

    key, recipe = found
    player = core_storage.sync_stamina(uid)
    if not player or not player["house"]:
        raise KitchenError("你还没有完成入学手续。")

    core_storage.sync_kitchen_stamina(uid)
    exp = core_storage.get_cooking_exp(uid)

    if player["grade"] < recipe["grade"] or exp < recipe["exp"]:
        raise KitchenError(
            f"这个配方需要{recipe['grade']}年级、烹饪{recipe['exp']}经验。"
            f"你目前是{player['grade']}年级、{exp}经验。"
        )

    day = core_storage.get_current_day() or 1
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM kitchen_sessions WHERE uid=?", (uid,)).fetchone():
            conn.rollback()
            return _render_session(get_session(uid), True)

        conn.execute("INSERT OR IGNORE INTO kitchen_daily(uid,day,count) VALUES(?,?,0)", (uid, day))
        count = conn.execute("SELECT count FROM kitchen_daily WHERE uid=? AND day=?", (uid, day)).fetchone()[0]
        if count >= DAILY_LIMIT:
            conn.rollback()
            raise KitchenError(f"你今天已经烹饪{DAILY_LIMIT}次了，再做下去连厨房都得关闭了。")

        stamina = conn.execute(
            "SELECT kitchen_stamina FROM kitchen_exp WHERE uid=?", (uid,)
        ).fetchone()
        kitchen_stamina = stamina[0] if stamina else STAMINA_MAX
        if kitchen_stamina < COOK_STAMINA_COST:
            conn.rollback()
            raise KitchenError(
                f"你现在只有{kitchen_stamina}/{STAMINA_MAX}点厨房活力，"
                f"烹饪需要{COOK_STAMINA_COST}点。"
            )

        missing = []
        for item_key, amount in recipe["ingredients"].items():
            have = conn.execute(
                "SELECT quantity FROM inventory WHERE uid=? AND item_key=?", (uid, item_key)
            ).fetchone()
            if not have or have[0] < amount:
                missing.append(f"{item_key}×{amount - (have[0] if have else 0)}")

        if missing:
            conn.rollback()
            raise KitchenError("材料还不够：" + "、".join(missing))

        for item_key, amount in recipe["ingredients"].items():
            conn.execute(
                "UPDATE inventory SET quantity=quantity-? WHERE uid=? AND item_key=?",
                (amount, uid, item_key),
            )

        ts = core_storage.now()
        conn.execute(
            "UPDATE kitchen_exp SET kitchen_stamina=kitchen_stamina-?,updated_at=? WHERE uid=?",
            (COOK_STAMINA_COST, ts, uid),
        )
        conn.execute("UPDATE kitchen_daily SET count=count+1 WHERE uid=? AND day=?", (uid, day))
        conn.execute(
            "INSERT INTO kitchen_sessions VALUES(?,?,?,?,?,?,?,?)",
            (uid, key, 0, 0, json.dumps(recipe["ingredients"]), "[]", ts, ts),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return _render_session(get_session(uid))


def choose(uid: str, position: int) -> dict:
    if position not in (1, 2, 3, 4):
        raise KitchenError("请选择1、2、3或4。")

    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM kitchen_sessions WHERE uid=?", (uid,)).fetchone()
        if not row:
            conn.rollback()
            raise KitchenError("你面前没有正在烹饪的食物。")

        recipe = RECIPES[row["recipe_key"]]
        _, _, correct = recipe["steps"][row["step"]]
        score = row["score"] + (1 if position - 1 == correct else 0)
        choices = json.loads(row["choices_json"])
        choices.append(position)
        next_step = row["step"] + 1

        if next_step < len(recipe["steps"]):
            conn.execute(
                "UPDATE kitchen_sessions SET step=?,score=?,choices_json=?,updated_at=? WHERE uid=?",
                (next_step, score, json.dumps(choices), core_storage.now(), uid),
            )
            conn.commit()
            return {"finished": False, **_render_session(get_session(uid))}

        success = score >= len(recipe["steps"]) - 1
        perfect = score == len(recipe["steps"])
        quantity = 2 if perfect else 1 if success else 0

        if quantity:
            conn.execute(
                "INSERT INTO kitchen_inventory(uid,food_key,quantity,created_at) "
                "VALUES(?,?,?,?) "
                "ON CONFLICT(uid,food_key) DO UPDATE SET quantity=quantity+excluded.quantity",
                (uid, f"food_{row['recipe_key']}", quantity, core_storage.now()),
            )

        conn.execute(
            "INSERT INTO kitchen_mastery(uid,recipe_key,attempts,successes,perfects) "
            "VALUES(?,?,?,?,?) "
            "ON CONFLICT(uid,recipe_key) DO UPDATE SET "
            "attempts=attempts+1,successes=successes+excluded.successes,"
            "perfects=perfects+excluded.perfects",
            (uid, row["recipe_key"], 1, int(success), int(perfect)),
        )

        accident = ""
        if not success:
            accident = random.choice(DISASTERS)
            conn.execute(
                "INSERT INTO active_effects(uid,effect_key,label,expires_at) "
                "VALUES(?,?,?,?) "
                "ON CONFLICT(uid,effect_key) DO UPDATE SET label=excluded.label,expires_at=excluded.expires_at",
                (uid, "cooking_disaster", accident, core_storage.now() + 2 * 3600),
            )

        conn.execute(
            "INSERT INTO kitchen_history(uid,recipe_key,quality,quantity,disaster,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (
                uid,
                row["recipe_key"],
                "perfect" if perfect else "success" if success else "failed",
                quantity,
                accident,
                core_storage.now(),
            ),
        )

        conn.execute("DELETE FROM kitchen_sessions WHERE uid=?", (uid,))
        conn.commit()

        return {
            "finished": True,
            "recipe": recipe["name"],
            "success": success,
            "perfect": perfect,
            "quantity": quantity,
            "accident": accident,
            "score": score,
            "max_score": len(recipe["steps"]),
        }

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def consume(uid: str, food_input: str) -> dict:
    """食用食物，应用buff效果。"""
    food_input = food_input.strip()

    # 查找配方
    found = find_recipe(food_input)
    if not found:
        raise KitchenError(f"不认识这个食物「{food_input}」。发送「/食柜」查看你有什么。")

    key, recipe = found
    food_key = f"food_{key}"

    player = core_storage.sync_stamina(uid)
    if not player or not player["house"]:
        raise KitchenError("你还没有分院。")

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT quantity FROM kitchen_inventory WHERE uid=? AND food_key=?",
            (uid, food_key),
        ).fetchone()

        if not row or row["quantity"] <= 0:
            raise KitchenError(f"你没有「{recipe['name']}」。")

        # 扣除食物
        conn.execute(
            "UPDATE kitchen_inventory SET quantity=quantity-1 WHERE uid=? AND food_key=?",
            (uid, food_key),
        )

        # 记录使用
        ts = core_storage.now()
        conn.execute(
            "INSERT INTO kitchen_history(uid,recipe_key,quality,quantity,disaster,created_at) "
            "VALUES(?,?,'consumed',1,'',?)",
            (uid, key, ts),
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return {
        "recipe": recipe["name"],
        "effect": recipe["effect"],
        "remaining": (row["quantity"] - 1) if row else 0,
    }


def apply_food_effects(uid: str, recipe_key: str) -> dict:
    """应用食物的buff效果。返回生成的效果列表。"""
    if recipe_key not in RECIPES:
        return {}

    recipe = RECIPES[recipe_key]
    effects = {}
    ts = core_storage.now()

    effect_text = recipe.get("effect", "")

    # 恢复厨房活力
    match = re.search(r"恢复(\d+)点厨房活力", effect_text)
    if match:
        amount = int(match.group(1))
        conn = get_conn()
        try:
            conn.execute(
                "UPDATE kitchen_exp SET kitchen_stamina=MIN(40, kitchen_stamina+?) WHERE uid=?",
                (amount, uid),
            )
            conn.commit()
        finally:
            conn.close()
        effects["kitchen_stamina"] = amount

    # 心情加成
    match = re.search(r"心情\+(\d+)", effect_text)
    if match:
        amount = int(match.group(1))
        conn = core_storage.get_conn()
        try:
            expires = ts + 2 * 3600  # 2小时
            conn.execute(
                "INSERT INTO active_effects(uid,effect_key,label,expires_at) VALUES(?,?,?,?) "
                "ON CONFLICT(uid,effect_key) DO UPDATE SET expires_at=MAX(expires_at,excluded.expires_at)",
                (uid, "mood_boost", f"心情愉悦(+{amount})", expires),
            )
            conn.commit()
        finally:
            conn.close()
        effects["mood"] = amount

    # 下次课堂表现
    match = re.search(r"下次课堂表现\+(\d+)", effect_text)
    if match:
        amount = int(match.group(1))
        conn = core_storage.get_conn()
        try:
            expires = ts + 12 * 3600  # 12小时内的下一次课程
            conn.execute(
                "INSERT INTO active_effects(uid,effect_key,label,expires_at) VALUES(?,?,?,?) "
                "ON CONFLICT(uid,effect_key) DO UPDATE SET label=excluded.label,expires_at=excluded.expires_at",
                (uid, "lesson_performance_boost", f"课堂表现加成(+{amount})", expires),
            )
            conn.commit()
        finally:
            conn.close()
        effects["lesson_bonus"] = amount

    # 禁林采集加成
    match = re.search(r"禁林采集\+(\d+)", effect_text)
    if match:
        amount = int(match.group(1))
        conn = core_storage.get_conn()
        try:
            expires = ts + 6 * 3600
            label = f"采集运气(+{amount})" if "材料" in effect_text else f"采集加成(+{amount}%)"
            conn.execute(
                "INSERT INTO active_effects(uid,effect_key,label,expires_at) VALUES(?,?,?,?) "
                "ON CONFLICT(uid,effect_key) DO UPDATE SET label=excluded.label,expires_at=excluded.expires_at",
                (uid, "forest_gathering_boost", label, expires),
            )
            conn.commit()
        finally:
            conn.close()
        effects["gathering"] = amount

    # 下次禁林冒险护盾
    match = re.search(r"下次禁林冒险\+(\d+)HP", effect_text)
    if match:
        amount = int(match.group(1))
        conn = core_storage.get_conn()
        try:
            expires = ts + 24 * 3600
            conn.execute(
                "INSERT INTO active_effects(uid,effect_key,label,expires_at) VALUES(?,?,?,?) "
                "ON CONFLICT(uid,effect_key) DO UPDATE SET label=excluded.label,expires_at=excluded.expires_at",
                (uid, "forest_shield", f"冒险护盾(+{amount}HP)", expires),
            )
            conn.commit()
        finally:
            conn.close()
        effects["shield"] = amount

    return effects


def get_material_name(mat_key: str) -> str:
    """获取材料的中文名称。"""
    if mat_key in KITCHEN_MATERIALS:
        return KITCHEN_MATERIALS[mat_key][0]
    return mat_key


def grant_starter_materials(uid: str) -> dict:
    """给新玩家赠送初始材料包。"""
    starter_pack = {
        "mat_egg": 5,
        "mat_butter": 3,
        "mat_salt": 2,
        "mat_bread": 3,
        "mat_milk": 4,
        "mat_honey": 2,
        "mat_flour": 3,
        "mat_sugar": 2,
    }

    conn = get_conn()
    try:
        granted = {}
        for mat_key, amount in starter_pack.items():
            conn.execute(
                "INSERT INTO inventory(uid,item_key,quantity) VALUES(?,?,?) "
                "ON CONFLICT(uid,item_key) DO UPDATE SET quantity=quantity+excluded.quantity",
                (uid, mat_key, amount),
            )
            granted[mat_key] = amount
        conn.commit()
        return granted
    finally:
        conn.close()


def grant_weekly_materials(uid: str) -> dict:
    """每周赠送补充材料包。"""
    weekly_pack = {
        "mat_egg": 3,
        "mat_butter": 2,
        "mat_milk": 2,
        "mat_honey": 1,
        "mat_flour": 2,
        "mat_salt": 1,
        "mat_sugar": 1,
        "mat_vegetable": 2,
        "mat_herbs": 1,
    }

    conn = get_conn()
    try:
        granted = {}
        for mat_key, amount in weekly_pack.items():
            conn.execute(
                "INSERT INTO inventory(uid,item_key,quantity) VALUES(?,?,?) "
                "ON CONFLICT(uid,item_key) DO UPDATE SET quantity=quantity+excluded.quantity",
                (uid, mat_key, amount),
            )
            granted[mat_key] = amount
        conn.commit()
        return granted
    finally:
        conn.close()


def check_achievements(uid: str) -> list[str]:
    """检查并解锁成就。"""
    unlocked = []
    conn = get_conn()
    try:
        # 检查各个成就条件
        player = core_storage.get_player(uid)

        # 成就1：首次烹饪成功
        history = conn.execute(
            "SELECT COUNT(*) as cnt FROM kitchen_history WHERE uid=? AND quality='success' OR quality='perfect'",
            (uid,),
        ).fetchone()
        if history and history["cnt"] >= 1:
            if not core_storage.has_title(uid, "kitchen_novice"):
                core_storage.unlock_title(uid, "kitchen_novice")
                unlocked.append("🎖️ 厨房新手")

        # 成就2：累计5次成功
        if history and history["cnt"] >= 5:
            if not core_storage.has_title(uid, "kitchen_apprentice"):
                core_storage.unlock_title(uid, "kitchen_apprentice")
                unlocked.append("🎖️ 学徒厨师")

        # 成就3：学会15个配方
        learned = conn.execute(
            "SELECT COUNT(*) as cnt FROM kitchen_learned_recipes WHERE uid=?",
            (uid,),
        ).fetchone()
        if learned and learned["cnt"] >= 15:
            if not core_storage.has_title(uid, "kitchen_enthusiast"):
                core_storage.unlock_title(uid, "kitchen_enthusiast")
                unlocked.append("🎖️ 烹饪爱好者")

        # 成就4：学会50个配方
        if learned and learned["cnt"] >= 50:
            if not core_storage.has_title(uid, "kitchen_collector"):
                core_storage.unlock_title(uid, "kitchen_collector")
                unlocked.append("🎖️ 配方收集家")

        # 成就5：学会所有魔法美食
        magic_recipes = [k for k, r in RECIPES.items() if r.get("category") == "magic"]
        magic_learned = conn.execute(
            "SELECT COUNT(*) as cnt FROM kitchen_learned_recipes WHERE uid=? AND recipe_key IN ("
            + ",".join(["?"] * len(magic_recipes))
            + ")",
            (uid, *magic_recipes),
        ).fetchone()
        if magic_learned and magic_learned["cnt"] >= len(magic_recipes):
            if not core_storage.has_title(uid, "kitchen_researcher"):
                core_storage.unlock_title(uid, "kitchen_researcher")
                unlocked.append("🎖️ 美食研究者")

        # 成就6：累计100次成功
        if history and history["cnt"] >= 100:
            if not core_storage.has_title(uid, "kitchen_expert"):
                core_storage.unlock_title(uid, "kitchen_expert")
                unlocked.append("🎖️ 霍格沃茨名厨")

        return unlocked
    finally:
        conn.close()
