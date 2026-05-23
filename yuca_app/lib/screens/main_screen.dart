import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/auth_service.dart';
import '../services/api_service.dart';
import '../utils/theme_utils.dart';
import '../services/notification_service.dart';
import 'calendar_screen.dart';
import 'guild_screen.dart';
import 'reports_screen.dart';
import 'toolbox/diary_screen.dart';
import 'toolbox/wishlist_screen.dart';
import 'toolbox/partners_screen.dart';
import 'toolbox/blacklist_screen.dart';
import 'toolbox/tools_screen.dart';
import 'toolbox/card_screen.dart';

class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  int _currentIndex = 0;

  final List<Widget> _screens = [
    const CalendarScreen(),
    const GuildScreen(),
    const ToolboxScreen(),
    const StatsScreen(),
    const ProfileScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final accent = themeToColor(context.watch<AuthService>().user?.theme);
    return Scaffold(
      body: IndexedStack(
        index: _currentIndex,
        children: _screens,
      ),
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _currentIndex,
        onTap: (i) => setState(() => _currentIndex = i),
        type: BottomNavigationBarType.fixed,
        backgroundColor: Theme.of(context).colorScheme.surfaceContainer,
        selectedItemColor: accent,
        unselectedItemColor: Theme.of(context).colorScheme.onSurface.withAlpha(100),
        selectedFontSize: 11,
        unselectedFontSize: 11,
        items: const [
          BottomNavigationBarItem(
              icon: Icon(Icons.calendar_month), label: '日历'),
          BottomNavigationBarItem(
              icon: Icon(Icons.groups_outlined), label: '公会·戏录'),
          BottomNavigationBarItem(
              icon: Icon(Icons.auto_awesome_outlined), label: '百宝箱'),
          BottomNavigationBarItem(
              icon: Icon(Icons.bar_chart_outlined), label: '统计'),
          BottomNavigationBarItem(
              icon: Icon(Icons.person_outline), label: '我的'),
        ],
      ),
    );
  }
}

// ── 公会 & 戏录 ──────────────────────────────────────────────────────────────────

class GuildDramaScreen extends StatefulWidget {
  const GuildDramaScreen({super.key});

  @override
  State<GuildDramaScreen> createState() => _GuildDramaScreenState();
}

class _GuildDramaScreenState extends State<GuildDramaScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tab;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('公会 & 戏录',
            style: TextStyle()),
        bottom: TabBar(
          controller: _tab,
          tabs: const [
            Tab(text: '公会'),
            Tab(text: '戏录'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tab,
        children: const [
          _ComingSoon(icon: Icons.groups, label: '公会'),
          _ComingSoon(icon: Icons.auto_stories_outlined, label: '戏录'),
        ],
      ),
    );
  }
}

// ── 百宝箱 ───────────────────────────────────────────────────────────────────────

class ToolboxScreen extends StatelessWidget {
  const ToolboxScreen({super.key});

