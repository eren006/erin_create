import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../services/auth_service.dart';
import '../services/api_service.dart';

// ── 状态常量 ───────────────────────────────────────────────────────────────────

const _statusLabels = {
  'ongoing':   '进行中',
  'completed': '已完结',
  'dropped':   '弃坑',
};

const _statusColors = {
  'ongoing':   Color(0xFF34d399),
  'completed': Color(0xFF8b7cf6),
  'dropped':   Color(0xFF6b7280),
};

const _genres = ['古言', '现言', '仙侠', '都市', '架空', '恐怖', '科幻', '其他'];

// ══════════════════════════════════════════════════════════════════════════════
// 戏录 Tab（嵌入 GuildScreen 使用）
// ══════════════════════════════════════════════════════════════════════════════

class DramaLogTab extends StatefulWidget {
  const DramaLogTab({super.key});
  @override
  State<DramaLogTab> createState() => _DramaLogTabState();
}

class _DramaLogTabState extends State<DramaLogTab>
    with AutomaticKeepAliveClientMixin {
  bool _loading = true;
  String? _error;
  List<dynamic> _all = [];
  String _filter = 'all'; // all / ongoing / completed / dropped

  @override
  bool get wantKeepAlive => true;

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
      final data = await ApiService(auth).getDrama();
      if (!mounted) return;
      setState(() { _all = data; _loading = false; });
    } catch (_) {
      if (!mounted) return;
      setState(() { _error = '加载失败，请重试'; _loading = false; });
    }
  }

  List<dynamic> get _filtered {
    if (_filter == 'all') return _all;
    return _all.where((e) => (e['status'] as String?) == _filter).toList();
  }

  // ── 新建戏录 ───────────────────────────────────────────────────────────────

  void _showAddSheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surfaceContainer,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => _AddDramaSheet(onSaved: _load),
    );
  }

  // ── 删除 ──────────────────────────────────────────────────────────────────

  Future<void> _delete(int id, String title) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除戏录', style: TextStyle()),
        content: Text('确定删除「$title」？',
            style: const TextStyle(color: Color(0xFF9ca3af))),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消', style: TextStyle(color: Color(0xFF9ca3af)))),
          TextButton(onPressed: () => Navigator.pop(ctx, true),
              child: const Text('删除', style: TextStyle(color: Color(0xFFf87171)))),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      final auth = context.read<AuthService>();
      await ApiService(auth).deleteDrama(id);
      _load();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('删除失败，请重试')));
      }
    }
  }

  // ── 修改进度 ──────────────────────────────────────────────────────────────

  Future<void> _updateStatus(int id, String current) async {
    final statuses = ['ongoing', 'completed', 'dropped'];
    final next = statuses[(statuses.indexOf(current) + 1) % statuses.length];
    try {
      final auth = context.read<AuthService>();
      await ApiService(auth).updateDramaStatus(id, next);
      _load();
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('状态更新失败，请重试')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (_loading) {
      return const Center(
          child: CircularProgressIndicator(color: Color(0xFF8b7cf6)));
    }
    if (_error != null) {
      return Center(child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(_error!, style: const TextStyle(color: Color(0xFF9ca3af))),
          const SizedBox(height: 16),
          ElevatedButton(
            onPressed: _load,
            style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF8b7cf6)),
            child: const Text('重试'),
          ),
        ],
      ));
    }

    final list = _filtered;

    return Stack(
      children: [
        Column(children: [
          // ── 过滤器 ───────────────────────────────────────────────────────
          _FilterBar(current: _filter, onSelect: (v) => setState(() => _filter = v)),
          // ── 列表 ─────────────────────────────────────────────────────────
          Expanded(
            child: list.isEmpty
                ? _Empty(filter: _filter, onAdd: _showAddSheet)
                : RefreshIndicator(
                    onRefresh: _load,
                    color: const Color(0xFF8b7cf6),
                    child: ListView.builder(
                      padding: const EdgeInsets.fromLTRB(12, 8, 12, 80),
                      itemCount: list.length,
                      itemBuilder: (ctx, i) => _DramaCard(
                        entry: list[i] as Map<String, dynamic>,
                        onDelete: () => _delete(
                            list[i]['id'] as int,
                            list[i]['title'] as String? ?? ''),
                        onStatusTap: () => _updateStatus(
                            list[i]['id'] as int,
                            list[i]['status'] as String? ?? 'ongoing'),
                        onEdit: () {
                          showModalBottomSheet(
                            context: context,
                            isScrollControlled: true,
                            backgroundColor: Theme.of(context).colorScheme.surfaceContainer,
                            shape: const RoundedRectangleBorder(
                                borderRadius: BorderRadius.vertical(
                                    top: Radius.circular(20))),
                            builder: (_) => _AddDramaSheet(
                                existing: list[i] as Map<String, dynamic>,
                                onSaved: _load),
                          );
                        },
                      ),
                    ),
                  ),
          ),
        ]),
        // ── 悬浮按钮 ──────────────────────────────────────────────────────
        Positioned(
          right: 16,
          bottom: 16,
          child: FloatingActionButton(
            heroTag: 'drama_fab',
            backgroundColor: const Color(0xFF8b7cf6),
            onPressed: _showAddSheet,
            child: const Icon(Icons.add),
          ),
        ),
      ],
    );
  }
}

