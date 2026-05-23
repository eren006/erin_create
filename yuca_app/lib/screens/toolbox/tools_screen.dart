import 'dart:math';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

// ── 入口页（Tab 导航） ─────────────────────────────────────────────────────────

class ToolsScreen extends StatefulWidget {
  const ToolsScreen({super.key});
  @override
  State<ToolsScreen> createState() => _ToolsScreenState();
}

class _ToolsScreenState extends State<ToolsScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tab;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() { _tab.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('小工具', style: TextStyle()),
        iconTheme: const IconThemeData(color: Colors.white),
        bottom: TabBar(
          controller: _tab,
          indicatorColor: const Color(0xFFfb923c),
          labelColor: const Color(0xFFfb923c),
          unselectedLabelColor: const Color(0xFF6b7280),
          tabs: const [
            Tab(text: '生成器'),
            Tab(text: '文化人专区'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tab,
        children: const [
          _GeneratorsTab(),
          _CultureTab(),
        ],
      ),
    );
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Tab 1 : 生成器
// ══════════════════════════════════════════════════════════════════════════════

class _GeneratorsTab extends StatelessWidget {
  const _GeneratorsTab();
  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: const [
        _NameGenCard(),
        SizedBox(height: 14),
        _RelationGenCard(),
        SizedBox(height: 14),
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: _HobbyGenCard()),
          SizedBox(width: 12),
          Expanded(child: _PersonaGenCard()),
        ]),
        SizedBox(height: 20),
      ],
    );
  }
}

// ── 姓名生成器 ────────────────────────────────────────────────────────────────

class _NameGenCard extends StatefulWidget {
  const _NameGenCard();
  @override
  State<_NameGenCard> createState() => _NameGenCardState();
}

class _NameGenCardState extends State<_NameGenCard> {
  String _era    = 'ancient';
  String _gender = 'male';
  String _result = '';

  static const _names = {
    'ancient': {
      'surnames': ['李','王','张','刘','陈','杨','赵','黄','周','吴','林','孙','徐','朱','马','胡','萧','白','崔','慕容','上官','欧阳','司马','诸葛','公孙'],
      'male':    ['君临','怀瑾','子墨','景行','元卿','云深','烛明','长风','清晏','凌霄','玄月','思远','逸尘','如玉','承安','夜行','孤星','望川','振羽','明徽'],
      'female':  ['芷晴','月华','凌雪','素言','芙蓉','若溪','青瑶','皎皎','含烟','莺歌','晚霜','听雨','云鬟','碧落','锦衣','朝云','秋水','幽兰','澜漪','玲珑'],
      'neutral': ['逍遥','云游','忘尘','静水','微澜','虚白','如初','无极','明月','清风'],
    },
    'european': {
      'surnames': ['Ashford','Blackwell','Crowe','Devereaux','Fairfax','Harlow','Kingsley','Langdon','Moreau','Nightingale','Oakhurst','Pemberton','Ravenscroft','Sterling','Thorne','Vance','Whitmore','Aldgate','Beaumont','Castlemore'],
      'male':    ['Aldric','Bastian','Caspian','Dorian','Evander','Florian','Gareth','Hadrian','Idris','Jasper','Keiran','Leander','Marcus','Nikolai','Orion','Percival','Quinlan','Roland','Sebastien','Theron','Ulric','Valerian','Wren','Xander'],
      'female':  ['Aelindra','Beatrix','Celestine','Delphine','Evangeline','Fiora','Genevieve','Helena','Isadora','Juliette','Katalina','Liora','Mirabelle','Nathalya','Ophelia','Persephone','Rosalind','Seraphina','Theodora','Vivienne'],
      'neutral': ['Aerin','Blythe','Caelum','Daire','Emrys','Fenix','Gray','Haven','Ivo','Jules'],
    },
    'modern': {
      'surnames': ['林','陈','张','李','王','吴','刘','周','黄','郑','谢','许','徐','苏','何','叶','罗','江','韩','唐','方','蔡','赵','邓','胡','冯','杨','余','曾','秦'],
      'male':    ['宇轩','子涵','浩然','俊熙','志远','明泽','嘉诚','博文','天宇','凯旋','晟哲','承远','泽宇','昊天','子默','景泽','铭扬','峻熙','逸飞','宸睿','瑞霖','煜城','梓豪','楷瑞','嘉禾','绍远','彦博','弘毅','思齐','翰林'],
      'female':  ['晨希','安然','若薇','思涵','慕晴','雨桐','嘉瑶','诗颜','妍希','可欣','芷晴','梦瑶','语嫣','雪瑶','欣妍','依诺','若汐','梓涵','子萱','悦心','清荷','灵犀','晓彤','碧瑶','雨欣','婧怡','诗涵','若兰','沐晴','紫萱'],
      'neutral': ['一诺','云逸','以晴','洛川','星河','知恩','晴川','明熙','悠然','沐白','昱辰','澄心','向晚','远帆','默笙','夕颜','时雨','云起','暮雪','清风'],
    },
  };

