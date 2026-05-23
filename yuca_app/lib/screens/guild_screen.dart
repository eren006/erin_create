import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/auth_service.dart';
import '../services/api_service.dart';
import '../utils/theme_utils.dart';
import 'drama_screen.dart';

// ── 公会主页（我的公会 + 发现 + 戏录） ───────────────────────────────────────────

class GuildScreen extends StatefulWidget {
  const GuildScreen({super.key});
  @override
  State<GuildScreen> createState() => _GuildScreenState();
}

class _GuildScreenState extends State<GuildScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tab;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final accent = themeToColor(context.watch<AuthService>().user?.theme);
    return Scaffold(
      appBar: AppBar(
        title: const Text('公会'),
        actions: [
          IconButton(
            icon: Icon(Icons.add, color: accent),
            onPressed: () => _showCreateDialog(context),
          ),
        ],
        bottom: TabBar(
          controller: _tab,
          indicatorColor: accent,
          labelColor: accent,
          unselectedLabelColor: const Color(0xFF6b7280),
          tabs: const [
            Tab(text: '我的公会'),
            Tab(text: '发现'),
            Tab(text: '戏录'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tab,
        children: const [
          _MyGuildsTab(),
          _DiscoverTab(),
          DramaLogTab(),
        ],
      ),
    );
  }

  void _showCreateDialog(BuildContext context) {
    final nameCtrl = TextEditingController();
    final slugCtrl = TextEditingController();
    final sigCtrl  = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(

        title: const Text('创建公会', style: TextStyle()),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _dialogField(nameCtrl, '公会名称'),
              const SizedBox(height: 12),
              _dialogField(slugCtrl, '公会 ID（小写字母/数字/下划线）'),
              const SizedBox(height: 12),
              _dialogField(sigCtrl, '公会简介（可选）', maxLines: 2),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消', style: TextStyle(color: Color(0xFF9ca3af))),
          ),
          TextButton(
            onPressed: () async {
              final auth = context.read<AuthService>();
              final api  = ApiService(auth);
              try {
                final resp = await api.createGuild(
                    nameCtrl.text.trim(),
                    slugCtrl.text.trim(),
                    sigCtrl.text.trim());
                if (!ctx.mounted) return;
                Navigator.pop(ctx);
                if (resp['ok'] == true) {
                  _showSnack(context, '✅ 公会已创建');
                } else {
                  _showSnack(context, resp['error'] ?? '创建失败');
                }
              } catch (e) {
                if (!ctx.mounted) return;
                Navigator.pop(ctx);
                _showSnack(context, '创建失败，请重试');
              }
            },
            child: const Text('创建', style: TextStyle(color: Color(0xFF8b7cf6))),
          ),
        ],
      ),
    );
  }

  Widget _dialogField(TextEditingController ctrl, String hint, {int maxLines = 1}) {
    return TextField(
      controller: ctrl,
      maxLines: maxLines,
      style: const TextStyle(),
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: const TextStyle(color: Color(0xFF6b7280)),
        filled: true,
        fillColor: const Color(0xFF1a1a2e),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide.none,
        ),
      ),
    );
  }
}

void _showSnack(BuildContext context, String msg) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(msg), backgroundColor: const Color(0xFF16213e)),
  );
}

// ── 我的公会 ──────────────────────────────────────────────────────────────────────

class _MyGuildsTab extends StatefulWidget {
  const _MyGuildsTab();
  @override
  State<_MyGuildsTab> createState() => _MyGuildsTabState();
}