  @override
  Widget build(BuildContext context) {
    // watch AuthService → 主题切换时自动重建
    final accent = themeToColor(context.watch<AuthService>().user?.theme);
    final cs     = Theme.of(context).colorScheme;

    final items = [
      _ToolItem(Icons.book_outlined,     '日记',    const Color(0xFF60a5fa),
          () => Navigator.push(context, MaterialPageRoute(builder: (_) => const DiaryScreen()))),
      _ToolItem(Icons.star_outline,      '心愿单',  const Color(0xFFfbbf24),
          () => Navigator.push(context, MaterialPageRoute(builder: (_) => const WishlistScreen()))),
      _ToolItem(Icons.people_outline,    '必吃榜',  const Color(0xFF34d399),
          () => Navigator.push(context, MaterialPageRoute(builder: (_) => const PartnersScreen()))),
      _ToolItem(Icons.block_outlined,    '黑名单',  const Color(0xFFf87171),
          () => Navigator.push(context, MaterialPageRoute(builder: (_) => const BlacklistScreen()))),
      _ToolItem(Icons.style_outlined,    '卡救星',  const Color(0xFFfb923c),
          () => Navigator.push(context, MaterialPageRoute(builder: (_) => const CardScreen()))),
      _ToolItem(Icons.timeline_outlined, '时间轴',  const Color(0xFFa78bfa), () {}),
      _ToolItem(Icons.build_outlined,    '小工具',  const Color(0xFFfb923c),
          () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ToolsScreen()))),
      _ToolItem(Icons.flag_outlined,     '公开检举', const Color(0xFFe879f9),
          () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ReportsScreen()))),
    ];

    return Scaffold(
      appBar: AppBar(
        title: const Text('百宝箱'),
      ),
      body: GridView.builder(
        padding: const EdgeInsets.all(16),
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 3,
          crossAxisSpacing: 12,
          mainAxisSpacing: 12,
          childAspectRatio: 1,
        ),
        itemCount: items.length,
        itemBuilder: (ctx, i) {
          final item = items[i];
          return GestureDetector(
            onTap: item.onTap,
            child: Container(
              decoration: BoxDecoration(
                // 背景：用 surfaceContainer 加上一点 accent 色调
                color: Color.lerp(cs.surfaceContainer, accent, 0.06),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: accent.withAlpha(90), width: 1.2),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Container(
                    width: 48, height: 48,
                    decoration: BoxDecoration(
                      color: item.color.withAlpha(35),
                      shape: BoxShape.circle,
                      border: Border.all(color: item.color.withAlpha(60)),
                    ),
                    child: Icon(item.icon, color: item.color, size: 24),
                  ),
                  const SizedBox(height: 10),
                  Text(item.label,
                      style: TextStyle(
                          color: cs.onSurface,
                          fontSize: 13,
                          fontWeight: FontWeight.w500)),
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}

class _ToolItem {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _ToolItem(this.icon, this.label, this.color, this.onTap);
}

// ── 年度统计 ─────────────────────────────────────────────────────────────────────

class StatsScreen extends StatefulWidget {
  const StatsScreen({super.key});

  @override
  State<StatsScreen> createState() => _StatsScreenState();
}

class _StatsScreenState extends State<StatsScreen> {
  int _year = DateTime.now().year;
  bool _loading = true;
  String? _error;
  Map<String, dynamic>? _data;
  List<int> _years = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final auth = context.read<AuthService>();
      final resp = await ApiService(auth).getStats(_year);
      if (!mounted) return;
      final stats = resp['stats'] as Map<String, dynamic>;
      // 从 involved 列表推断可用年份
      if (_years.isEmpty) {
        final now = DateTime.now().year;
        _years = List.generate(math.max(0, now - 2023), (i) => now - i)
            .where((y) => y >= 2024).toList();
        if (!_years.contains(now)) _years.insert(0, now);
      }
      setState(() { _data = stats; _loading = false; });
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = '加载失败，请重试'; _loading = false; });
    }
  }

  Color _hexColor(String hex) {
    try { return Color(int.parse(hex.replaceFirst('#', '0xFF'))); }
    catch (_) { return const Color(0xFF8b7cf6); }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('年度统计', style: TextStyle()),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(_error!, style: const TextStyle(color: Color(0xFF9ca3af))),
                    const SizedBox(height: 16),
                    ElevatedButton(
                      onPressed: _load,
                      child: const Text('重试'),
                    ),
                  ],
                ))
              : _buildBody(),
    );
  }

  Widget _buildBody() {
    final data = _data!;
    final total = data['total'] as int? ?? 0;
    final label = data['label'] as String? ?? '$_year年';

    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── 年份选择 ──────────────────────────────────────────
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: _years.map((y) {
                final active = y == _year;
                final accent = themeToColor(context.read<AuthService>().user?.theme);
                final cs = Theme.of(context).colorScheme;
                return GestureDetector(
                  onTap: active ? null : () { setState(() => _year = y); _load(); },
                  child: Container(
                    margin: const EdgeInsets.only(right: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                    decoration: BoxDecoration(
                      color: active ? accent : cs.surfaceContainer,
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: active ? accent : cs.onSurface.withAlpha(50),
                      ),
                    ),
                    child: Text('$y年',
                        style: TextStyle(
                            color: active ? cs.onPrimary : cs.onSurface.withAlpha(180),
                            fontSize: 13)),
                  ),
                );
              }).toList(),
            ),
          ),
          const SizedBox(height: 20),

          if (total == 0) ...[
            Center(child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 48),
              child: Text('$label暂无档期数据',
                  style: const TextStyle(color: Color(0xFF6b7280))),
            )),
          ] else ...[
            // ── 数字概览 ──────────────────────────────────────
            _StatsOverview(data: data),
            const SizedBox(height: 14),

            // ── 天数进度 ──────────────────────────────────────
            _DayProgressCard(data: data),
            const SizedBox(height: 14),

            // ── 涉及恋综 ──────────────────────────────────────
            _InvolvedCard(data: data, hexColor: _hexColor),
            const SizedBox(height: 14),

            // ── 两列分布 ──────────────────────────────────────
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(child: _DistribCard(
                title: '🎭 皮相使用',
                items: (data['characters'] as List<dynamic>? ?? [])
                    .map((c) => c as Map<String, dynamic>)
                    .toList(),
                isChars: true,
              )),
              const SizedBox(width: 12),
              Expanded(child: _DistribCard(
                title: '🎨 主题题材',
                items: (data['themes'] as List<dynamic>? ?? [])
                    .map((c) => c as Map<String, dynamic>)
                    .toList(),
                barColor: const Color(0xFF8b7cf6),
              )),
            ]),
            const SizedBox(height: 12),
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Expanded(child: _DistribCard(
                title: '❤️ 性向分布',
                items: (data['orientations'] as List<dynamic>? ?? [])
                    .map((c) => c as Map<String, dynamic>)
                    .toList(),
                barColor: const Color(0xFFf472b6),
              )),
              const SizedBox(width: 12),
              Expanded(child: _DistribCard(
                title: '🚻 性别分布',
                items: (data['genders'] as List<dynamic>? ?? [])
                    .map((c) => c as Map<String, dynamic>)
                    .toList(),
                barColor: const Color(0xFF34d399),
              )),
            ]),
            const SizedBox(height: 12),
            _DistribCard(
              title: '🎬 结局分布',
              items: (data['outcomes'] as List<dynamic>? ?? [])
                  .map((c) => c as Map<String, dynamic>)
                  .toList(),
              barColor: const Color(0xFFfbbf24),
              fullWidth: true,
            ),
          ],
        ],
      ),
    );
  }
}