// ── 过滤条 ────────────────────────────────────────────────────────────────────

class _FilterBar extends StatelessWidget {
  final String current;
  final void Function(String) onSelect;
  const _FilterBar({required this.current, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final filters = [
      ('all', '全部'),
      ('ongoing', '进行中'),
      ('completed', '已完结'),
      ('dropped', '弃坑'),
    ];
    final surface = Theme.of(context).colorScheme.surfaceContainer;
    final divider = Theme.of(context).colorScheme.onSurface.withAlpha(20);
    return Container(
      color: surface,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: filters.map((f) {
          final active = f.$1 == current;
          final color = f.$1 == 'all'
              ? const Color(0xFF8b7cf6)
              : (_statusColors[f.$1] ?? const Color(0xFF8b7cf6));
          return GestureDetector(
            onTap: () => onSelect(f.$1),
            child: Container(
              margin: const EdgeInsets.only(right: 8),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
              decoration: BoxDecoration(
                color: active ? color.withAlpha(40) : Colors.transparent,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: active ? color : divider),
              ),
              child: Text(f.$2,
                  style: TextStyle(
                      color: active ? color : Theme.of(context).colorScheme.onSurface.withAlpha(120),
                      fontSize: 12,
                      fontWeight: active ? FontWeight.w600 : FontWeight.normal)),
            ),
          );
        }).toList(),
      ),
    );
  }
}

// ── 戏录卡片 ──────────────────────────────────────────────────────────────────

class _DramaCard extends StatelessWidget {
  final Map<String, dynamic> entry;
  final VoidCallback onDelete;
  final VoidCallback onStatusTap;
  final VoidCallback onEdit;
  const _DramaCard({
    required this.entry,
    required this.onDelete,
    required this.onStatusTap,
    required this.onEdit,
  });