class _MyGuildsTabState extends State<_MyGuildsTab> {
  bool _loading = true;
  List<dynamic> _owned   = [];
  List<dynamic> _member  = [];
  List<dynamic> _pending = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() => _loading = true);
    try {
      final auth = context.read<AuthService>();
      final data = await ApiService(auth).getMyGuilds();
      if (!mounted) return;
      setState(() {
        _owned   = data['owned']   as List<dynamic>? ?? [];
        _member  = data['member']  as List<dynamic>? ?? [];
        _pending = data['pending'] as List<dynamic>? ?? [];
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: Color(0xFF8b7cf6)));
    }
    if (_owned.isEmpty && _member.isEmpty && _pending.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.groups_outlined, size: 56, color: Color(0xFF374151)),
            const SizedBox(height: 12),
            const Text('还没有加入任何公会',
                style: TextStyle(color: Color(0xFF6b7280))),
            const SizedBox(height: 8),
            const Text('去「发现」页面找找看',
                style: TextStyle(color: Color(0xFF4b5563), fontSize: 13)),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _load,
      color: const Color(0xFF8b7cf6),
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          if (_owned.isNotEmpty) ...[
            _sectionHeader('我创建的公会'),
            ..._owned.map((g) => _GuildCard(
                guild: g,
                isOwner: true,
                onTap: () => _openDetail(context, g))),
          ],
          if (_member.isNotEmpty) ...[
            _sectionHeader('我加入的公会'),
            ..._member.map((g) => _GuildCard(
                guild: g,
                isOwner: false,
                onTap: () => _openDetail(context, g))),
          ],
          if (_pending.isNotEmpty) ...[
            _sectionHeader('申请中'),
            ..._pending.map((g) => _PendingCard(guild: g)),
          ],
        ],
      ),
    );
  }

  void _openDetail(BuildContext context, dynamic g) async {
    await Navigator.push(context,
        MaterialPageRoute(builder: (_) => GuildDetailScreen(gid: g['id'] as int)));
    _load(); // 返回后刷新
  }
}

Widget _sectionHeader(String title) => Padding(
      padding: const EdgeInsets.only(top: 8, bottom: 6, left: 4),
      child: Text(title,
          style: const TextStyle(
              color: Color(0xFF9ca3af), fontSize: 12, fontWeight: FontWeight.w600)),
    );

class _GuildCard extends StatelessWidget {
  final dynamic guild;
  final bool isOwner;
  final VoidCallback onTap;
  const _GuildCard({required this.guild, required this.isOwner, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final pending = (guild['pending_count'] as int? ?? 0);
    final cs = Theme.of(context).colorScheme;
    return Card(
      color: cs.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: isOwner
              ? cs.primary.withAlpha(100)
              : cs.primary.withAlpha(40),
        ),
      ),
      child: ListTile(
        onTap: onTap,
        leading: CircleAvatar(
          backgroundColor: cs.primary.withAlpha(50),
          child: Text(
            (guild['name'] as String? ?? '?')[0],
            style: TextStyle(color: cs.primary, fontWeight: FontWeight.bold),
          ),
        ),
        title: Text(guild['name'] as String? ?? '',
            style: const TextStyle(fontWeight: FontWeight.w500)),
        subtitle: Text('#${guild['slug'] ?? ''}',
            style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (isOwner)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: const Color(0xFF8b7cf6).withOpacity(0.2),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: const Text('会长',
                    style: TextStyle(color: Color(0xFF8b7cf6), fontSize: 11)),
              ),
            if (pending > 0) ...[
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: const Color(0xFFf87171).withOpacity(0.2),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text('$pending 待审',
                    style: const TextStyle(color: Color(0xFFf87171), fontSize: 11)),
              ),
            ],
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right, color: Color(0xFF6b7280), size: 18),
          ],
        ),
      ),
    );
  }
}

class _PendingCard extends StatelessWidget {
  final dynamic guild;
  const _PendingCard({required this.guild});
  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Theme.of(context).colorScheme.primary.withAlpha(50)),
      ),
      child: ListTile(
        leading: const Icon(Icons.hourglass_empty, color: Color(0xFFfbbf24)),
        title: Text(guild['name'] as String? ?? '',
            style: const TextStyle()),
        subtitle: const Text('申请中，等待审核',
            style: TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
      ),
    );
  }
}

// ── 发现公会 ──────────────────────────────────────────────────────────────────────

class _DiscoverTab extends StatefulWidget {
  const _DiscoverTab();
  @override
  State<_DiscoverTab> createState() => _DiscoverTabState();
}

class _DiscoverTabState extends State<_DiscoverTab> {
  final _searchCtrl = TextEditingController();
  bool _loading = true;
  List<dynamic> _guilds = [];

