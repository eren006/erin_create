import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/auth_service.dart';
import '../services/api_service.dart';

// 状态标签
const _statusLabels = {
  'pending':  '审核中',
  'approved': '已通过',
  'rejected': '已拒绝',
  'editing':  '需修改',
};

const _statusColors = {
  'pending':  Color(0xFFfbbf24),
  'approved': Color(0xFF34d399),
  'rejected': Color(0xFFf87171),
  'editing':  Color(0xFF60a5fa),
};

class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});
  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tab;
  bool _loading = true;
  bool _canView = false;
  int  _approvedCount = 0;
  List<dynamic> _myReports = [];
  List<int>     _appealedIds = [];
  List<dynamic> _groups = [];
  String? _error;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 2, vsync: this);
    _load();
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final auth = context.read<AuthService>();
      final data = await ApiService(auth).getReports();
      if (!mounted) return;
      setState(() {
        _canView      = data['can_view'] as bool? ?? false;
        _approvedCount= data['approved_count'] as int? ?? 0;
        _myReports    = data['my_reports'] as List<dynamic>? ?? [];
        _appealedIds  = (data['appealed_ids'] as List<dynamic>? ?? []).map((e) => e as int).toList();
        _groups       = data['groups'] as List<dynamic>? ?? [];
        _loading      = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = '加载失败，请重试'; _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('公开检举', style: TextStyle()),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            icon: const Icon(Icons.add_circle_outline, color: Color(0xFFe879f9)),
            tooltip: '提交检举',
            onPressed: () => _showSubmitDialog(context),
          ),
        ],
        bottom: TabBar(
          controller: _tab,
          indicatorColor: const Color(0xFFe879f9),
          labelColor: const Color(0xFFe879f9),
          unselectedLabelColor: const Color(0xFF6b7280),
          tabs: const [
            Tab(text: '我的检举'),
            Tab(text: '公开列表'),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFFe879f9)))
          : _error != null
              ? _ErrorView(msg: _error!, onRetry: _load)
              : TabBarView(
                  controller: _tab,
                  children: [
                    _MyReportsTab(
                      reports: _myReports,
                      appealedIds: _appealedIds,
                      onRefresh: _load,
                      onEdit: (r) => _showEditDialog(context, r),
                      onDelete: (rid) => _deleteReport(context, rid),
                      onAppeal: (rid) => _showAppealDialog(context, rid),
                    ),
                    _PublicListTab(
                      canView: _canView,
                      approvedCount: _approvedCount,
                      groups: _groups,
                      onRefresh: _load,
                      appealedIds: _appealedIds,
                      onAppeal: (rid) => _showAppealDialog(context, rid),
                    ),
                  ],
                ),
    );
  }

  void _showSubmitDialog(BuildContext context) {
    final qqCtrl     = TextEditingController();
    final tagCtrl    = TextEditingController();
    final reasonCtrl = TextEditingController();
    String? err;

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setS) => AlertDialog(
          title: const Text('提交检举', style: TextStyle()),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (err != null)
                  Container(
                    width: double.infinity,
                    margin: const EdgeInsets.only(bottom: 10),
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF7f1d1d),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(err!, style: const TextStyle(color: Color(0xFFfca5a5), fontSize: 13)),
                  ),
                _dlgLabel('被检举 QQ *'),
                _dlgField(qqCtrl, '5-12 位数字', keyboardType: TextInputType.number),
                const SizedBox(height: 10),
                _dlgLabel('分类标签（可选）'),
                _dlgField(tagCtrl, '例如：骚扰 / 欺诈 / 违规'),
                const SizedBox(height: 10),
                _dlgLabel('检举原因 *'),
                _dlgField(reasonCtrl, '请详细描述...', maxLines: 4),
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
                if (qqCtrl.text.trim().isEmpty) {
                  setS(() => err = 'QQ 号不能为空'); return;
                }
                if (!RegExp(r'^\d{5,12}$').hasMatch(qqCtrl.text.trim())) {
                  setS(() => err = 'QQ 号格式不正确（5-12位数字）'); return;
                }
                if (reasonCtrl.text.trim().isEmpty) {
                  setS(() => err = '检举原因不能为空'); return;
                }
                try {
                  final auth = context.read<AuthService>();
                  final res  = await ApiService(auth).submitReport(
                    qqCtrl.text.trim(),
                    tagCtrl.text.trim(),
                    reasonCtrl.text.trim(),
                  );
                  if (!ctx.mounted) return;
                  Navigator.pop(ctx);
                  if (res['ok'] == true) {
                    _showSnack(context, '✅ 检举已提交，等待审核');
                    _load();
                  } else {
                    _showSnack(context, res['error'] ?? '提交失败');
                  }
                } catch (e) {
                  if (!ctx.mounted) return;
                  setS(() => err = '提交失败，请重试');
                }
              },
              child: const Text('提交', style: TextStyle(color: Color(0xFFe879f9))),
            ),
          ],
        ),
      ),
    );
  }

  void _showEditDialog(BuildContext context, Map<String, dynamic> report) {
    final tagCtrl    = TextEditingController(text: report['tag'] as String? ?? '');
    final reasonCtrl = TextEditingController(text: report['reason'] as String? ?? '');
    final note       = report['edit_note'] as String? ?? '';

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('修改检举', style: TextStyle()),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (note.isNotEmpty) ...[
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(8),
                  margin: const EdgeInsets.only(bottom: 10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF60a5fa).withOpacity(0.1),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: const Color(0xFF60a5fa).withOpacity(0.4)),
                  ),
                  child: Text('管理员备注：$note',
                      style: const TextStyle(color: Color(0xFF60a5fa), fontSize: 12)),
                ),
              ],
              _dlgLabel('分类标签'),
              _dlgField(tagCtrl, '例如：骚扰 / 欺诈 / 违规'),
              const SizedBox(height: 10),
              _dlgLabel('检举原因 *'),
              _dlgField(reasonCtrl, '请详细描述...', maxLines: 4),
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
              if (reasonCtrl.text.trim().isEmpty) {
                _showSnack(context, '检举原因不能为空'); return;
              }
              try {
                final auth = context.read<AuthService>();
                final res  = await ApiService(auth).editReport(
                  report['id'] as int,
                  tagCtrl.text.trim(),
                  reasonCtrl.text.trim(),
                );
                if (!ctx.mounted) return;
                Navigator.pop(ctx);
                if (res['ok'] == true) {
                  _showSnack(context, '✅ 已提交修改');
                  _load();
                } else {
                  _showSnack(context, res['error'] ?? '提交失败');
                }
              } catch (e) {
                if (!ctx.mounted) return;
                _showSnack(context, '提交失败，请重试');
              }
            },
            child: const Text('提交修改', style: TextStyle(color: Color(0xFF60a5fa))),
          ),
        ],
      ),
    );
  }

  Future<void> _deleteReport(BuildContext context, int rid) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除检举', style: TextStyle()),
        content: const Text('确认删除这条检举记录吗？',
            style: TextStyle(color: Color(0xFF9ca3af))),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消', style: TextStyle(color: Color(0xFF9ca3af)))),
          TextButton(onPressed: () => Navigator.pop(ctx, true),
              child: const Text('删除', style: TextStyle(color: Color(0xFFf87171)))),
        ],
      ),
    );
    if (ok != true) return;
    try {
      final auth = context.read<AuthService>();
      final res  = await ApiService(auth).deleteReport(rid);
      if (!mounted) return;
      if (res['ok'] == true) {
        _showSnack(context, '已删除');
        _load();
      } else {
        _showSnack(context, res['error'] ?? '删除失败');
      }
    } catch (e) {
      if (!mounted) return;
      _showSnack(context, '删除失败，请重试');
    }
  }

  void _showAppealDialog(BuildContext context, int rid) {
    final reasonCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('申请撤下', style: TextStyle()),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('请说明申请撤下的理由',
                style: TextStyle(color: Color(0xFF9ca3af), fontSize: 13)),
            const SizedBox(height: 10),
            _dlgField(reasonCtrl, '撤下理由...', maxLines: 3),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('取消', style: TextStyle(color: Color(0xFF9ca3af))),
          ),
          TextButton(
            onPressed: () async {
              if (reasonCtrl.text.trim().isEmpty) {
                _showSnack(context, '理由不能为空'); return;
              }
              try {
                final auth = context.read<AuthService>();
                final res  = await ApiService(auth).appealReport(rid, reasonCtrl.text.trim());
                if (!ctx.mounted) return;
                Navigator.pop(ctx);
                if (res['ok'] == true) {
                  _showSnack(context, '✅ 申请已提交，等待管理员审核');
                  _load();
                } else {
                  _showSnack(context, res['error'] ?? '申请失败');
                }
              } catch (e) {
                if (!ctx.mounted) return;
                _showSnack(context, '申请失败，请重试');
              }
            },
            child: const Text('提交申请', style: TextStyle(color: Color(0xFFfbbf24))),
          ),
        ],
      ),
    );
  }
}

