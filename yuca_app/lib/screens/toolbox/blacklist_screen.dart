import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../services/auth_service.dart';
import '../../services/api_service.dart';

class BlacklistScreen extends StatefulWidget {
  const BlacklistScreen({super.key});
  @override
  State<BlacklistScreen> createState() => _BlacklistScreenState();
}

class _BlacklistScreenState extends State<BlacklistScreen> {
  bool _loading = true;
  String? _error;
  List<dynamic> _items = [];
  final _searchCtrl = TextEditingController();
  List<dynamic> _filtered = [];

  @override
  void initState() {
    super.initState();
    _searchCtrl.addListener(_filter);
    _load();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final auth = context.read<AuthService>();
      final data = await ApiService(auth).getBlacklist();
      if (!mounted) return;
      setState(() { _items = data; _filtered = data; _loading = false; });
    } catch (_) {
      if (!mounted) return;
      setState(() { _error = '加载失败，请重试'; _loading = false; });
    }
  }

  void _filter() {
    final q = _searchCtrl.text.trim().toLowerCase();
    setState(() {
      _filtered = q.isEmpty
          ? _items
          : _items.where((i) {
              final nick = (i['nickname'] as String? ?? '').toLowerCase();
              final qq   = (i['qq']       as String? ?? '').toLowerCase();
              return nick.contains(q) || qq.contains(q);
            }).toList();
    });
  }

  void _showAddDialog() {
    final nicknameCtrl  = TextEditingController();
    final qqCtrl        = TextEditingController();
    final reasonCtrl    = TextEditingController();
    final notesCtrl     = TextEditingController();
    final happenedCtrl  = TextEditingController();
    String? err;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF16213e),
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setS) => SingleChildScrollView(
          padding: EdgeInsets.only(
            left: 20, right: 20, top: 20,
            bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Text('添加黑名单', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const Spacer(),
                IconButton(icon: const Icon(Icons.close, color: Color(0xFF9ca3af)),
                    onPressed: () => Navigator.pop(ctx)),
              ]),
              if (err != null) ...[
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFF7f1d1d),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(err!, style: const TextStyle(color: Color(0xFFfca5a5), fontSize: 13)),
                ),
              ],
              const SizedBox(height: 12),
              Row(children: [
                Expanded(child: TextField(
                  controller: nicknameCtrl,
                  style: const TextStyle(),
                  autofocus: true,
                  decoration: _inputDeco('昵称 *'),
                )),
                const SizedBox(width: 10),
                Expanded(child: TextField(
                  controller: qqCtrl,
                  style: const TextStyle(),
                  keyboardType: TextInputType.number,
                  decoration: _inputDeco('QQ（可选）'),
                )),
              ]),
              const SizedBox(height: 10),
              TextField(
                controller: reasonCtrl,
                style: const TextStyle(),
                maxLines: 3,
                decoration: _inputDeco('拉黑原因 *'),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: happenedCtrl,
                style: const TextStyle(),
                decoration: _inputDeco('事发时间（可选）'),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: notesCtrl,
                style: const TextStyle(),
                maxLines: 2,
                decoration: _inputDeco('备注（可选）'),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFFf87171),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  onPressed: () async {
                    if (nicknameCtrl.text.trim().isEmpty) {
                      setS(() => err = '昵称不能为空'); return;
                    }
                    if (reasonCtrl.text.trim().isEmpty) {
                      setS(() => err = '拉黑原因不能为空'); return;
                    }
                    try {
                      final auth = context.read<AuthService>();
                      await ApiService(auth).addBlacklistItem({
                        'nickname':    nicknameCtrl.text.trim(),
                        'qq':          qqCtrl.text.trim(),
                        'reason':      reasonCtrl.text.trim(),
                        'happened_at': happenedCtrl.text.trim(),
                        'notes':       notesCtrl.text.trim(),
                      });
                      if (!ctx.mounted) return;
                      Navigator.pop(ctx);
                      _load();
                    } catch (_) {
                      setS(() => err = '添加失败，请重试');
                    }
                  },
                  child: const Text('添加'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _delete(int id) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('移除', style: TextStyle()),
        content: const Text('确定从黑名单移除吗？', style: TextStyle(color: Color(0xFF9ca3af))),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消', style: TextStyle(color: Color(0xFF9ca3af)))),
          TextButton(onPressed: () => Navigator.pop(ctx, true),
              child: const Text('移除', style: TextStyle(color: Color(0xFFf87171)))),
        ],
      ),
    );
    if (ok != true) return;
    final auth = context.read<AuthService>();
    await ApiService(auth).deleteBlacklistItem(id);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('黑名单', style: TextStyle()),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            icon: const Icon(Icons.add, color: Color(0xFFf87171)),
            onPressed: _showAddDialog,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFFf87171)))
          : _error != null
              ? _ErrorView(msg: _error!, onRetry: _load)
              : Column(children: [
                  if (_items.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                      child: TextField(
                        controller: _searchCtrl,
                        style: const TextStyle(),
                        decoration: InputDecoration(
                          hintText: '搜索昵称或QQ',
                          hintStyle: const TextStyle(color: Color(0xFF6b7280)),
                          prefixIcon: const Icon(Icons.search, color: Color(0xFF6b7280)),
                          filled: true,
                          fillColor: const Color(0xFF16213e),
                          border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: BorderSide.none),
                          contentPadding: const EdgeInsets.symmetric(vertical: 10),
                        ),
                      ),
                    ),
                  Expanded(
                    child: _items.isEmpty
                        ? _empty()
                        : _filtered.isEmpty
                            ? const Center(child: Text('未找到', style: TextStyle(color: Color(0xFF6b7280))))
                            : RefreshIndicator(
                                onRefresh: _load,
                                color: const Color(0xFFf87171),
                                child: ListView.builder(
                                  padding: const EdgeInsets.all(16),
                                  itemCount: _filtered.length,
                                  itemBuilder: (ctx, i) => _BlackCard(
                                    item: _filtered[i] as Map<String, dynamic>,
                                    onDelete: () => _delete(_filtered[i]['id'] as int),
                                  ),
                                ),
                              ),
                  ),
                ]),
      floatingActionButton: _items.isNotEmpty
          ? FloatingActionButton(
              backgroundColor: const Color(0xFFf87171),
              onPressed: _showAddDialog,
              child: const Icon(Icons.add),
            )
          : null,
    );
  }

  Widget _empty() => Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
    const Icon(Icons.block_outlined, size: 56, color: Color(0xFF374151)),
    const SizedBox(height: 12),
    const Text('黑名单为空', style: TextStyle(color: Color(0xFF6b7280), fontSize: 16)),
    const SizedBox(height: 4),
    const Text('记录在恋综中遇到的问题人物', style: TextStyle(color: Color(0xFF4b5563), fontSize: 13)),
    const SizedBox(height: 16),
    ElevatedButton.icon(
      style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFFf87171), foregroundColor: Colors.white),
      onPressed: _showAddDialog,
      icon: const Icon(Icons.add, size: 18),
      label: const Text('添加'),
    ),
  ]));
}