class _StatsOverview extends StatelessWidget {
  final Map<String, dynamic> data;
  const _StatsOverview({required this.data});

  @override
  Widget build(BuildContext context) {
    final total   = data['total']        as int?    ?? 0;
    final covered = data['covered_days'] as int?    ?? 0;
    final pct     = data['pct']          as double? ?? 0.0;
    final weekend = data['weekend']      as int?    ?? 0;

    return Row(children: [
      _Stat(num: '$total',    label: '涉及恋综'),
      const SizedBox(width: 10),
      _Stat(num: '$covered',  label: '语擦天数'),
      const SizedBox(width: 10),
      _Stat(num: '$pct%',     label: '占比'),
      const SizedBox(width: 10),
      _Stat(num: '$weekend',  label: '周末语擦'),
    ]);
  }
}

class _Stat extends StatelessWidget {
  final String num, label;
  const _Stat({required this.num, required this.label});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: cs.surfaceContainer,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: cs.primary.withAlpha(70)),
        ),
        child: Column(children: [
          Text(num, style: TextStyle(
              color: themeToColor(context.watch<AuthService>().user?.theme), fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 4),
          Text(label, style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 11)),
        ]),
      ),
    );
  }
}

class _DayProgressCard extends StatelessWidget {
  final Map<String, dynamic> data;
  const _DayProgressCard({required this.data});

  @override
  Widget build(BuildContext context) {
    final covered   = data['covered_days'] as int?    ?? 0;
    final total     = data['total_days']   as int?    ?? 1;
    final pct       = data['pct']          as double? ?? 0.0;
    final weekday   = data['weekday']      as int?    ?? 0;
    final weekend   = data['weekend']      as int?    ?? 0;
    final label     = data['label']        as String? ?? '';
    final free      = total - covered;

    final cs = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: cs.primary.withAlpha(70)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('📅 $label语擦天数',
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
        const SizedBox(height: 10),
        Text('共 $total 天中，有档期覆盖 $covered 天（$pct%）',
            style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 13)),
        const SizedBox(height: 10),
        ClipRRect(
          borderRadius: BorderRadius.circular(6),
          child: LinearProgressIndicator(
            value: pct / 100,
            minHeight: 10,
            backgroundColor: const Color(0xFF374151),
            valueColor: AlwaysStoppedAnimation(
              themeToColor(context.watch<AuthService>().user?.theme),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Row(children: [
          _Tag('周中 $weekday 天', const Color(0xFF9ca3af)),
          const SizedBox(width: 12),
          _Tag('周末 $weekend 天', const Color(0xFF9ca3af)),
          const SizedBox(width: 12),
          _Tag('空闲 $free 天',   const Color(0xFF9ca3af)),
        ]),
      ]),
    );
  }
}

class _Tag extends StatelessWidget {
  final String text;
  final Color color;
  const _Tag(this.text, this.color);
  @override
  Widget build(BuildContext context) =>
      Text(text, style: TextStyle(color: color, fontSize: 12));
}

class _InvolvedCard extends StatelessWidget {
  final Map<String, dynamic> data;
  final Color Function(String) hexColor;
  const _InvolvedCard({required this.data, required this.hexColor});

  @override
  Widget build(BuildContext context) {
    final involved = data['involved'] as List<dynamic>? ?? [];
    final cs = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: cs.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: cs.primary.withAlpha(70)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('📌 涉及的恋综（${involved.length} 个）',
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: involved.map((s) {
            final m = s as Map<String, dynamic>;
            final c = hexColor(m['color'] as String? ?? '#8b7cf6');
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: c.withOpacity(0.12),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: c.withOpacity(0.35)),
              ),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Container(width: 7, height: 7,
                    decoration: BoxDecoration(color: c, shape: BoxShape.circle)),
                const SizedBox(width: 6),
                Text(m['show_name'] as String? ?? '',
                    style: const TextStyle(fontSize: 12)),
              ]),
            );
          }).toList(),
        ),
      ]),
    );
  }
}