  void _generate() {
    final r = Random();
    String pick(List<String> l) => l[r.nextInt(l.length)];
    final d = _names[_era]!;
    String name;
    if (_era == 'european') {
      name = '${pick(d[_gender]!)} ${pick(d['surnames']!)}';
    } else {
      name = '${pick(d['surnames']!)}${pick(d[_gender]!)}';
    }
    setState(() => _result = name);
  }

  @override
  Widget build(BuildContext context) {
    return _ToolCard(
      title: '姓名生成器',
      desc:  '随机生成一个角色名，适合各种时代背景',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // 时代
        _OptRow(
          options: const [('ancient','古代'),('european','欧洲'),('modern','现代')],
          selected: _era,
          onSelect: (v) => setState(() => _era = v),
        ),
        const SizedBox(height: 8),
        // 性别
        _OptRow(
          options: const [('male','男'),('female','女'),('neutral','中性')],
          selected: _gender,
          onSelect: (v) => setState(() => _gender = v),
        ),
        const SizedBox(height: 12),
        // 结果
        GestureDetector(
          onLongPress: _result.isEmpty ? null : () {
            Clipboard.setData(ClipboardData(text: _result));
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('已复制'), duration: Duration(seconds: 1)));
          },
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainer,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              _result.isEmpty ? '—' : _result,
              style: TextStyle(
                color: _result.isEmpty ? const Color(0xFF4b5563) : Colors.white,
                fontSize: 22, fontWeight: FontWeight.w700, letterSpacing: 2,
              ),
              textAlign: TextAlign.center,
            ),
          ),
        ),
        if (_result.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text('长按复制', style: const TextStyle(color: Color(0xFF4b5563), fontSize: 11),
                textAlign: TextAlign.center),
          ),
        const SizedBox(height: 12),
        _GenButton('生成名字', _generate),
      ]),
    );
  }
}

// ── 关系设定生成器 ────────────────────────────────────────────────────────────

class _RelationGenCard extends StatefulWidget {
  const _RelationGenCard();
  @override
  State<_RelationGenCard> createState() => _RelationGenCardState();
}

class _RelationGenCardState extends State<_RelationGenCard> {
  final _aCtrl = TextEditingController();
  final _bCtrl = TextEditingController();
  String _result = '';

  @override
  void dispose() { _aCtrl.dispose(); _bCtrl.dispose(); super.dispose(); }

  static const _relTypes = [
    ('青梅竹马',  ['从小一起长大，彼此是对方最熟悉的陌生人', '幼时形影不离，长大后各奔东西，重逢时才发现心里从未真正放下']),
    ('宿敌',     ['每次相遇都是唇枪舌战，却谁也没办法真正无视对方', '明面上针锋相对，私底下却比任何人都了解彼此的弱点']),
    ('萍水相逢', ['在异乡的雨夜偶然相遇，没有来由地聊了一整夜', '本是擦肩而过的陌生人，命运却一再把两人推向同一个坐标']),
    ('救命之恩', ['一方在对方最灰暗的时刻伸出了手，从此成了对方心里无法归还的债', '恩情太重，反而成了距离——一个不敢靠近，一个不知如何回报']),
    ('前任',     ['曾经以为是一生的人，最后成了彼此最懂又最陌生的存在', '分开的理由说不清楚，再见面时更说不清心里翻涌的是什么']),
    ('主仆/雇佣', ['名分上是主从，相处久了早已界限模糊', '一个习惯了被服侍，一个习惯了付出，直到有一天两人都开始慌乱']),
    ('同门师兄妹', ['同一个师父教出来，功夫一样，脾气却天差地别', '年少时争强好胜，如今同门之情早已胜过血亲']),
    ('政敌/商业对手', ['台面上你来我往，台面下谁也没轻视过对方一分', '赢了对方是目标，但没有这个对手的世界，竟然会让人感到空洞']),
    ('网友/笔友', ['隔着屏幕说过无数心里话，线下见面的那一刻却手足无措', '对方是那个见过最真实自我的人，偏偏从来没见过真实的脸']),
    ('故人之后', ['两人的父辈之间有一段未了的恩怨，这一代的相遇像是命运的续章', '旧人的故事横在两人中间，亲近一分就离那段历史更近一分']),
    ('失忆与被记得', ['一方忘了，另一方什么都还记得，这份记忆的重量只能一个人扛', '甲对乙来说是陌生人，乙对甲来说是整段失去的岁月']),
    ('共同秘密', ['两人意外共享了一个不能说出口的秘密，从此谁也离不开谁', '守着同一个秘密的人，最终会比任何人都了解彼此的底线']),
    ('师徒',     ['一个传授，一个吸收，权力不对等的关系里最容易生出复杂的情感', '甲以为自己在教乙，后来才发现是乙改变了甲']),
    ('邻居/室友', ['近到听得见彼此的脚步声，远到不知道对方在想什么', '某个普通的傍晚，甲突然意识到，乙已经成了一种背景音，少了会不习惯']),
    ('互相救赎', ['甲不知道自己破碎，直到乙到来；乙以为自己无药可救，直到甲出现', '没有谁是光，但两人在一起时，黑暗好像没那么重了']),
  ];