  @override
  Widget build(BuildContext context) {
    final title       = entry['title']        as String? ?? '';
    final myChar      = entry['my_char']      as String? ?? '';
    final partnerChar = entry['partner_char'] as String? ?? '';
    final partnerQq   = entry['partner_qq']   as String? ?? '';
    final genre       = entry['genre']        as String? ?? '';
    final status      = entry['status']       as String? ?? 'ongoing';
    final notes       = entry['notes']        as String? ?? '';
    final content     = entry['content']      as String? ?? '';
    final startTs     = entry['start_ts']     as int?;
    final endTs       = entry['end_ts']       as int?;
    final wordCount   = content.trim().isEmpty ? 0 : content.trim().length;

    final statusColor = _statusColors[status] ?? const Color(0xFF6b7280);
    final statusLabel = _statusLabels[status] ?? status;

    String? dateStr;
    if (startTs != null && startTs > 0) {
      final s = DateTime.fromMillisecondsSinceEpoch(startTs * 1000).toLocal();
      dateStr = '${s.year}/${s.month.toString().padLeft(2,'0')}/${s.day.toString().padLeft(2,'0')}';
      if (endTs != null && endTs > 0) {
        final e = DateTime.fromMillisecondsSinceEpoch(endTs * 1000).toLocal();
        dateStr += ' → ${e.year}/${e.month.toString().padLeft(2,'0')}/${e.day.toString().padLeft(2,'0')}';
      } else if (status == 'ongoing') {
        dateStr += ' → 至今';
      }
    }

    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: statusColor.withAlpha(60)),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onEdit,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            // 标题行
            Row(children: [
              Expanded(
                child: Text(title.isEmpty ? '（无题）' : title,
                    style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600)),
              ),
              // 状态 chip（点击切换）
              GestureDetector(
                onTap: onStatusTap,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                  decoration: BoxDecoration(
                    color: statusColor.withAlpha(35),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: statusColor.withAlpha(120)),
                  ),
                  child: Text(statusLabel,
                      style: TextStyle(color: statusColor, fontSize: 11)),
                ),
              ),
            ]),
            const SizedBox(height: 8),

            // CP 行
            if (myChar.isNotEmpty || partnerChar.isNotEmpty)
              Row(children: [
                const Icon(Icons.swap_horiz, color: Color(0xFF4b5563), size: 14),
                const SizedBox(width: 4),
                if (myChar.isNotEmpty)
                  Text(myChar,
                      style: const TextStyle(
                          color: Color(0xFFa78bfa), fontSize: 13)),
                if (myChar.isNotEmpty && partnerChar.isNotEmpty)
                  const Text('  ×  ',
                      style: TextStyle(color: Color(0xFF4b5563), fontSize: 13)),
                if (partnerChar.isNotEmpty)
                  Text(partnerChar,
                      style: const TextStyle(
                          color: Color(0xFF9ca3af), fontSize: 13)),
                const Spacer(),
                if (partnerQq.isNotEmpty)
                  GestureDetector(
                    onLongPress: () {
                      Clipboard.setData(ClipboardData(text: partnerQq));
                      ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                              content: Text('已复制 QQ'),
                              duration: Duration(seconds: 1)));
                    },
                    child: Row(children: [
                      const Icon(Icons.person_outline,
                          color: Color(0xFF4b5563), size: 13),
                      const SizedBox(width: 3),
                      Text(partnerQq,
                          style: const TextStyle(
                              color: Color(0xFF6b7280), fontSize: 12)),
                    ]),
                  ),
              ]),

            // 题材 + 日期行
            const SizedBox(height: 6),
            Row(children: [
              if (genre.isNotEmpty)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surfaceContainer,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(genre,
                      style: const TextStyle(
                          color: Color(0xFF9ca3af), fontSize: 11)),
                ),
              if (dateStr != null) ...[
                const SizedBox(width: 8),
                Text(dateStr,
                    style: const TextStyle(
                        color: Color(0xFF4b5563), fontSize: 11)),
              ],
              if (wordCount > 0) ...[
                const SizedBox(width: 8),
                Text('$wordCount 字',
                    style: const TextStyle(
                        color: Color(0xFF8b7cf6), fontSize: 11)),
              ],
              const Spacer(),
              // 删除按钮
              GestureDetector(
                onTap: onDelete,
                child: const Icon(Icons.delete_outline,
                    color: Color(0xFF4b5563), size: 18),
              ),
            ]),

            // 备注
            if (notes.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(notes,
                  style: const TextStyle(
                      color: Color(0xFF6b7280),
                      fontSize: 12,
                      height: 1.5),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis),
            ],
          ]),
        ),
      ),
    );
  }
}

// ── 空状态 ────────────────────────────────────────────────────────────────────

class _Empty extends StatelessWidget {
  final String filter;
  final VoidCallback onAdd;
  const _Empty({required this.filter, required this.onAdd});

  @override
  Widget build(BuildContext context) {
    final msg = filter == 'all'
        ? '还没有戏录，记录你的第一部戏吧'
        : '没有「${_statusLabels[filter] ?? filter}」的戏录';
    return Center(
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        const Icon(Icons.auto_stories_outlined,
            size: 56, color: Color(0xFF374151)),
        const SizedBox(height: 12),
        Text(msg,
            style: const TextStyle(color: Color(0xFF6b7280), fontSize: 15)),
        if (filter == 'all') ...[
          const SizedBox(height: 20),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF8b7cf6),
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10)),
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            ),
            onPressed: onAdd,
            icon: const Icon(Icons.add, size: 18),
            label: const Text('建立戏录'),
          ),
        ],
      ]),
    );
  }
}

// ── 新建/编辑 bottom sheet ─────────────────────────────────────────────────────

class _AddDramaSheet extends StatefulWidget {
  final Map<String, dynamic>? existing; // null = 新建，非 null = 编辑
  final VoidCallback onSaved;
  const _AddDramaSheet({this.existing, required this.onSaved});
  @override
  State<_AddDramaSheet> createState() => _AddDramaSheetState();
}