class _DistribCard extends StatelessWidget {
  final String title;
  final List<Map<String, dynamic>> items;
  final bool isChars;
  final Color barColor;
  final bool fullWidth;

  const _DistribCard({
    required this.title,
    required this.items,
    this.isChars = false,
    this.barColor = const Color(0xFF8b7cf6),
    this.fullWidth = false,
  });

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Container(
      width: fullWidth ? double.infinity : null,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: cs.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: cs.primary.withAlpha(70)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        const SizedBox(height: 12),
        if (items.isEmpty)
          const Text('无记录', style: TextStyle(color: Color(0xFF6b7280), fontSize: 12))
        else if (isChars)
          ...items.map((c) => Padding(
            padding: const EdgeInsets.only(bottom: 6),
            child: Row(children: [
              Expanded(child: Text(c['name'] as String? ?? '',
                  style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 12),
                  overflow: TextOverflow.ellipsis)),
              Text(c['char'] as String? ?? '',
                  style: const TextStyle(fontSize: 12)),
            ]),
          ))
        else
          ...items.map((item) {
            final pct   = (item['pct'] as num?)?.toDouble() ?? 0.0;
            final count = item['count'] as int? ?? 0;
            final value = item['value'] as String? ?? '';
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(child: Text(value,
                      style: const TextStyle(fontSize: 12))),
                  Text('$count · $pct%',
                      style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 11)),
                ]),
                const SizedBox(height: 4),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: pct / 100,
                    minHeight: 6,
                    backgroundColor: const Color(0xFF374151),
                    valueColor: AlwaysStoppedAnimation(barColor),
                  ),
                ),
              ]),
            );
          }),
      ]),
    );
  }
}