  @override
  void initState() {
    super.initState();
    _search('');
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _search(String q) async {
    if (!mounted) return;
    setState(() => _loading = true);
    try {
      final auth = context.read<AuthService>();
      final list = await ApiService(auth).discoverGuilds(q: q);
      if (!mounted) return;
      setState(() { _guilds = list; _loading = false; });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: TextField(
            controller: _searchCtrl,
            style: const TextStyle(),
            decoration: InputDecoration(
              hintText: '搜索公会名或 ID',
              hintStyle: const TextStyle(color: Color(0xFF6b7280)),
              prefixIcon: const Icon(Icons.search, color: Color(0xFF6b7280)),
              filled: true,
              fillColor: const Color(0xFF16213e),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
            ),
            onSubmitted: _search,
          ),
        ),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator(color: Color(0xFF8b7cf6)))
              : _guilds.isEmpty
                  ? const Center(child: Text('没有找到公会',
                        style: TextStyle(color: Color(0xFF6b7280))))
                  : RefreshIndicator(
                      onRefresh: () => _search(_searchCtrl.text),
                      color: const Color(0xFF8b7cf6),
                      child: ListView.builder(
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                        itemCount: _guilds.length,
                        itemBuilder: (ctx, i) => _DiscoverCard(
                          guild: _guilds[i],
                          onJoined: () => _search(_searchCtrl.text),
                        ),
                      ),
                    ),
        ),
      ],
    );
  }
}

class _DiscoverCard extends StatelessWidget {
  final dynamic guild;
  final VoidCallback onJoined;
  const _DiscoverCard({required this.guild, required this.onJoined});

  @override
  Widget build(BuildContext context) {
    final isOwner  = guild['is_owner'] as bool? ?? false;
    final myStatus = guild['my_status'] as String?;
    final count    = guild['member_count'] as int? ?? 0;

    Widget trailing;
    if (isOwner) {
      trailing = const Text('我的公会',
          style: TextStyle(color: Color(0xFF8b7cf6), fontSize: 12));
    } else if (myStatus == 'approved') {
      trailing = const Text('已加入',
          style: TextStyle(color: Color(0xFF34d399), fontSize: 12));
    } else if (myStatus == 'pending') {
      trailing = const Text('申请中',
          style: TextStyle(color: Color(0xFFfbbf24), fontSize: 12));
    } else {
      trailing = TextButton(
        onPressed: () async {
          try {
            final auth = context.read<AuthService>();
            await ApiService(auth).joinGuild(guild['id'] as int);
            _showSnack(context, '✅ 申请已发送');
            onJoined();
          } catch (e) {
            _showSnack(context, '申请失败，请重试');
          }
        },
        style: TextButton.styleFrom(
          backgroundColor: const Color(0xFF8b7cf6).withOpacity(0.15),
          foregroundColor: const Color(0xFF8b7cf6),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          minimumSize: Size.zero,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
        child: const Text('申请加入', style: TextStyle(fontSize: 12)),
      );
    }

    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Theme.of(context).colorScheme.primary.withAlpha(50)),
      ),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: const Color(0xFF374151),
          child: Text(
            (guild['name'] as String? ?? '?')[0],
            style: const TextStyle(),
          ),
        ),
        title: Text(guild['name'] as String? ?? '',
            style: const TextStyle()),
        subtitle: Text(
          '#${guild['slug'] ?? ''}  ·  $count 人  ·  ${guild['owner_name'] ?? ''}',
          style: const TextStyle(color: Color(0xFF6b7280), fontSize: 11),
        ),
        trailing: trailing,
      ),
    );
  }
}

// ── 公会详情 ──────────────────────────────────────────────────────────────────────

class GuildDetailScreen extends StatefulWidget {
  final int gid;
  const GuildDetailScreen({super.key, required this.gid});
  @override
  State<GuildDetailScreen> createState() => _GuildDetailScreenState();
}