  static const _details = [
    '有一个只有两人知道的暗号或约定','曾经在最狼狈的时候被对方看见过',
    '各自都以为自己付出得更多','有一件事永远没有说清楚，成了两人之间隐形的结',
    '第一印象极差，后来却成了转折点','一方比另一方先动心，自己知道，对方不知道',
    '有过一次彻夜长谈，之后两人关系悄悄变了','共同经历过一件危险或难忘的事',
    '对方的某个小习惯，已经被自己记在心里很久了','曾经误会过对方，后来才明白真相',
    '两人之间有一句话说了一半，永远没说完','甲在乙面前展示过一个不给任何人看的侧面',
    '乙总是在甲最不需要帮助的时候出现，在甲最需要的时候不在',
    '两人曾经在某件事上达成过默契，一个眼神就够了',
    '乙送给甲一件东西，甲一直带着但从未提起',
    '两人都在等对方先开口，结果谁都没有开口',
    '甲有一个脆弱的瞬间，全世界只有乙见过','乙无意间说的一句话，甲记了很久',
    '有人误解过两人的关系，两人都没有解释',
  ];

  void _generate() {
    final r = Random();
    String pick<T>(List<T> l) => l[r.nextInt(l.length)].toString();
    final a  = _aCtrl.text.trim().isEmpty ? '甲' : _aCtrl.text.trim();
    final b  = _bCtrl.text.trim().isEmpty ? '乙' : _bCtrl.text.trim();
    final rel = _relTypes[r.nextInt(_relTypes.length)];
    final d1  = _details[r.nextInt(_details.length)];
    String d2; do { d2 = _details[r.nextInt(_details.length)]; } while (d2 == d1);

    final lines = [
      '关系类型：${rel.$1}',
      '',
      rel.$2[r.nextInt(rel.$2.length)],
      '',
      '细节一：$d1',
      '细节二：$d2',
    ].join('\n').replaceAll('甲', a).replaceAll('乙', b);
    setState(() => _result = lines);
  }

  @override
  Widget build(BuildContext context) {
    return _ToolCard(
      title: '关系设定生成器',
      desc:  '随机生成两个角色之间的背景关系与羁绊细节',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: _MiniField(_aCtrl, '角色甲（选填）')),
          const SizedBox(width: 10),
          Expanded(child: _MiniField(_bCtrl, '角色乙（选填）')),
        ]),
        const SizedBox(height: 12),
        GestureDetector(
          onLongPress: _result.isEmpty ? null : () {
            Clipboard.setData(ClipboardData(text: _result));
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('已复制'), duration: Duration(seconds: 1)));
          },
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainer,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Text(
              _result.isEmpty ? '—' : _result,
              style: TextStyle(
                color: _result.isEmpty ? const Color(0xFF4b5563) : const Color(0xFF9ca3af),
                fontSize: 13, height: 1.8,
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        _GenButton('生成关系', _generate),
      ]),
    );
  }
}

// ── 爱好生成器 ────────────────────────────────────────────────────────────────

class _HobbyGenCard extends StatefulWidget {
  const _HobbyGenCard();
  @override
  State<_HobbyGenCard> createState() => _HobbyGenCardState();
}

class _HobbyGenCardState extends State<_HobbyGenCard> {
  String _result = '';

  static const _hobbies = [
    '读古典文学','写长篇同人','画水彩插画','练书法','写诗','翻译文章','设计字体',
    '剪辑视频','做播客','写剧本','学素描','做手账','制作相册','学油画',
    '弹古筝','玩电子琴','学吉他','玩合成器','研究黑胶唱片',
    '下围棋','玩桌游','拼装模型','玩策略游戏','玩RPG跑团','解密游戏',
    '收集旧邮票','收藏香水','整理胶卷相机','拼乐高',
    '打羽毛球','骑行','徒步爬山','游泳','攀岩','跑步','溜旱冰','打太极','练剑术',
    '煮咖啡','烘焙曲奇','做日式便当','调鸡尾酒','研究茶道','做手工皮具',
    '刺绣','学花道','做蜡烛','制作香皂',
    '研究历史地图','学编程','逛博物馆','研究古代服饰','自学天文学','学手语','学乐理',
    '冥想','练瑜伽','养多肉植物','养猫','观星','逛二手书店','去跳蚤市场',
  ];

  void _generate() {
    final r = Random();
    final n = 3 + r.nextInt(3);
    final list = [..._hobbies]..shuffle(r);
    setState(() => _result = list.take(n).join(' / '));
  }

  @override
  Widget build(BuildContext context) {
    return _ToolCard(
      title: '爱好生成器',
      desc:  '随机给角色分配 3–5 个爱好',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainer, borderRadius: BorderRadius.circular(10)),
          child: Text(_result.isEmpty ? '—' : _result,
            style: TextStyle(
              color: _result.isEmpty ? const Color(0xFF4b5563) : const Color(0xFF9ca3af),
              fontSize: 13, height: 1.7)),
        ),
        const SizedBox(height: 10),
        _GenButton('生成爱好', _generate),
      ]),
    );
  }
}