class _BlackCard extends StatelessWidget {
  final Map<String, dynamic> item;
  final VoidCallback onDelete;
  const _BlackCard({required this.item, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final nickname   = item['nickname']    as String? ?? '';
    final qq         = item['qq']          as String? ?? '';
    final reason     = item['reason']      as String? ?? '';
    final notes      = item['notes']       as String? ?? '';
    final happenedAt = item['happened_at'] as String? ?? '';
    final ts         = item['created_at']  as int?    ?? 0;
    final dateStr    = ts > 0
        ? DateTime.fromMillisecondsSinceEpoch(ts * 1000).toLocal().toString().substring(0, 10)
        : '';

    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: const Color(0xFFf87171).withAlpha(60)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Container(
              width: 36, height: 36,
              decoration: BoxDecoration(
                color: const Color(0xFFf87171).withAlpha(25),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.block, color: Color(0xFFf87171), size: 18),
            ),
            const SizedBox(width: 10),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(nickname, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
              if (qq.isNotEmpty)
                Text('QQ: $qq', style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
            ])),
            IconButton(
              icon: const Icon(Icons.delete_outline, color: Color(0xFF6b7280), size: 20),
              onPressed: onDelete,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
          ]),
          const SizedBox(height: 10),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFFf87171).withAlpha(15),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFf87171).withAlpha(40)),
            ),
            child: Text(reason, style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 13, height: 1.5)),
          ),
          if (happenedAt.isNotEmpty || notes.isNotEmpty || dateStr.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(spacing: 12, children: [
              if (happenedAt.isNotEmpty)
                _MetaChip('事发：$happenedAt'),
              if (dateStr.isNotEmpty)
                _MetaChip('录入：$dateStr'),
            ]),
          ],
          if (notes.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(notes, style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
          ],
        ]),
      ),
    );
  }
}

class _MetaChip extends StatelessWidget {
  final String text;
  const _MetaChip(this.text);
  @override
  Widget build(BuildContext context) =>
      Text(text, style: const TextStyle(color: Color(0xFF6b7280), fontSize: 11));
}

InputDecoration _inputDeco(String hint) => InputDecoration(
  hintText: hint,
  hintStyle: const TextStyle(color: Color(0xFF4b5563)),
  filled: true,
  fillColor: const Color(0xFF1a1a2e),
  border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
  focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: Color(0xFFf87171))),
  contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
);

class _ErrorView extends StatelessWidget {
  final String msg; final VoidCallback onRetry;
  const _ErrorView({required this.msg, required this.onRetry});
  @override
  Widget build(BuildContext context) => Center(child: Column(
    mainAxisAlignment: MainAxisAlignment.center,
    children: [
      Text(msg, style: const TextStyle(color: Color(0xFF9ca3af))),
      const SizedBox(height: 16),
      ElevatedButton(onPressed: onRetry,
          style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFFf87171)),
          child: const Text('重试')),
    ],
  ));
}