class _AddDramaSheetState extends State<_AddDramaSheet> {
  final _titleCtrl       = TextEditingController();
  final _myCharCtrl      = TextEditingController();
  final _partnerCharCtrl = TextEditingController();
  final _partnerQqCtrl   = TextEditingController();
  final _contentCtrl     = TextEditingController();
  final _notesCtrl       = TextEditingController();
  String _genre  = '古言';
  String _status = 'ongoing';
  DateTime? _startDate;
  DateTime? _endDate;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _titleCtrl.text       = e['title']        as String? ?? '';
      _myCharCtrl.text      = e['my_char']      as String? ?? '';
      _partnerCharCtrl.text = e['partner_char'] as String? ?? '';
      _partnerQqCtrl.text   = e['partner_qq']   as String? ?? '';
      _contentCtrl.text     = e['content']      as String? ?? '';
      _notesCtrl.text       = e['notes']        as String? ?? '';
      final g = e['genre'] as String? ?? '';
      _genre                = g.isNotEmpty ? g : '古言';
      _status               = e['status']       as String? ?? 'ongoing';
      final sts = e['start_ts'] as int?;
      final ets = e['end_ts']   as int?;
      if (sts != null && sts > 0)
        _startDate = DateTime.fromMillisecondsSinceEpoch(sts * 1000);
      if (ets != null && ets > 0)
        _endDate   = DateTime.fromMillisecondsSinceEpoch(ets * 1000);
    }
  }

  @override
  void dispose() {
    _titleCtrl.dispose(); _myCharCtrl.dispose();
    _partnerCharCtrl.dispose(); _partnerQqCtrl.dispose();
    _contentCtrl.dispose(); _notesCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickDate(bool isStart) async {
    final initial = isStart
        ? (_startDate ?? DateTime.now())
        : (_endDate ?? _startDate ?? DateTime.now());
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2020),
      lastDate: DateTime(2099),
      builder: (ctx, child) => Theme(
        data: ThemeData.dark().copyWith(
          colorScheme: const ColorScheme.dark(
            primary: Color(0xFF8b7cf6),
            surface: Color(0xFF16213e),
          ),
        ),
        child: child!,
      ),
    );
    if (picked == null) return;
    setState(() {
      if (isStart) _startDate = picked;
      else          _endDate   = picked;
    });
  }

  Future<void> _save() async {
    if (_saving) return;
    setState(() => _saving = true);
    try {
      final auth = context.read<AuthService>();
      final api  = ApiService(auth);
      final payload = {
        'title':        _titleCtrl.text.trim(),
        'my_char':      _myCharCtrl.text.trim(),
        'partner_char': _partnerCharCtrl.text.trim(),
        'partner_qq':   _partnerQqCtrl.text.trim(),
        'genre':        _genre,
        'status':       _status,
        'content':      _contentCtrl.text.trim(),
        'notes':        _notesCtrl.text.trim(),
        'start_ts': _startDate != null
            ? (_startDate!.millisecondsSinceEpoch ~/ 1000) : null,
        'end_ts': _endDate != null
            ? (_endDate!.millisecondsSinceEpoch ~/ 1000) : null,
      };
      if (widget.existing != null) {
        await api.updateDrama(widget.existing!['id'] as int, payload);
      } else {
        await api.addDrama(payload);
      }
      if (!mounted) return;
      Navigator.pop(context);
      widget.onSaved();
    } catch (_) {
      if (!mounted) return;
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('保存失败，请重试')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final isEdit = widget.existing != null;
    return Padding(
      padding: EdgeInsets.only(
          left: 20, right: 20, top: 20,
          bottom: MediaQuery.of(context).viewInsets.bottom + 24),
      child: SingleChildScrollView(
        child: Column(mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
          // 标题栏
          Row(children: [
            Text(isEdit ? '编辑戏录' : '新建戏录',
                style: const TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold)),
            const Spacer(),
            IconButton(
              icon: const Icon(Icons.close, color: Color(0xFF9ca3af)),
              onPressed: () => Navigator.pop(context),
            ),
          ]),
          const SizedBox(height: 14),

          // 戏名
          _Field(_titleCtrl, '戏名 / 剧本标题'),
          const SizedBox(height: 10),

          // CP 行
          Row(children: [
            Expanded(child: _Field(_myCharCtrl, '我的 OC')),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 8),
              child: Text('×', style: TextStyle(color: Color(0xFF6b7280), fontSize: 16)),
            ),
            Expanded(child: _Field(_partnerCharCtrl, '对家 OC')),
          ]),
          const SizedBox(height: 10),

          // 对家 QQ
          _Field(_partnerQqCtrl, '对家 QQ（选填）',
              keyboardType: TextInputType.number),
          const SizedBox(height: 14),

          // 题材
          const Text('题材',
              style: TextStyle(color: Color(0xFF9ca3af), fontSize: 12)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8, runSpacing: 8,
            children: _genres.map((g) {
              final active = g == _genre;
              return GestureDetector(
                onTap: () => setState(() => _genre = g),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 14, vertical: 6),
                  decoration: BoxDecoration(
                    color: active
                        ? const Color(0xFF8b7cf6).withAlpha(40)
                        : Theme.of(context).colorScheme.surface,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                        color: active
                            ? const Color(0xFF8b7cf6)
                            : const Color(0xFF374151)),
                  ),
                  child: Text(g,
                      style: TextStyle(
                          color: active
                              ? const Color(0xFF8b7cf6)
                              : const Color(0xFF9ca3af),
                          fontSize: 13)),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 14),

          // 进度
          const Text('进度',
              style: TextStyle(color: Color(0xFF9ca3af), fontSize: 12)),
          const SizedBox(height: 8),
          Row(children: [
            ...['ongoing', 'completed', 'dropped'].map((s) {
              final active = s == _status;
              final color  = _statusColors[s]!;
              return GestureDetector(
                onTap: () => setState(() => _status = s),
                child: Container(
                  margin: const EdgeInsets.only(right: 10),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 16, vertical: 7),
                  decoration: BoxDecoration(
                    color: active ? color.withAlpha(40) : Theme.of(context).colorScheme.surface,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                        color: active ? color : const Color(0xFF374151)),
                  ),
                  child: Text(_statusLabels[s]!,
                      style: TextStyle(
                          color: active ? color : const Color(0xFF9ca3af),
                          fontSize: 13)),
                ),
              );
            }),
          ]),
          const SizedBox(height: 14),

          // 日期
          Row(children: [
            Expanded(child: _DatePicker(
              label: '开始日期',
              date: _startDate,
              onTap: () => _pickDate(true),
            )),
            const SizedBox(width: 10),
            Expanded(child: _DatePicker(
              label: '结束日期',
              date: _endDate,
              onTap: () => _pickDate(false),
            )),
          ]),
          const SizedBox(height: 10),

          // 正文
          Row(children: [
            const Text('正文',
                style: TextStyle(color: Color(0xFF9ca3af), fontSize: 12)),
            const Spacer(),
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: _contentCtrl,
              builder: (_, v, __) {
                final wc = v.text.trim().isEmpty ? 0 : v.text.trim().length;
                return Text('$wc 字',
                    style: const TextStyle(
                        color: Color(0xFF6b7280), fontSize: 11));
              },
            ),
          ]),
          const SizedBox(height: 8),
          _Field(_contentCtrl, '在这里写下这段戏的内容…', maxLines: 10),
          const SizedBox(height: 10),

          // 备注
          _Field(_notesCtrl, '备注 / 感受（选填）', maxLines: 3),
          const SizedBox(height: 18),

          // 保存按钮
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF8b7cf6),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(
                      width: 20, height: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2))
                  : Text(isEdit ? '保存修改' : '建立戏录',
                      style: const TextStyle(fontSize: 15)),
            ),
          ),
        ]),
      ),
    );
  }
}