// ── 性格生成器 ────────────────────────────────────────────────────────────────

class _PersonaGenCard extends StatefulWidget {
  const _PersonaGenCard();
  @override
  State<_PersonaGenCard> createState() => _PersonaGenCardState();
}

class _PersonaGenCardState extends State<_PersonaGenCard> {
  List<String> _tags = [];

  static const _personas = [
    '温柔体贴','冷静理性','热情开朗','内敛深沉','随遇而安','独立自主','完美主义',
    '善解人意','自由散漫','极度自律','感性优先','理性压倒一切','天生乐观','习惯性悲观',
    '清醒且克制','敏锐但不说破','毒舌嘴硬','傲娇在心','刀子嘴豆腐心','口嫌体正直',
    '表面淡漠私下超在意','说话冲但从不真的伤人','占有欲强','依赖型人格','容易共情',
    '情绪化','超级保护欲','容易吃醋','护短','慢热','高冷','外冷内热','神经质式敏感',
    '极度敏感的自尊心','一旦喜欢就缴械投降','把喜欢藏得很深以为没人看出来',
    '越在乎越不敢靠近','天然呆','腹黑一笑','行动派','话少但在意','大方洒脱',
    '习惯默默关心','不擅长拒绝别人','对承诺极度认真','不轻易哭泣','喜欢撒娇但死不承认',
    '表面强硬实则脆弱','习惯把道歉说成玩笑','把关心藏进日常小事里',
    '喜欢掌控感却嘴上说随便','极度怕麻烦别人','记仇但也记恩','讲话直接有时显得莽撞',
    '容易陷入反刍思维','外表迷糊内心精明','想太多导致行动迟缓','直觉很准但喜欢用逻辑说服自己',
    '很少主动但一旦主动就全力以赴','有点社恐但喜欢的人面前变话痨',
    '身上有种说不清的孤独感','笑起来很好看但眼睛不一定跟着笑',
    '偶尔会冒出一句让人心疼的话然后假装没说','帮别人解决问题但自己的事扛着不说',
  ];

  void _generate() {
    final r = Random();
    final n = 5 + r.nextInt(4);
    final list = [..._personas]..shuffle(r);
    setState(() => _tags = list.take(n).toList());
  }

  @override
  Widget build(BuildContext context) {
    return _ToolCard(
      title: '性格生成器',
      desc:  '随机生成 5–8 个性格标签',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          width: double.infinity,
          constraints: const BoxConstraints(minHeight: 60),
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainer, borderRadius: BorderRadius.circular(10)),
          child: _tags.isEmpty
              ? Text('—', style: const TextStyle(color: Color(0xFF4b5563)))
              : Wrap(
                  spacing: 6, runSpacing: 6,
                  children: _tags.map((t) => Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFfb923c).withAlpha(40),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(t, style: const TextStyle(color: Color(0xFFfb923c), fontSize: 12)),
                  )).toList(),
                ),
        ),
        const SizedBox(height: 10),
        _GenButton('生成性格', _generate),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// Tab 2 : 文化人专区
// ══════════════════════════════════════════════════════════════════════════════

class _CultureTab extends StatelessWidget {
  const _CultureTab();
  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: const [
        _FlowerCard(),
        SizedBox(height: 14),
        _GemCard(),
        SizedBox(height: 20),
      ],
    );
  }
}

// ── 花语词典 ──────────────────────────────────────────────────────────────────

class _FlowerData {
  final String name, sub, lang, detail;
  final Color color;
  final List<String> alias;
  const _FlowerData({required this.name, required this.sub, required this.lang,
      required this.detail, required this.color, required this.alias});
}