class _GuildDetailScreenState extends State<GuildDetailScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tab;
  bool _loading = true;
  Map<String, dynamic>? _guild;
  List<dynamic> _members = [];
  List<dynamic> _pending = [];
  bool _isOwner = false;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 4, vsync: this);
    _load();
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() => _loading = true);
    try {
      final auth = context.read<AuthService>();
      final data = await ApiService(auth).getGuildDetail(widget.gid);
      if (!mounted) return;
      setState(() {
        _guild   = data['guild']   as Map<String, dynamic>?;
        _members = data['members'] as List<dynamic>? ?? [];
        _pending = data['pending'] as List<dynamic>? ?? [];
        _isOwner = data['is_owner'] as bool? ?? false;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final accent = themeToColor(context.watch<AuthService>().user?.theme);
    return Scaffold(
      appBar: AppBar(
        title: Text(_guild?['name'] as String? ?? '公会详情'),
        bottom: _loading
            ? null
            : TabBar(
                controller: _tab,
                indicatorColor: accent,
                labelColor: accent,
                unselectedLabelColor: const Color(0xFF6b7280),
                labelStyle: const TextStyle(fontSize: 12),
                tabs: [
                  Tab(text: '成员${_pending.isNotEmpty && _isOwner ? ' (${_pending.length}待审)' : ''}'),
                  const Tab(text: '共同档期'),
                  const Tab(text: '共同搭档'),
                  const Tab(text: '共同黑名单'),
                ],
              ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF8b7cf6)))
          : Column(
              children: [
                // 公会信息卡片
                _GuildInfoCard(guild: _guild, isOwner: _isOwner, memberCount: _members.length),
                // Tab内容
                Expanded(
                  child: TabBarView(
                    controller: _tab,
                    children: [
                      // 成员 tab
                      _MembersTab(
                        members: _members,
                        pending: _pending,
                        isOwner: _isOwner,
                        gid: widget.gid,
                        onAction: _load,
                      ),
                      // 共同档期
                      _GuildSharedTab(
                        gid: widget.gid,
                        tabType: 'schedules',
                      ),
                      // 共同搭档
                      _GuildSharedTab(
                        gid: widget.gid,
                        tabType: 'partners',
                      ),
                      // 共同黑名单
                      _GuildSharedTab(
                        gid: widget.gid,
                        tabType: 'blacklist',
                      ),
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}

// 公会信息卡片
class _GuildInfoCard extends StatelessWidget {
  final Map<String, dynamic>? guild;
  final bool isOwner;
  final int memberCount;
  const _GuildInfoCard({required this.guild, required this.isOwner, required this.memberCount});

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: const Color(0xFF8b7cf6).withOpacity(0.3)),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 22,
            backgroundColor: const Color(0xFF8b7cf6).withOpacity(0.2),
            child: Text(
              (guild?['name'] as String? ?? '?')[0],
              style: const TextStyle(
                  color: Color(0xFF8b7cf6), fontSize: 18, fontWeight: FontWeight.bold),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(guild?['name'] as String? ?? '',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.bold)),
                Text(
                  '会长：${guild?['owner_name'] ?? ''}  ·  $memberCount 人',
                  style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12),
                ),
                if ((guild?['signature'] as String? ?? '').isNotEmpty)
                  Text(guild!['signature'] as String,
                      style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 12),
                      maxLines: 1, overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
          if (isOwner)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: const Color(0xFF8b7cf6).withOpacity(0.2),
                borderRadius: BorderRadius.circular(6),
              ),
              child: const Text('会长', style: TextStyle(color: Color(0xFF8b7cf6), fontSize: 11)),
            ),
        ],
      ),
    );
  }
}

// 成员 tab
class _MembersTab extends StatelessWidget {
  final List<dynamic> members;
  final List<dynamic> pending;
  final bool isOwner;
  final int gid;
  final VoidCallback onAction;
  const _MembersTab({required this.members, required this.pending,
      required this.isOwner, required this.gid, required this.onAction});

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () async => onAction(),
      color: const Color(0xFF8b7cf6),
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          if (isOwner && pending.isNotEmpty) ...[
            _sectionHeader('待审核 (${pending.length})'),
            ...pending.map((u) => _PendingMemberCard(member: u, gid: gid, onAction: onAction)),
            const SizedBox(height: 8),
          ],
          _sectionHeader('成员 (${members.length})'),
          ...members.map((u) => Card(
                color: Theme.of(context).colorScheme.surfaceContainer,
                margin: const EdgeInsets.only(bottom: 6),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                  side: BorderSide(color: Theme.of(context).colorScheme.primary.withAlpha(50)),
                ),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: const Color(0xFF374151),
                    child: Text(
                      (u['display_name'] as String? ?? '?')[0],
                      style: const TextStyle(),
                    ),
                  ),
                  title: Text(u['display_name'] as String? ?? '',
                      style: const TextStyle()),
                  subtitle: Text('@${u['username'] ?? ''}',
                      style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
                ),
              )),
        ],
      ),
    );
  }
}

// 共同内容 tab（档期 / 搭档 / 黑名单）
class _GuildSharedTab extends StatefulWidget {
  final int gid;
  final String tabType; // 'schedules' | 'partners' | 'blacklist'
  const _GuildSharedTab({required this.gid, required this.tabType});
  @override
  State<_GuildSharedTab> createState() => _GuildSharedTabState();
}