// ── 我的检举 Tab ───────────────────────────────────────────────────────────────────

class _MyReportsTab extends StatelessWidget {
  final List<dynamic> reports;
  final List<int> appealedIds;
  final Future<void> Function() onRefresh;
  final void Function(Map<String, dynamic>) onEdit;
  final void Function(int) onDelete;
  final void Function(int) onAppeal;

  const _MyReportsTab({
    required this.reports,
    required this.appealedIds,
    required this.onRefresh,
    required this.onEdit,
    required this.onDelete,
    required this.onAppeal,
  });

  @override
  Widget build(BuildContext context) {
    if (reports.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.flag_outlined, size: 52, color: Color(0xFF374151)),
            const SizedBox(height: 12),
            const Text('暂无检举记录', style: TextStyle(color: Color(0xFF6b7280))),
            const SizedBox(height: 8),
            const Text('点击右上角 + 提交检举',
                style: TextStyle(color: Color(0xFF4b5563), fontSize: 13)),
          ],
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: onRefresh,
      color: const Color(0xFFe879f9),
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: reports.length,
        itemBuilder: (ctx, i) {
          final r   = reports[i] as Map<String, dynamic>;
          final rid = r['id'] as int;
          final status = r['status'] as String? ?? 'pending';
          final hasAppealed = appealedIds.contains(rid);
          return _MyReportCard(
            report: r,
            hasAppealed: hasAppealed,
            onEdit: status == 'editing' ? () => onEdit(r) : null,
            onDelete: () => onDelete(rid),
            onAppeal: (status == 'approved' && !hasAppealed) ? () => onAppeal(rid) : null,
          );
        },
      ),
    );
  }
}