final _flowers = [
  _FlowerData(name:'玫瑰', sub:'Rosa', lang:'爱情·热情·勇气', color:const Color(0xFFf87171),
      alias:['rose','蔷薇玫瑰'],
      detail:'红玫瑰象征热烈的爱情与深深的敬意；粉玫瑰代表初恋与温柔；白玫瑰代表纯洁与尊重。'),
  _FlowerData(name:'百合', sub:'Lilium', lang:'纯洁·优雅·庄严', color:const Color(0xFFf0fdf4),
      alias:['lily','白百合'],
      detail:'白百合是圣母玛利亚的象征，代表纯洁与神圣；在中国文化中百合寓意"百年好合"。'),
  _FlowerData(name:'樱花', sub:'Prunus serrulata', lang:'生命之无常·纯洁的爱·别离', color:const Color(0xFFfda4af),
      alias:['cherry blossom','山樱','吉野樱'],
      detail:'樱花盛开不过一两周，日本文化中象征武士道精神"刹那即永恒"，也代表青春的短暂美丽。'),
  _FlowerData(name:'向日葵', sub:'Helianthus annuus', lang:'忠诚·崇拜·热情', color:const Color(0xFFfbbf24),
      alias:['sunflower','太阳花'],
      detail:'向日葵始终朝向阳光，象征对光明的追随与忠诚的心。在西方花语中也代表"我只仰望你"。'),
  _FlowerData(name:'郁金香', sub:'Tulipa', lang:'完美的爱·荣誉', color:const Color(0xFFf472b6),
      alias:['tulip'],
      detail:'红郁金香是"热烈的爱的宣言"；紫郁金香代表无尽的爱；白郁金香象征纯洁与宽恕。'),
  _FlowerData(name:'风信子', sub:'Hyacinthus orientalis', lang:'游戏·嫉妒·悲伤中的胜出', color:const Color(0xFF818cf8),
      alias:['hyacinth','洋水仙'],
      detail:'源自希腊神话：阿波罗挚爱的美少年雅辛托斯意外死去，从其血液中生长出风信子。'),
  _FlowerData(name:'薰衣草', sub:'Lavandula', lang:'等待·宁静·优雅的爱', color:const Color(0xFFa78bfa),
      alias:['lavender','拉文德'],
      detail:'薰衣草的紫色象征等待中的心，以及对爱情的忠诚守候。普罗旺斯的薰衣草田是浪漫的代名词。'),
  _FlowerData(name:'茉莉', sub:'Jasminum', lang:'爱情·柔情·优雅', color:const Color(0xFFf5f5f4),
      alias:['jasmine','茉莉花'],
      detail:'茉莉洁白芬芳，在东方文化中是纯洁爱情的象征；在波斯文化中茉莉是"神之花"。'),
  _FlowerData(name:'莲花', sub:'Nelumbo nucifera', lang:'出淤泥而不染·圣洁·重生', color:const Color(0xFFf9a8d4),
      alias:['lotus','荷花','睡莲'],
      detail:'莲花生于淤泥却洁白无瑕，是佛教圣洁的象征，也代表君子的高洁品格。'),
  _FlowerData(name:'梅花', sub:'Prunus mume', lang:'坚韧·高洁·不屈', color:const Color(0xFFfda4af),
      alias:['plum blossom','红梅','腊梅'],
      detail:'梅花在严冬独自绽放，与松、竹并称"岁寒三友"，象征在逆境中坚守气节的君子品格。'),
  _FlowerData(name:'牡丹', sub:'Paeonia suffruticosa', lang:'富贵·雍容·圆满', color:const Color(0xFFf9a8d4),
      alias:['peony','国色天香'],
      detail:'牡丹是中国的"国花"候选，古称"花王"，象征繁荣、富贵与圆满。'),
  _FlowerData(name:'勿忘我', sub:'Myosotis', lang:'永恒的记忆·请不要忘记我', color:const Color(0xFF93c5fd),
      alias:['forget-me-not','勿忘草'],
      detail:'传说一位骑士在河边为爱人采花，不慎落水，临死前将花抛给爱人说"forget me not"。'),
  _FlowerData(name:'雏菊', sub:'Bellis perennis', lang:'纯真·希望·我会想你', color:const Color(0xFFfef3c7),
      alias:['daisy','延命菊'],
      detail:'雏菊花瓣游戏"爱我·不爱我"源于欧洲民间，象征对爱情的纯真期待与童年的美好。'),
  _FlowerData(name:'紫罗兰', sub:'Viola', lang:'永恒的美·羞涩·心中的秘密', color:const Color(0xFFa78bfa),
      alias:['violet','香堇菜'],
      detail:'紫罗兰是古希腊雅典的市花，拿破仑最爱的花，代表低调中的永恒之美与深藏的爱意。'),
  _FlowerData(name:'彼岸花', sub:'Lycoris radiata', lang:'悲伤的回忆·相见在彼岸·永别', color:const Color(0xFFdc2626),
      alias:['red spider lily','曼珠沙华','石蒜'],
      detail:'佛教传说中彼岸花开在通往冥界的路上，花叶永不相见。象征爱而不得的凄美与彼岸重逢的渴望。'),
  _FlowerData(name:'迷迭香', sub:'Rosmarinus officinalis', lang:'记忆·忠诚·思念你', color:const Color(0xFF4ade80),
      alias:['rosemary','海露珠'],
      detail:'莎士比亚《哈姆雷特》中奥菲利娅说"迷迭香，是为了帮助记忆"，自古便是记忆与忠诚的象征。'),
  _FlowerData(name:'丁香', sub:'Syringa', lang:'初恋·青涩的心动·无悔的等待', color:const Color(0xFFc4b5fd),
      alias:['lilac','紫丁香'],
      detail:'戴望舒《雨巷》中"丁香一样的姑娘"将丁香定格为含苞待放的初恋意象。'),
  _FlowerData(name:'桃花', sub:'Prunus persica', lang:'爱情运势·桃花运·春日缘分', color:const Color(0xFFfda4af),
      alias:['peach blossom','碧桃'],
      detail:'"桃花运"一词源于桃花象征浪漫缘分。春日桃花纷飞是无数诗人最爱的意象。'),
  _FlowerData(name:'绣球花', sub:'Hydrangea macrophylla', lang:'善变·希望·青春的喜悦', color:const Color(0xFF93c5fd),
      alias:['hydrangea','八仙花'],
      detail:'绣球花会随土壤酸碱度改变颜色，在日本花语中蓝色绣球代表谦虚与辛勤。'),
  _FlowerData(name:'芍药', sub:'Paeonia lactiflora', lang:'惜别·含羞·思念', color:const Color(0xFFfda4af),
      alias:['Chinese peony','将离'],
      detail:'古称"将离"，是古人送别时的赠花。《诗经》中"赠之以芍药"即是情人的定情之礼。'),
];