class _GuildSharedTabState extends State<_GuildSharedTab>
    with AutomaticKeepAliveClientMixin {
  bool _loading = false;
  bool _loaded  = false;
  List<dynamic> _items = [];
  String? _error;

  @override
  bool get wantKeepAlive => true;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (!_loaded) _load();
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final auth = context.read<AuthService>();
      final api  = ApiService(auth);
      Map<String, dynamic> data;
      if (widget.tabType == 'schedules') {
        data = await api.getGuildSchedules(widget.gid);
        if (!mounted) return;
        setState(() {
          _items  = data['members'] as List<dynamic>? ?? [];
          _loaded = true; _loading = false;
        });
      } else if (widget.tabType == 'partners') {
        data = await api.getGuildPartners(widget.gid);
        if (!mounted) return;
        setState(() {
          _items  = data['partners'] as List<dynamic>? ?? [];
          _loaded = true; _loading = false;
        });
      } else {
        data = await api.getGuildBlacklist(widget.gid);
        if (!mounted) return;
        setState(() {
          _items  = data['blacklist'] as List<dynamic>? ?? [];
          _loaded = true; _loading = false;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = '加载失败'; _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_loading) {
      return const Center(child: CircularProgressIndicator(color: Color(0xFF8b7cf6)));
    }
    if (_error != null) {
      return Center(
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Text(_error!, style: const TextStyle(color: Color(0xFF9ca3af))),
          const SizedBox(height: 12),
          ElevatedButton(
            onPressed: _load,
            style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF8b7cf6)),
            child: const Text('重试'),
          ),
        ]),
      );
    }
    if (_items.isEmpty) {
      final labels = {'schedules': '档期', 'partners': '搭档', 'blacklist': '黑名单'};
      return Center(
        child: Text('暂无共同${labels[widget.tabType] ?? '内容'}',
            style: const TextStyle(color: Color(0xFF6b7280))));
    }

    if (widget.tabType == 'schedules') {
      return RefreshIndicator(
        onRefresh: _load,
        color: const Color(0xFF8b7cf6),
        child: ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: _items.length,
          itemBuilder: (ctx, i) {
            final entry   = _items[i] as Map<String, dynamic>;
            final user    = entry['user'] as Map<String, dynamic>;
            final scheds  = entry['schedules'] as List<dynamic>? ?? [];
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  child: Row(children: [
                    CircleAvatar(
                      radius: 14,
                      backgroundColor: const Color(0xFF8b7cf6).withOpacity(0.2),
                      child: Text(
                        (user['display_name'] as String? ?? '?')[0],
                        style: const TextStyle(color: Color(0xFF8b7cf6), fontSize: 12),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(user['display_name'] as String? ?? '',
                        style: const TextStyle(fontWeight: FontWeight.w600)),
                  ]),
                ),
                ...scheds.map((s) => _SharedScheduleCard(schedule: s)),
              ],
            );
          },
        ),
      );
    }

    if (widget.tabType == 'partners') {
      return RefreshIndicator(
        onRefresh: _load,
        color: const Color(0xFF8b7cf6),
        child: ListView.builder(
          padding: const EdgeInsets.all(12),
          itemCount: _items.length,
          itemBuilder: (ctx, i) => _SharedPartnerCard(partner: _items[i]),
        ),
      );
    }

    // blacklist
    return RefreshIndicator(
      onRefresh: _load,
      color: const Color(0xFF8b7cf6),
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: _items.length,
        itemBuilder: (ctx, i) => _SharedBlacklistCard(entry: _items[i]),
      ),
    );
  }
}

// 共同档期卡片
class _SharedScheduleCard extends StatelessWidget {
  final dynamic schedule;
  const _SharedScheduleCard({required this.schedule});

  Color _hexColor(String hex) {
    try { return Color(int.parse(hex.replaceFirst('#', '0xFF'))); }
    catch (_) { return const Color(0xFF8b7cf6); }
  }

  @override
  Widget build(BuildContext context) {
    final color   = _hexColor(schedule['color'] as String? ?? '#8b7cf6');
    final tr      = schedule['time_range'] as String? ?? '';
    final sy      = schedule['start_year'] as int? ?? DateTime.now().year;
    String dateStr = tr;
    if (tr.length == 9) {
      final sm = tr.substring(0, 2).replaceFirst(RegExp('^0'), '');
      final sd = tr.substring(2, 4).replaceFirst(RegExp('^0'), '');
      final em = tr.substring(5, 7).replaceFirst(RegExp('^0'), '');
      final ed = tr.substring(7, 9).replaceFirst(RegExp('^0'), '');
      final ey = int.parse(tr.substring(5, 7)) < int.parse(tr.substring(0, 2)) ? sy + 1 : sy;
      dateStr  = ey != sy ? '$sy/$sm/$sd - $ey/$em/$ed' : '$sy/$sm/$sd - $em/$ed';
    }
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 6, left: 8),
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
          side: BorderSide(color: color.withOpacity(0.3))),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Row(children: [
          Container(width: 3, height: 40,
              decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(2))),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(schedule['show_name'] as String? ?? '',
                style: const TextStyle(fontWeight: FontWeight.w500)),
            Text(dateStr, style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 12)),
          ])),
        ]),
      ),
    );
  }
}