class _MyReportCard extends StatelessWidget {
  final Map<String, dynamic> report;
  final bool hasAppealed;
  final VoidCallback? onEdit;
  final VoidCallback onDelete;
  final VoidCallback? onAppeal;

  const _MyReportCard({
    required this.report,
    required this.hasAppealed,
    required this.onEdit,
    required this.onDelete,
    required this.onAppeal,
  });

  @override
  Widget build(BuildContext context) {
    final status     = report['status'] as String? ?? 'pending';
    final statusLabel = _statusLabels[status] ?? status;
    final statusColor = _statusColors[status] ?? const Color(0xFF9ca3af);
    final tag     = report['tag'] as String? ?? '';
    final note    = report['edit_note'] as String? ?? '';
    final ts      = report['created_at'] as int? ?? 0;
    final dateStr = ts > 0
        ? DateTime.fromMillisecondsSinceEpoch(ts * 1000).toLocal().toString().substring(0, 16)
        : '';

    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: statusColor.withOpacity(0.3)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // header row
            Row(
              children: [
                Expanded(
                  child: Row(children: [
                    const Icon(Icons.person_off_outlined, color: Color(0xFFf87171), size: 16),
                    const SizedBox(width: 6),
                    Text('QQ: ${report['target_qq'] ?? ''}',
                        style: const TextStyle(
                            fontWeight: FontWeight.w600, fontSize: 15)),
                    if (tag.isNotEmpty) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        decoration: BoxDecoration(
                          color: const Color(0xFFe879f9).withOpacity(0.1),
                          borderRadius: BorderRadius.circular(4),
                          border: Border.all(color: const Color(0xFFe879f9).withOpacity(0.4)),
                        ),
                        child: Text(tag,
                            style: const TextStyle(color: Color(0xFFe879f9), fontSize: 11)),
                      ),
                    ],
                  ]),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: statusColor.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(statusLabel,
                      style: TextStyle(color: statusColor, fontSize: 12)),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(report['reason'] as String? ?? '',
                style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 13)),

            // edit note (when status=editing)
            if (note.isNotEmpty) ...[
              const SizedBox(height: 8),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color(0xFF60a5fa).withOpacity(0.1),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: const Color(0xFF60a5fa).withOpacity(0.4)),
                ),
                child: Text('管理员：$note',
                    style: const TextStyle(color: Color(0xFF60a5fa), fontSize: 12)),
              ),
            ],

            const SizedBox(height: 8),
            Row(
              children: [
                Text(dateStr,
                    style: const TextStyle(color: Color(0xFF6b7280), fontSize: 11)),
                const Spacer(),
                // 修改按钮（仅 editing 状态）
                if (onEdit != null)
                  TextButton.icon(
                    onPressed: onEdit,
                    icon: const Icon(Icons.edit_outlined, size: 14),
                    label: const Text('修改', style: TextStyle(fontSize: 12)),
                    style: TextButton.styleFrom(
                      foregroundColor: const Color(0xFF60a5fa),
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      minimumSize: Size.zero,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  ),
                // 申请撤下（已通过且未申请过）
                if (onAppeal != null)
                  TextButton.icon(
                    onPressed: onAppeal,
                    icon: const Icon(Icons.undo_outlined, size: 14),
                    label: const Text('申请撤下', style: TextStyle(fontSize: 12)),
                    style: TextButton.styleFrom(
                      foregroundColor: const Color(0xFFfbbf24),
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      minimumSize: Size.zero,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  ),
                if (hasAppealed && status == 'approved')
                  const Padding(
                    padding: EdgeInsets.only(left: 8),
                    child: Text('已申请撤下',
                        style: TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
                  ),
                const SizedBox(width: 4),
                // 删除（不可删已通过且只剩≤2条的，但后端会拒绝，所以前端统一显示）
                if (status != 'approved')
                  IconButton(
                    icon: const Icon(Icons.delete_outline,
                        color: Color(0xFFf87171), size: 18),
                    onPressed: onDelete,
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ── 公开列表 Tab ───────────────────────────────────────────────────────────────────

class _PublicListTab extends StatefulWidget {
  final bool canView;
  final int approvedCount;
  final List<dynamic> groups;
  final Future<void> Function() onRefresh;
  final List<int> appealedIds;
  final void Function(int) onAppeal;

  const _PublicListTab({
    required this.canView,
    required this.approvedCount,
    required this.groups,
    required this.onRefresh,
    required this.appealedIds,
    required this.onAppeal,
  });

  @override
  State<_PublicListTab> createState() => _PublicListTabState();
}

class _PublicListTabState extends State<_PublicListTab> {
  final _searchCtrl = TextEditingController();
  List<dynamic> _filtered = [];

  @override
  void initState() {
    super.initState();
    _filtered = widget.groups;
    _searchCtrl.addListener(_filter);
  }

  @override
  void didUpdateWidget(_PublicListTab old) {
    super.didUpdateWidget(old);
    if (old.groups != widget.groups) {
      _filtered = widget.groups;
      _filter();
    }
  }

  void _filter() {
    final q = _searchCtrl.text.trim().toLowerCase();
    setState(() {
      _filtered = q.isEmpty
          ? widget.groups
          : widget.groups.where((g) {
              final qq = (g['qq'] as String? ?? '').toLowerCase();
              return qq.contains(q);
            }).toList();
    });
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.canView) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.lock_outline, size: 48, color: Color(0xFF374151)),
              const SizedBox(height: 16),
              const Text('公开名单已锁定',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text(
                '需要至少 2 条已通过的检举才能查看公开名单\n（当前：${widget.approvedCount} 条）',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Color(0xFF9ca3af), height: 1.5),
              ),
              const SizedBox(height: 24),
              const Text('提交检举后，等管理员审核通过即可解锁',
                  style: TextStyle(color: Color(0xFF6b7280), fontSize: 13)),
            ],
          ),
        ),
      );
    }

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
          child: TextField(
            controller: _searchCtrl,
            style: const TextStyle(),
            decoration: InputDecoration(
              hintText: '搜索 QQ 号',
              hintStyle: const TextStyle(color: Color(0xFF6b7280)),
              prefixIcon: const Icon(Icons.search, color: Color(0xFF6b7280)),
              filled: true,
              fillColor: const Color(0xFF16213e),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
              contentPadding: const EdgeInsets.symmetric(vertical: 10),
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
          child: Row(children: [
            Text('共 ${_filtered.length} 个 QQ',
                style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
          ]),
        ),
        Expanded(
          child: _filtered.isEmpty
              ? const Center(
                  child: Text('未找到相关记录',
                      style: TextStyle(color: Color(0xFF6b7280))))
              : RefreshIndicator(
                  onRefresh: widget.onRefresh,
                  color: const Color(0xFFe879f9),
                  child: ListView.builder(
                    padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                    itemCount: _filtered.length,
                    itemBuilder: (ctx, i) {
                      final g = _filtered[i] as Map<String, dynamic>;
                      final reports = g['reports'] as List<dynamic>? ?? [];
                      return _PublicGroupCard(
                        qq: g['qq'] as String? ?? '',
                        count: g['count'] as int? ?? reports.length,
                        reports: reports,
                        appealedIds: widget.appealedIds,
                        onAppeal: widget.onAppeal,
                      );
                    },
                  ),
                ),
        ),
      ],
    );
  }
}