class _FlowerCard extends StatefulWidget {
  const _FlowerCard();
  @override
  State<_FlowerCard> createState() => _FlowerCardState();
}

class _FlowerCardState extends State<_FlowerCard> {
  final _searchCtrl = TextEditingController();
  _FlowerData? _result;
  bool _notFound = false;

  @override
  void dispose() { _searchCtrl.dispose(); super.dispose(); }

  void _lookup() {
    final q = _searchCtrl.text.trim().toLowerCase();
    if (q.isEmpty) { _lucky(); return; }
    final match = _flowers.where((f) =>
      f.name.contains(q) || q.contains(f.name) ||
      f.alias.any((a) => a.toLowerCase().contains(q) || q.contains(a.toLowerCase()))
    ).firstOrNull;
    setState(() { _result = match; _notFound = match == null; });
  }

  void _lucky() {
    final f = _flowers[Random().nextInt(_flowers.length)];
    _searchCtrl.clear();
    setState(() { _result = f; _notFound = false; });
  }

  @override
  Widget build(BuildContext context) {
    return _ToolCard(
      title: '🌺 花语词典',
      desc:  '输入花名查询花语，或点击「随便来一个」探索',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: TextField(
            controller: _searchCtrl,
            style: const TextStyle(),
            onSubmitted: (_) => _lookup(),
            decoration: InputDecoration(
              hintText: '玫瑰、樱花、薰衣草……',
              hintStyle: const TextStyle(color: Color(0xFF4b5563)),
              filled: true, fillColor: const Color(0xFF1a1a2e),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            ),
          )),
          const SizedBox(width: 8),
          _SmallButton('查询', _lookup, const Color(0xFF8b7cf6)),
          const SizedBox(width: 6),
          _SmallButton('🎲', _lucky, const Color(0xFF374151)),
        ]),
        const SizedBox(height: 12),
        if (_notFound)
          const Text('没有找到对应的花语，换个词试试？',
              style: TextStyle(color: Color(0xFF6b7280), fontSize: 13)),
        if (_result != null) _FlowerResult(f: _result!),
      ]),
    );
  }
}

class _FlowerResult extends StatelessWidget {
  final _FlowerData f;
  const _FlowerResult({required this.f});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: f.color.withAlpha(80)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(f.name, style: TextStyle(color: f.color, fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(width: 10),
          Text(f.sub, style: const TextStyle(color: Color(0xFF6b7280), fontSize: 11)),
        ]),
        const SizedBox(height: 6),
        Text('花语：${f.lang}', style: TextStyle(color: f.color, fontSize: 13, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Text(f.detail, style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 13, height: 1.7)),
      ]),
    );
  }
}

// ── 宝石图鉴 ──────────────────────────────────────────────────────────────────

class _GemData {
  final String name, en, meaning, detail;
  final Color color;
  final List<String> tags;
  const _GemData({required this.name, required this.en, required this.meaning,
      required this.detail, required this.color, required this.tags});
}