// 共同搭档卡片
class _SharedPartnerCard extends StatelessWidget {
  final dynamic partner;
  const _SharedPartnerCard({required this.partner});

  @override
  Widget build(BuildContext context) {
    final tags = partner['tags_list'] as List<dynamic>? ?? [];
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Theme.of(context).colorScheme.primary.withAlpha(50)),
      ),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: const Color(0xFF34d399).withOpacity(0.2),
          child: const Icon(Icons.people, color: Color(0xFF34d399), size: 20),
        ),
        title: Text(partner['qq'] as String? ?? '',
            style: const TextStyle(fontWeight: FontWeight.w500)),
        subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if ((partner['notes'] as String? ?? '').isNotEmpty)
            Text(partner['notes'] as String,
                style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 12),
                maxLines: 1, overflow: TextOverflow.ellipsis),
          Text('来自：${partner['owner_name'] ?? ''}',
              style: const TextStyle(color: Color(0xFF6b7280), fontSize: 11)),
          if (tags.isNotEmpty)
            Wrap(spacing: 4, children: tags.map((t) => Chip(
              label: Text(t.toString(), style: const TextStyle(fontSize: 10, color: Color(0xFF34d399))),
              backgroundColor: const Color(0xFF34d399).withOpacity(0.1),
              padding: EdgeInsets.zero,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            )).toList()),
        ]),
        isThreeLine: true,
      ),
    );
  }
}

// 共同黑名单卡片
class _SharedBlacklistCard extends StatelessWidget {
  final dynamic entry;
  const _SharedBlacklistCard({required this.entry});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: const Color(0xFFf87171).withOpacity(0.3))),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: const Color(0xFFf87171).withOpacity(0.2),
          child: const Icon(Icons.block, color: Color(0xFFf87171), size: 20),
        ),
        title: Text(entry['qq'] as String? ?? '',
            style: const TextStyle(fontWeight: FontWeight.w500)),
        subtitle: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if ((entry['reason'] as String? ?? '').isNotEmpty)
            Text(entry['reason'] as String,
                style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 12),
                maxLines: 2, overflow: TextOverflow.ellipsis),
          Text('来自：${entry['owner_name'] ?? ''}',
              style: const TextStyle(color: Color(0xFF6b7280), fontSize: 11)),
        ]),
        isThreeLine: true,
      ),
    );
  }
}

class _PendingMemberCard extends StatelessWidget {
  final dynamic member;
  final int gid;
  final VoidCallback onAction;
  const _PendingMemberCard(
      {required this.member, required this.gid, required this.onAction});

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 6),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: const Color(0xFFfbbf24).withOpacity(0.3)),
      ),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: const Color(0xFFfbbf24).withOpacity(0.2),
          child: Text(
            (member['display_name'] as String? ?? '?')[0],
            style: const TextStyle(color: Color(0xFFfbbf24)),
          ),
        ),
        title: Text(member['display_name'] as String? ?? '',
            style: const TextStyle()),
        subtitle: Text('@${member['username'] ?? ''}',
            style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              icon: const Icon(Icons.check_circle_outline,
                  color: Color(0xFF34d399)),
              onPressed: () async {
                final auth = context.read<AuthService>();
                await ApiService(auth)
                    .approveGuildMember(gid, member['id'] as int);
                _showSnack(context, '✅ 已通过');
                onAction();
              },
            ),
            IconButton(
              icon: const Icon(Icons.cancel_outlined, color: Color(0xFFf87171)),
              onPressed: () async {
                final auth = context.read<AuthService>();
                await ApiService(auth)
                    .rejectGuildMember(gid, member['id'] as int);
                _showSnack(context, '已拒绝');
                onAction();
              },
            ),
          ],
        ),
      ),
    );
  }
}