// ── 我的 ─────────────────────────────────────────────────────────────────────────

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});
  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  Map<String, dynamic>? _stats;
  bool _statsLoading = true;

  @override
  void initState() {
    super.initState();
    _loadStats();
  }

  Future<void> _loadStats() async {
    try {
      final auth = context.read<AuthService>();
      final resp = await ApiService(auth).getStats(DateTime.now().year);
      if (!mounted) return;
      setState(() { _stats = resp['stats'] as Map<String, dynamic>?; _statsLoading = false; });
    } catch (_) {
      if (!mounted) return;
      setState(() => _statsLoading = false);
    }
  }

  void _showFeedback(BuildContext context) {
    final typeNotifier = ValueNotifier<String>('bug');
    final ctrl = TextEditingController();
    bool sending = false;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surfaceContainer,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(bottom: MediaQuery.of(ctx).viewInsets.bottom),
        child: StatefulBuilder(
          builder: (ctx, setState) => Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 把手
              Center(
                child: Container(
                  margin: const EdgeInsets.only(top: 12, bottom: 8),
                  width: 36, height: 4,
                  decoration: BoxDecoration(
                    color: const Color(0xFF6b7280).withOpacity(0.5),
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('反馈 / 报告问题',
                        style: TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
                    const SizedBox(height: 4),
                    const Text('你的反馈将直接发送给开发者',
                        style: TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
                    const SizedBox(height: 16),
                    // 类型切换
                    ValueListenableBuilder<String>(
                      valueListenable: typeNotifier,
                      builder: (_, type, __) => Row(children: [
                        _fbTypeChip(ctx, '🐛 报告 Bug', 'bug', type,
                            () { typeNotifier.value = 'bug'; setState(() {}); }),
                        const SizedBox(width: 10),
                        _fbTypeChip(ctx, '✨ 功能建议', 'wish', type,
                            () { typeNotifier.value = 'wish'; setState(() {}); }),
                      ]),
                    ),
                    const SizedBox(height: 12),
                    // 内容输入
                    TextField(
                      controller: ctrl,
                      maxLines: 5,
                      maxLength: 1000,
                      style: const TextStyle(fontSize: 14),
                      decoration: InputDecoration(
                        hintText: typeNotifier.value == 'bug'
                            ? '描述一下遇到了什么问题？在哪个页面？怎么触发的？'
                            : '说说你希望有什么新功能或改进…',
                        hintStyle: const TextStyle(color: Color(0xFF4b5563), fontSize: 13),
                        filled: true,
                        fillColor: Theme.of(ctx).colorScheme.surface,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: Color(0xFFfb923c)),
                        ),
                        contentPadding: const EdgeInsets.all(14),
                        counterStyle: const TextStyle(color: Color(0xFF6b7280), fontSize: 11),
                      ),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: sending
                              ? const Color(0xFF374151)
                              : const Color(0xFFfb923c),
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12)),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          elevation: 0,
                        ),
                        onPressed: sending ? null : () async {
                          final text = ctrl.text.trim();
                          if (text.isEmpty) {
                            ScaffoldMessenger.of(ctx).showSnackBar(
                              const SnackBar(content: Text('请填写反馈内容')));
                            return;
                          }
                          setState(() => sending = true);
                          try {
                            final auth = context.read<AuthService>();
                            await ApiService(auth).submitFeedback(
                              type: typeNotifier.value,
                              content: text,
                            );
                            if (ctx.mounted) {
                              Navigator.pop(ctx);
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('感谢你的反馈！开发者已收到 ✓'),
                                  duration: Duration(seconds: 3),
                                ),
                              );
                            }
                          } catch (_) {
                            setState(() => sending = false);
                            if (ctx.mounted) {
                              ScaffoldMessenger.of(ctx).showSnackBar(
                                const SnackBar(content: Text('发送失败，请检查网络')));
                            }
                          }
                        },
                        child: sending
                            ? const SizedBox(width: 18, height: 18,
                                child: CircularProgressIndicator(
                                    strokeWidth: 2, color: Colors.white))
                            : const Text('提交反馈',
                                style: TextStyle(fontWeight: FontWeight.bold)),
                      ),
                    ),
                    const SizedBox(height: 8),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _fbTypeChip(BuildContext ctx, String label, String value,
      String current, VoidCallback onTap) {
    final selected = current == value;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: selected
              ? const Color(0xFFfb923c).withOpacity(0.15)
              : Theme.of(ctx).colorScheme.surface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: selected
                ? const Color(0xFFfb923c)
                : const Color(0xFF374151),
          ),
        ),
        child: Text(label,
            style: TextStyle(
              fontSize: 13,
              color: selected
                  ? const Color(0xFFfb923c)
                  : const Color(0xFF9ca3af),
              fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
            )),
      ),
    );
  }

  void _showAbout(BuildContext context) {
    final accent = themeToColor(context.read<AuthService>().user?.theme);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Text('关于语擦日历', style: TextStyle()),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(
            children: [
              Text('语擦助手',
                  style: TextStyle(color: accent, fontSize: 15, fontWeight: FontWeight.bold)),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                decoration: BoxDecoration(
                  color: accent.withAlpha(30),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: accent.withAlpha(80)),
                ),
                child: Text('v1.0.0',
                    style: TextStyle(color: accent, fontSize: 11, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          const Text('记录你的恋综档期、搭档和心情，让每一次语c都有迹可循。',
              style: TextStyle(color: Color(0xFF9ca3af), fontSize: 13, height: 1.65)),
          const SizedBox(height: 14),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Theme.of(ctx).colorScheme.surfaceContainer,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Theme.of(ctx).colorScheme.primary.withAlpha(60)),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Icon(Icons.person_outline, color: Color(0xFF6b7280), size: 14),
                SizedBox(width: 6),
                Text('开发者：长日将尽',
                    style: TextStyle(color: Color(0xFF9ca3af), fontSize: 12)),
              ]),
              SizedBox(height: 6),
              Row(children: [
                Icon(Icons.lock_outline, color: Color(0xFF6b7280), size: 14),
                SizedBox(width: 6),
                Expanded(child: Text('本应用仅供内部使用，严禁外传',
                    style: TextStyle(color: Color(0xFFf87171), fontSize: 12))),
              ]),
            ]),
          ),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx),
              child: Text('好的', style: TextStyle(color: accent))),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();
    final user = auth.user;
    final initial = (user?.displayName ?? '?')[0].toUpperCase();
    final total   = _stats?['total']        as int?    ?? 0;
    final covered = _stats?['covered_days'] as int?    ?? 0;
    final pct     = _stats?['pct']          as double? ?? 0.0;
    final accent  = themeToColor(user?.theme);

    return Scaffold(
      appBar: AppBar(
        title: const Text('我的', style: TextStyle()),
      ),
      body: ListView(
        children: [
          // ── 用户信息卡片 ──────────────────────────────────────
          Container(
            margin: const EdgeInsets.all(16),
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  Color.lerp(Theme.of(context).colorScheme.surfaceContainer, accent, 0.45)!,
                  Color.lerp(Theme.of(context).colorScheme.surface, accent, 0.10)!,
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(20),
              border: Border.all(color: accent.withAlpha(80)),
            ),
            child: Column(children: [
              Row(children: [
                // 头像
                Container(
                  width: 64, height: 64,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [accent, const Color(0xFFe879f9)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    shape: BoxShape.circle,
                  ),
                  child: Center(
                    child: Text(initial,
                        style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold)),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Expanded(
                      child: Text(user?.displayName ?? '',
                          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                          overflow: TextOverflow.ellipsis),
                    ),
                    if (user?.isVip == true) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                              colors: [Color(0xFFf59e0b), Color(0xFFfbbf24)]),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: const Row(mainAxisSize: MainAxisSize.min, children: [
                          Icon(Icons.star, color: Colors.white, size: 11),
                          SizedBox(width: 3),
                          Text('VIP', style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold)),
                        ]),
                      ),
                    ],
                  ]),
                  const SizedBox(height: 4),
                  Text('@${user?.username ?? ''}',
                      style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 13)),
                ])),
              ]),
              const SizedBox(height: 20),
              // 今年数据简报
              Container(
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerLow,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: accent.withAlpha(50)),
                ),
                child: _statsLoading
                    ? Center(child: SizedBox(height: 20, width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2, color: accent)))
                    : Row(children: [
                        _ProfileStat('${DateTime.now().year}年恋综', '$total 个', color: accent),
                        _vDivider(),
                        _ProfileStat('语擦天数', '$covered 天', color: accent),
                        _vDivider(),
                        _ProfileStat('档期占比', '$pct%', color: accent),
                      ]),
              ),
            ]),
          ),

          // ── 设置分组 ──────────────────────────────────────────
          _sectionHeader('偏好设置'),
          _SettingTile(
            icon: Icons.palette_outlined,
            label: '主题设置',
            color: accent,
            onTap: () => _showThemeDialog(context),
          ),

          _sectionHeader('数据'),
          _SettingTile(
            icon: Icons.download_outlined,
            label: '导出档期数据',
            color: const Color(0xFF34d399),
            onTap: () {},
          ),

          _sectionHeader('其他'),
          _SettingTile(
            icon: Icons.notifications_outlined,
            label: '测试提醒通知',
            color: const Color(0xFF34d399),
            onTap: () async {
              await NotificationService.sendTestNotification();
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('已发送测试通知，请查看状态栏')),
                );
              }
            },
          ),
          _SettingTile(
            icon: Icons.info_outline,
            label: '关于语擦日历',
            color: const Color(0xFF60a5fa),
            onTap: () => _showAbout(context),
          ),
          _SettingTile(
            icon: Icons.bug_report_outlined,
            label: '反馈 / 报告问题',
            color: const Color(0xFFfb923c),
            onTap: () => _showFeedback(context),
          ),

          const SizedBox(height: 8),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Divider(color: Theme.of(context).colorScheme.onSurface.withAlpha(30)),
          ),
          const SizedBox(height: 8),

          // 退出登录
          _SettingTile(
            icon: Icons.logout,
            label: '退出登录',
            color: const Color(0xFFf87171),
            trailing: false,
            onTap: () async {
              final confirm = await showDialog<bool>(
                context: context,
                builder: (ctx) => AlertDialog(
                  title: const Text('退出登录', style: TextStyle()),
                  content: const Text('确定要退出吗？', style: TextStyle(color: Color(0xFF9ca3af))),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(ctx, false),
                        child: const Text('取消', style: TextStyle(color: Color(0xFF9ca3af)))),
                    TextButton(onPressed: () => Navigator.pop(ctx, true),
                        child: const Text('退出', style: TextStyle(color: Color(0xFFf87171)))),
                  ],
                ),
              );
              if (confirm == true && context.mounted) {
                await context.read<AuthService>().logout();
              }
            },
          ),
          const SizedBox(height: 32),
        ],
      ),
    );
  }

  Widget _sectionHeader(String title) => Padding(
    padding: const EdgeInsets.fromLTRB(20, 20, 20, 6),
    child: Builder(builder: (ctx) => Text(title.toUpperCase(),
        style: TextStyle(color: Theme.of(ctx).colorScheme.onSurface.withAlpha(100),
            fontSize: 11, fontWeight: FontWeight.w600, letterSpacing: 0.8))),
  );

  Widget _vDivider() => Builder(builder: (ctx) => Container(
    width: 1, height: 32,
    margin: const EdgeInsets.symmetric(horizontal: 16),
    color: Theme.of(ctx).colorScheme.onSurface.withAlpha(40),
  ));

  void _showThemeDialog(BuildContext context) {
    final auth = context.read<AuthService>();
    showModalBottomSheet(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surfaceContainer,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => _ThemePicker(
        currentTheme: auth.user?.theme ?? '',
        isVip: auth.user?.isVip ?? false,
        unlockedAchievements: auth.user?.unlockedAchievements ?? [],
        onSelect: (t) {
          // 立刻换色，无需等待 API
          final prev = auth.user?.theme ?? '';
          auth.updateTheme(t);
          // 后台保存，失败则回滚
          ApiService(auth).setTheme(t).then((_) {
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('主题已同步，网页端刷新后生效'),
                  duration: Duration(seconds: 2),
                ),
              );
            }
          }).catchError((_) {
            auth.updateTheme(prev); // 回滚
            if (context.mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(content: Text('同步失败，已恢复原主题')));
            }
          });
        },
      ),
    );
  }
}