class _PublicGroupCard extends StatefulWidget {
  final String qq;
  final int count;
  final List<dynamic> reports;
  final List<int> appealedIds;
  final void Function(int) onAppeal;

  const _PublicGroupCard({
    required this.qq,
    required this.count,
    required this.reports,
    required this.appealedIds,
    required this.onAppeal,
  });

  @override
  State<_PublicGroupCard> createState() => _PublicGroupCardState();
}

class _PublicGroupCardState extends State<_PublicGroupCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: const Color(0xFFf87171).withOpacity(0.3)),
      ),
      child: Column(
        children: [
          InkWell(
            borderRadius: BorderRadius.circular(12),
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 20,
                    backgroundColor: const Color(0xFFf87171).withOpacity(0.15),
                    child: const Icon(Icons.person_off,
                        color: Color(0xFFf87171), size: 20),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('QQ: ${widget.qq}',
                            style: const TextStyle(
                                fontWeight: FontWeight.w600,
                                fontSize: 15)),
                        Text('${widget.count} 条检举记录',
                            style: const TextStyle(
                                color: Color(0xFF9ca3af), fontSize: 12)),
                      ],
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFf87171).withOpacity(0.15),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text('${widget.count}条',
                        style: const TextStyle(
                            color: Color(0xFFf87171),
                            fontWeight: FontWeight.bold,
                            fontSize: 13)),
                  ),
                  const SizedBox(width: 6),
                  Icon(_expanded ? Icons.expand_less : Icons.expand_more,
                      color: const Color(0xFF6b7280)),
                ],
              ),
            ),
          ),
          if (_expanded)
            ...widget.reports.map((r) {
              final rid = r['id'] as int;
              final hasAppealed = widget.appealedIds.contains(rid);
              final tag = r['tag'] as String? ?? '';
              final ts  = r['created_at'] as int? ?? 0;
              final dateStr = ts > 0
                  ? DateTime.fromMillisecondsSinceEpoch(ts * 1000)
                      .toLocal()
                      .toString()
                      .substring(0, 16)
                  : '';
              return Container(
                margin: const EdgeInsets.fromLTRB(14, 0, 14, 10),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainer,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      if (tag.isNotEmpty)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          margin: const EdgeInsets.only(right: 8),
                          decoration: BoxDecoration(
                            color: const Color(0xFFe879f9).withOpacity(0.1),
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(color: const Color(0xFFe879f9).withOpacity(0.4)),
                          ),
                          child: Text(tag,
                              style: const TextStyle(
                                  color: Color(0xFFe879f9), fontSize: 11)),
                        ),
                      Text(dateStr,
                          style: const TextStyle(
                              color: Color(0xFF6b7280), fontSize: 11)),
                    ]),
                    const SizedBox(height: 6),
                    Text(r['reason'] as String? ?? '',
                        style: const TextStyle(
                            color: Color(0xFF9ca3af), fontSize: 13)),
                    const SizedBox(height: 6),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        if (!hasAppealed)
                          TextButton.icon(
                            onPressed: () => widget.onAppeal(rid),
                            icon: const Icon(Icons.undo_outlined, size: 14),
                            label: const Text('申请撤下', style: TextStyle(fontSize: 12)),
                            style: TextButton.styleFrom(
                              foregroundColor: const Color(0xFFfbbf24),
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 2),
                              minimumSize: Size.zero,
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                            ),
                          )
                        else
                          const Text('已申请撤下',
                              style: TextStyle(
                                  color: Color(0xFF6b7280), fontSize: 12)),
                      ],
                    ),
                  ],
                ),
              );
            }),
        ],
      ),
    );
  }
}

// ── 辅助 ──────────────────────────────────────────────────────────────────────────

class _ErrorView extends StatelessWidget {
  final String msg;
  final VoidCallback onRetry;
  const _ErrorView({required this.msg, required this.onRetry});

  @override
  Widget build(BuildContext context) => Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(msg, style: const TextStyle(color: Color(0xFF9ca3af))),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: onRetry,
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFFe879f9)),
              child: const Text('重试'),
            ),
          ],
        ),
      );
}

Widget _dlgLabel(String text) => Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Text(text,
          style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 12)),
    );

Widget _dlgField(TextEditingController ctrl, String hint,
    {int maxLines = 1, TextInputType? keyboardType}) =>
    TextField(
      controller: ctrl,
      maxLines: maxLines,
      keyboardType: keyboardType,
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
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      ),
    );

void _showSnack(BuildContext context, String msg) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text(msg), backgroundColor: const Color(0xFF16213e)),
  );
}