// ── 公共小部件 ─────────────────────────────────────────────────────────────────

class _Field extends StatelessWidget {
  final TextEditingController ctrl;
  final String hint;
  final int maxLines;
  final TextInputType keyboardType;
  const _Field(this.ctrl, this.hint,
      {this.maxLines = 1,
      this.keyboardType = TextInputType.text});

  @override
  Widget build(BuildContext context) => TextField(
    controller: ctrl,
    maxLines: maxLines,
    keyboardType: keyboardType,
    style: const TextStyle(fontSize: 13),
    decoration: InputDecoration(
      hintText: hint,
      hintStyle: const TextStyle(color: Color(0xFF4b5563), fontSize: 13),
      filled: true,
      fillColor: Theme.of(context).colorScheme.surface,
      border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: BorderSide.none),
      focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Color(0xFF8b7cf6))),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
    ),
  );
}

class _DatePicker extends StatelessWidget {
  final String label;
  final DateTime? date;
  final VoidCallback onTap;
  const _DatePicker({required this.label, required this.date, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final str = date == null
        ? null
        : '${date!.year}/${date!.month.toString().padLeft(2,'0')}/${date!.day.toString().padLeft(2,'0')}';
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainer,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(children: [
          const Icon(Icons.calendar_today_outlined,
              color: Color(0xFF6b7280), size: 14),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              str ?? label,
              style: TextStyle(
                  color: str != null
                      ? Colors.white
                      : const Color(0xFF4b5563),
                  fontSize: 12),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ]),
      ),
    );
  }
}