class _ProfileStat extends StatelessWidget {
  final String label, value;
  final Color color;
  const _ProfileStat(this.label, this.value, {required this.color});
  @override
  Widget build(BuildContext context) => Expanded(
    child: Column(children: [
      Text(value, style: TextStyle(color: color, fontSize: 18, fontWeight: FontWeight.bold)),
      const SizedBox(height: 4),
      Text(label, style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 11)),
    ]),
  );
}

class _SettingTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  final bool trailing;

  const _SettingTile({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
    this.trailing = true,
  });

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: Container(
        width: 36, height: 36,
        decoration: BoxDecoration(
          color: color.withAlpha(38),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Icon(icon, color: color, size: 20),
      ),
      title: Text(label, style: TextStyle(color: trailing ? Theme.of(context).colorScheme.onSurface : color)),
      trailing: trailing
          ? const Icon(Icons.chevron_right, color: Color(0xFF6b7280), size: 20)
          : null,
      onTap: onTap,
    );
  }
}

// ── 占位组件 ──────────────────────────────────────────────────────────────────────

// ── 主题选择器 ─────────────────────────────────────────────────────────────────────

class _ThemePicker extends StatefulWidget {
  final String currentTheme;
  final bool isVip;
  final List<String> unlockedAchievements;
  final void Function(String) onSelect;
  const _ThemePicker({
    required this.currentTheme,
    required this.isVip,
    required this.unlockedAchievements,
    required this.onSelect,
  });
  @override
  State<_ThemePicker> createState() => _ThemePickerState();
}