final _gems = [
  _GemData(name:'红宝石', en:'Ruby', color:const Color(0xFFdc2626), meaning:'热情·勇气·永恒的爱',
      detail:'被誉为"宝石之王"，深红色象征炽热的爱与无畏的勇气。7月生辰石，代表高贵与忠诚。', tags:['7月生辰石','硬度9','刚玉族']),
  _GemData(name:'蓝宝石', en:'Sapphire', color:const Color(0xFF2563eb), meaning:'智慧·忠诚·神圣',
      detail:'古代祭司和国王认为蓝宝石代表天堂的颜色，象征神圣的保护。戴安娜王妃的订婚戒指镶嵌了缅甸蓝宝石。9月生辰石。', tags:['9月生辰石','硬度9','刚玉族']),
  _GemData(name:'祖母绿', en:'Emerald', color:const Color(0xFF059669), meaning:'重生·希望·永恒的春天',
      detail:'古埃及艳后克利奥帕特拉酷爱祖母绿。深绿色象征生命力的永续与春天的重生。5月生辰石。', tags:['5月生辰石','硬度7.5-8','绿柱石族']),
  _GemData(name:'钻石', en:'Diamond', color:const Color(0xFFe2e8f0), meaning:'永恒·纯洁·无与伦比的爱',
      detail:'"钻石恒久远，一颗永流传"。钻石是自然界最坚硬的物质，象征永不磨灭的爱情与誓言。4月生辰石。', tags:['4月生辰石','硬度10','碳元素']),
  _GemData(name:'翡翠', en:'Jade (Jadeite)', color:const Color(0xFF16a34a), meaning:'长寿·健康·君子之德',
      detail:'中华文明中最重要的宝石，"君子无故，玉不去身"。满绿的"帝王绿"极为珍贵。', tags:['缅甸产','硬度6.5-7','辉石族']),
  _GemData(name:'珍珠', en:'Pearl', color:const Color(0xFFf8fafc), meaning:'纯洁·智慧·月之泪',
      detail:'古罗马人视珍珠为最高贵的宝石。6月生辰石，象征纯洁、智慧与隐忍之美——经历了沙粒的磨砺才成就圆润。', tags:['6月生辰石','有机宝石','海水/淡水']),
  _GemData(name:'紫水晶', en:'Amethyst', color:const Color(0xFF7c3aed), meaning:'平静·保护·清醒',
      detail:'希腊文amethystos意为"不醉"，古人相信紫水晶能防止醉酒与冲动。2月生辰石。', tags:['2月生辰石','硬度7','石英族']),
  _GemData(name:'月光石', en:'Moonstone', color:const Color(0xFFbfdbfe), meaning:'直觉·新的开始·女性之力',
      detail:'月光石内部有蓝白色光晕随角度流动如月光，代表直觉与感知力的增强。', tags:['6月生辰石','硬度6-6.5','长石族']),
  _GemData(name:'青金石', en:'Lapis Lazuli', color:const Color(0xFF1d4ed8), meaning:'智慧·皇权·星空',
      detail:'古埃及人将青金石研磨成颜料绘制壁画，是法老的专用宝石。梵高《星夜》中那片深蓝便是它的颜色。', tags:['不透明宝石','硬度5-6','含方解石金点']),
  _GemData(name:'粉晶', en:'Rose Quartz', color:const Color(0xFFfda4af), meaning:'无条件的爱·温柔·自我疗愈',
      detail:'粉晶被称为"爱情石"，象征无条件的爱与内心的柔软。现代水晶疗愈中粉晶对应心轮，帮助疗愈情感创伤。', tags:['硬度7','石英族','常见产于巴西']),
  _GemData(name:'黑曜石', en:'Obsidian', color:const Color(0xFF1c1917), meaning:'保护·揭示真相·破除幻象',
      detail:'黑曜石是火山熔岩急速冷却形成的天然玻璃，阿兹特克祭司用它作神圣镜子以窥见真相。', tags:['火山岩玻璃','硬度5-5.5','天然玻璃']),
  _GemData(name:'琥珀', en:'Amber', color:const Color(0xFFd97706), meaning:'时间·疗愈·被封存的温柔',
      detail:'琥珀是数千万年前的树脂化石，偶有昆虫被封存其中。波罗的海沿岸古代人视琥珀为"北方黄金"。', tags:['有机宝石','8月生辰石之一','最古老宝石']),
  _GemData(name:'海蓝宝石', en:'Aquamarine', color:const Color(0xFF38bdf8), meaning:'清明·勇气·海洋的祝福',
      detail:'名字来源于拉丁文"海水"，古代水手携带它以保佑平安渡海。蓝绿色象征平静的心境与清晰的思维。3月生辰石。', tags:['3月生辰石','硬度7.5-8','绿柱石族']),
  _GemData(name:'欧泊', en:'Opal', color:const Color(0xFFa855f7), meaning:'创造力·变幻·希望之彩',
      detail:'欧泊是唯一会变色的宝石，一颗欧泊中藏有所有颜色，古罗马人称其为"宝石之祖"。10月生辰石。', tags:['10月生辰石','含水二氧化硅','变彩效应']),
  _GemData(name:'绿松石', en:'Turquoise', color:const Color(0xFF0d9488), meaning:'守护·幸运·友谊',
      detail:'人类最古老的护身宝石之一，古埃及、波斯、阿兹特克文明都视之为神圣。12月生辰石。', tags:['12月生辰石','硬度5-6','古老护身石']),
  _GemData(name:'虎眼石', en:"Tiger's Eye", color:const Color(0xFFb45309), meaning:'专注·毅力·大地之力',
      detail:'虎眼石内部有金色丝状光带随光线流动，如猛虎的眼睛。古罗马士兵随身携带以增添勇气。', tags:['硬度7','石英族','丝绢光泽']),
  _GemData(name:'孔雀石', en:'Malachite', color:const Color(0xFF15803d), meaning:'转变·冒险·守护心脏',
      detail:'孔雀石以绿色同心圆花纹著称，古埃及人将其研磨成绿色眼影，象征成长与转变。', tags:['硬度3.5-4','碳酸铜','不透明宝石']),
  _GemData(name:'拉长石', en:'Labradorite', color:const Color(0xFF475569), meaning:'神秘·魔法·北极光',
      detail:'拉长石外表灰暗，转动角度却爆发出蓝绿金紫的彩虹光晕。因纽特传说中这是被困在石头里的极光。', tags:['硬度6-6.5','长石族','晕彩效应']),
  _GemData(name:'碧玺', en:'Tourmaline', color:const Color(0xFFec4899), meaning:'创造·情感平衡·彩虹之石',
      detail:'碧玺是颜色最丰富的宝石，清代慈禧太后极爱碧玺。"西瓜碧玺"外红内绿如切开的西瓜，是极品。', tags:['10月生辰石','硬度7-7.5','复杂硅酸盐']),
  _GemData(name:'红纹石', en:'Rhodochrosite', color:const Color(0xFFf43f5e), meaning:'爱的复苏·怜悯·情感疗愈',
      detail:'红纹石以粉红色和白色条纹交织而成，阿根廷土著称其为"印加玫瑰"。象征对受伤心灵的温柔抚慰。', tags:['硬度3.5-4','碳酸锰','印加玫瑰']),
];

class _GemCard extends StatefulWidget {
  const _GemCard();
  @override
  State<_GemCard> createState() => _GemCardState();
}

class _GemCardState extends State<_GemCard> {
  _GemData? _selected;

  @override
  Widget build(BuildContext context) {
    return _ToolCard(
      title: '💎 宝石图鉴',
      desc:  '点击宝石查看象征含义与传说',
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Wrap(
          spacing: 8, runSpacing: 8,
          children: _gems.map((g) {
            final active = g == _selected;
            return GestureDetector(
              onTap: () => setState(() => _selected = active ? null : g),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: g.color.withAlpha(active ? 50 : 25),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: g.color.withAlpha(active ? 180 : 80)),
                ),
                child: Row(mainAxisSize: MainAxisSize.min, children: [
                  Container(width: 9, height: 9,
                      decoration: BoxDecoration(color: g.color, shape: BoxShape.circle)),
                  const SizedBox(width: 6),
                  Text(g.name, style: TextStyle(color: g.color, fontSize: 12)),
                ]),
              ),
            );
          }).toList(),
        ),
        if (_selected != null) ...[
          const SizedBox(height: 14),
          _GemDetail(g: _selected!),
        ],
      ]),
    );
  }
}

class _GemDetail extends StatelessWidget {
  final _GemData g;
  const _GemDetail({required this.g});
  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: g.color.withAlpha(80)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(width: 32, height: 32,
              decoration: BoxDecoration(color: g.color, shape: BoxShape.circle)),
          const SizedBox(width: 12),
          Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(g.name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            Text(g.en, style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
          ]),
        ]),
        const SizedBox(height: 10),
        Text('象征：${g.meaning}', style: TextStyle(color: g.color, fontSize: 13, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Text(g.detail, style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 13, height: 1.7)),
        const SizedBox(height: 10),
        Wrap(spacing: 6, runSpacing: 6, children: g.tags.map((t) => Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
          decoration: BoxDecoration(
            color: g.color.withAlpha(30),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: g.color.withAlpha(80)),
          ),
          child: Text(t, style: TextStyle(color: g.color, fontSize: 11)),
        )).toList()),
      ]),
    );
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// 公共 Widget
// ══════════════════════════════════════════════════════════════════════════════

class _ToolCard extends StatelessWidget {
  final String title, desc;
  final Widget child;
  const _ToolCard({required this.title, required this.desc, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF374151)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        const SizedBox(height: 4),
        Text(desc, style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
        const SizedBox(height: 14),
        child,
      ]),
    );
  }
}

class _OptRow extends StatelessWidget {
  final List<(String, String)> options;
  final String selected;
  final void Function(String) onSelect;
  const _OptRow({required this.options, required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      children: options.map((o) {
        final active = o.$1 == selected;
        return GestureDetector(
          onTap: () => onSelect(o.$1),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
            decoration: BoxDecoration(
              color: active ? const Color(0xFFfb923c) : const Color(0xFF1a1a2e),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: active ? const Color(0xFFfb923c) : const Color(0xFF374151)),
            ),
            child: Text(o.$2, style: TextStyle(
              color: active ? Colors.white : const Color(0xFF9ca3af),
              fontSize: 13,
            )),
          ),
        );
      }).toList(),
    );
  }
}

class _GenButton extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  const _GenButton(this.label, this.onTap);
  @override
  Widget build(BuildContext context) => ElevatedButton(
    style: ElevatedButton.styleFrom(
      backgroundColor: const Color(0xFFfb923c),
      foregroundColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 10),
      elevation: 0,
    ),
    onPressed: onTap,
    child: Text(label, style: const TextStyle(fontSize: 13)),
  );
}

class _SmallButton extends StatelessWidget {
  final String label;
  final VoidCallback onTap;
  final Color color;
  const _SmallButton(this.label, this.onTap, this.color);
  @override
  Widget build(BuildContext context) => ElevatedButton(
    style: ElevatedButton.styleFrom(
      backgroundColor: color,
      foregroundColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      elevation: 0,
      minimumSize: Size.zero,
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    ),
    onPressed: onTap,
    child: Text(label, style: const TextStyle(fontSize: 13)),
  );
}

class _MiniField extends StatelessWidget {
  final TextEditingController ctrl;
  final String hint;
  const _MiniField(this.ctrl, this.hint);
  @override
  Widget build(BuildContext context) => TextField(
    controller: ctrl,
    style: const TextStyle(fontSize: 13),
    decoration: InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(color: Color(0xFF4b5563), fontSize: 13),
      filled: true, fillColor: const Color(0xFF1a1a2e),
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8), borderSide: BorderSide.none),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
    ),
  );
}