class _ThemePickerState extends State<_ThemePicker> {
  late String _selected;

  // (id, color, label, type)  type: 'normal' | 'vip' | 'achieve'
  static const _themes = [
    ('default',            Color(0xFF8b7cf6), '默认',           'normal'),
    ('spring',             Color(0xFFf472b6), '春·樱',          'normal'),
    ('summer',             Color(0xFF06b6d4), '夏·海',          'normal'),
    ('autumn',             Color(0xFFf59e0b), '秋·枫',          'normal'),
    ('winter',             Color(0xFF7dd3fc), '冬·冰',          'normal'),
    ('monet',              Color(0xFFa8d8ea), '莫奈',           'normal'),
    ('vangogh',            Color(0xFFe8b840), '梵高·星夜',      'normal'),
    ('picasso',            Color(0xFFe06840), '毕加索·玫瑰',    'normal'),
    ('davinci',            Color(0xFFc8882a), '达芬奇·晕涂',    'normal'),
    ('gukaizhi',           Color(0xFFc03830), '顾恺之·丹青',    'normal'),
    ('michelangelo',       Color(0xFFc8a050), '米开朗基罗',     'normal'),
    ('warhol',             Color(0xFFffd700), '沃霍尔·波普',    'normal'),
    ('spring-day',         Color(0xFFdb2777), '春·樱 ☀',       'normal'),
    ('summer-day',         Color(0xFF0284c7), '夏·海 ☀',       'normal'),
    ('autumn-day',         Color(0xFFb45309), '秋·枫 ☀',       'normal'),
    ('winter-day',         Color(0xFF1d6fa0), '冬·冰 ☀',       'normal'),
    ('monet-day',          Color(0xFF4a8fa8), '莫奈 ☀',         'normal'),
    ('vangogh-day',        Color(0xFF1a4a9a), '梵高 ☀',         'normal'),
    ('picasso-day',        Color(0xFFc04828), '毕加索 ☀',       'normal'),
    ('davinci-day',        Color(0xFF8a3c10), '达芬奇 ☀',       'normal'),
    ('gukaizhi-day',       Color(0xFF9a2018), '顾恺之 ☀',       'normal'),
    ('michelangelo-day',   Color(0xFF7a3e18), '米开朗基罗 ☀',   'normal'),
    ('warhol-day',         Color(0xFFcc0000), '沃霍尔 ☀',       'normal'),
    ('vip-gold',           Color(0xFFf59e0b), '烈金 ★',         'vip'),
    ('vip-jade',           Color(0xFF10b981), '翡翠 ★',         'vip'),
    ('achieve-first-drama',Color(0xFFe879f9), '初心·破茧',      'achieve'),
    ('achieve-sched-10',   Color(0xFF22d3ee), '积羽·十档',      'achieve'),
    ('achieve-sched-50',   Color(0xFFf59e0b), '百炼·五十档',    'achieve'),
  ];

  static const _achieveDesc = {
    'achieve-first-drama': '记录第一篇戏录',
    'achieve-sched-10':    '累计录入 10 个日程',
    'achieve-sched-50':    '累计录入 50 个日程',
  };

  @override
  void initState() {
    super.initState();
    _selected = widget.currentTheme;
  }

  bool _isLocked(String id, String type) {
    if (type == 'vip')     return !widget.isVip;
    if (type == 'achieve') return !widget.unlockedAchievements.contains(id);
    return false;
  }

  Widget _buildGroup(BuildContext context, String title, String type, Color titleColor,
      {String? hint}) {
    final items = _themes.where((t) => t.$4 == type).toList();
    final itemW = (MediaQuery.of(context).size.width - 40 - 30) / 4;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Text(title,
            style: TextStyle(color: titleColor, fontSize: 11, fontWeight: FontWeight.w600)),
        if (hint != null) ...[
          const SizedBox(width: 6),
          Text(hint, style: const TextStyle(color: Color(0xFF6b7280), fontSize: 10)),
        ],
      ]),
      const SizedBox(height: 8),
      Wrap(
        spacing: 10,
        runSpacing: 10,
        children: items.map((t) {
          final id     = t.$1;
          final color  = t.$2;
          final label  = t.$3;
          final locked = _isLocked(id, type);
          final active = id == _selected;
          final desc   = type == 'achieve' ? _achieveDesc[id] : null;

          return GestureDetector(
            onTap: locked ? null : () {
              setState(() => _selected = id);
              widget.onSelect(id);
              Navigator.pop(context);
            },
            child: Opacity(
              opacity: locked ? 0.4 : 1.0,
              child: Container(
                width: itemW,
                padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
                decoration: BoxDecoration(
                  color: active ? color.withAlpha(40) : Theme.of(context).colorScheme.surface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: active ? color : Theme.of(context).colorScheme.onSurface.withAlpha(40),
                    width: active ? 2 : 1,
                  ),
                ),
                child: Column(children: [
                  Stack(alignment: Alignment.topRight, children: [
                    Container(
                      width: 26, height: 26,
                      decoration: BoxDecoration(
                        color: color,
                        shape: BoxShape.circle,
                        boxShadow: active
                            ? [BoxShadow(color: color.withAlpha(100), blurRadius: 8)]
                            : null,
                      ),
                    ),
                    if (locked)
                      const Positioned(right: -2, top: -2,
                          child: Icon(Icons.lock, color: Color(0xFFfbbf24), size: 11)),
                    if (active)
                      const Positioned(right: -2, top: -2,
                          child: Icon(Icons.check_circle, color: Colors.white, size: 13)),
                  ]),
                  const SizedBox(height: 5),
                  Text(label,
                      style: TextStyle(
                          color: active ? color : Theme.of(context).colorScheme.onSurface.withAlpha(160),
                          fontSize: 9.5),
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                  if (locked && desc != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(desc,
                          style: const TextStyle(color: Color(0xFF4b5563), fontSize: 8),
                          textAlign: TextAlign.center,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis),
                    ),
                ]),
              ),
            ),
          );
        }).toList(),
      ),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 32),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Row(children: [
          const Text('主题设置',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const Spacer(),
          IconButton(
            icon: const Icon(Icons.close, color: Color(0xFF9ca3af)),
            onPressed: () => Navigator.pop(context),
          ),
        ]),
        const SizedBox(height: 4),
        const Text('同步到网页端，刷新网页后生效',
            style: TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
        const SizedBox(height: 16),
        // 主题网格（分组）
        Flexible(
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildGroup(context, '普通主题', 'normal', const Color(0xFF9ca3af)),
                const SizedBox(height: 14),
                _buildGroup(context, '★ VIP 专属', 'vip', const Color(0xFFf59e0b),
                    hint: widget.isVip ? null : '累计 10 条有效检举解锁'),
                const SizedBox(height: 14),
                _buildGroup(context, '🏆 成就主题', 'achieve', const Color(0xFFe879f9)),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),
      ]),
    );
  }
}

// ── 占位组件 ─────────────────────────────────────────────────────────────────────

class _ComingSoon extends StatelessWidget {
  final IconData icon;
  final String label;
  const _ComingSoon({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 48, color: const Color(0xFF374151)),
          const SizedBox(height: 12),
          Text(label,
              style: const TextStyle(
                  color: Color(0xFF6b7280), fontSize: 16)),
          const SizedBox(height: 4),
          const Text('开发中...',
              style: TextStyle(
                  color: Color(0xFF4b5563), fontSize: 13)),
        ],
      ),
    );
  }
}
