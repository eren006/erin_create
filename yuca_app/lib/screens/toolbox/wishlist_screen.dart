import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../services/auth_service.dart';
import '../../services/api_service.dart';

const _wtypes = ['题材', '剧本', '搭档', '服装', '恋综', '其他'];

class WishlistScreen extends StatefulWidget {
  const WishlistScreen({super.key});
  @override
  State<WishlistScreen> createState() => _WishlistScreenState();
}

class _WishlistScreenState extends State<WishlistScreen> {
  bool _loading = true;
  String? _error;
  List<dynamic> _items = [];

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final auth = context.read<AuthService>();
      final data = await ApiService(auth).getWishlist();
      if (!mounted) return;
      setState(() { _items = data; _loading = false; });
    } catch (_) {
      if (!mounted) return;
      setState(() { _error = '加载失败，请重试'; _loading = false; });
    }
  }

  void _showAddDialog() {
    final contentCtrl = TextEditingController();
    final notesCtrl   = TextEditingController();
    String wtype = '题材';

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF16213e),
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setS) => Padding(
          padding: EdgeInsets.only(
            left: 20, right: 20, top: 20,
            bottom: MediaQuery.of(ctx).viewInsets.bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                const Text('添加心愿', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const Spacer(),
                IconButton(icon: const Icon(Icons.close, color: Color(0xFF9ca3af)),
                    onPressed: () => Navigator.pop(ctx)),
              ]),
              const SizedBox(height: 12),
              const Text('类型', style: TextStyle(color: Color(0xFF9ca3af), fontSize: 12)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8, runSpacing: 8,
                children: _wtypes.map((t) => GestureDetector(
                  onTap: () => setS(() => wtype = t),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: wtype == t
                          ? const Color(0xFFfbbf24).withAlpha(40)
                          : const Color(0xFF1a1a2e),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: wtype == t ? const Color(0xFFfbbf24) : const Color(0xFF374151),
                      ),
                    ),
                    child: Text(t, style: TextStyle(
                      color: wtype == t ? const Color(0xFFfbbf24) : const Color(0xFF9ca3af),
                      fontSize: 13,
                    )),
                  ),
                )).toList(),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: contentCtrl,
                style: const TextStyle(),
                autofocus: true,
                decoration: _inputDeco('心愿内容 *'),
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
                    backgroundColor: const Color(0xFFfbbf24),
                    foregroundColor: Colors.black,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  onPressed: () async {
                    if (contentCtrl.text.trim().isEmpty) return;
                    try {
                      final auth = context.read<AuthService>();
                      await ApiService(auth).addWishlistItem({
                        'wtype':   wtype,
                        'content': contentCtrl.text.trim(),
                        'notes':   notesCtrl.text.trim(),
                      });
                      if (!ctx.mounted) return;
                      Navigator.pop(ctx);
                      _load();
                    } catch (_) {}
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

  Future<void> _toggle(int id) async {
    final auth = context.read<AuthService>();
    await ApiService(auth).toggleWishlistItem(id);
    _load();
  }

  Future<void> _delete(int id) async {
    final auth = context.read<AuthService>();
    await ApiService(auth).deleteWishlistItem(id);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final pending  = _items.where((i) => (i['is_done'] as int? ?? 0) == 0).toList();
    final done     = _items.where((i) => (i['is_done'] as int? ?? 0) == 1).toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('心愿单', style: TextStyle()),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            icon: const Icon(Icons.add, color: Color(0xFFfbbf24)),
            onPressed: _showAddDialog,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFFfbbf24)))
          : _error != null
              ? _ErrorView(msg: _error!, onRetry: _load)
              : _items.isEmpty
                  ? _empty()
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: const Color(0xFFfbbf24),
                      child: ListView(
                        padding: const EdgeInsets.all(16),
                        children: [
                          if (pending.isNotEmpty) ...[
                            _sectionLabel('未完成 ${pending.length}'),
                            ...pending.map((item) => _WishCard(
                              item: item as Map<String, dynamic>,
                              onToggle: () => _toggle(item['id'] as int),
                              onDelete: () => _delete(item['id'] as int),
                            )),
                          ],
                          if (done.isNotEmpty) ...[
                            _sectionLabel('已实现 ${done.length}'),
                            ...done.map((item) => _WishCard(
                              item: item as Map<String, dynamic>,
                              onToggle: () => _toggle(item['id'] as int),
                              onDelete: () => _delete(item['id'] as int),
                            )),
                          ],
                        ],
                      ),
                    ),
      floatingActionButton: _items.isNotEmpty
          ? FloatingActionButton(
              backgroundColor: const Color(0xFFfbbf24),
              foregroundColor: Colors.black,
              onPressed: _showAddDialog,
              child: const Icon(Icons.add),
            )
          : null,
    );
  }

  Widget _sectionLabel(String text) => Padding(
    padding: const EdgeInsets.only(top: 8, bottom: 8),
    child: Text(text, style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12, fontWeight: FontWeight.w600)),
  );

  Widget _empty() => Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
    const Icon(Icons.star_outline, size: 56, color: Color(0xFF374151)),
    const SizedBox(height: 12),
    const Text('还没有心愿', style: TextStyle(color: Color(0xFF6b7280), fontSize: 16)),
    const SizedBox(height: 8),
    ElevatedButton.icon(
      style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFFfbbf24), foregroundColor: Colors.black),
      onPressed: _showAddDialog,
      icon: const Icon(Icons.add, size: 18),
      label: const Text('添加心愿'),
    ),
  ]));
}

class _WishCard extends StatelessWidget {
  final Map<String, dynamic> item;
  final VoidCallback onToggle;
  final VoidCallback onDelete;
  const _WishCard({required this.item, required this.onToggle, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final isDone   = (item['is_done'] as int? ?? 0) == 1;
    final content  = item['content'] as String? ?? '';
    final notes    = item['notes']   as String? ?? '';
    final wtype    = item['wtype']   as String? ?? '';

    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: isDone
              ? const Color(0xFF374151)
              : const Color(0xFFfbbf24).withAlpha(80),
        ),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onToggle,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(children: [
            Icon(
              isDone ? Icons.check_circle : Icons.radio_button_unchecked,
              color: isDone ? const Color(0xFF34d399) : const Color(0xFFfbbf24),
              size: 22,
            ),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                if (wtype.isNotEmpty)
                  Container(
                    margin: const EdgeInsets.only(right: 8),
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                    decoration: BoxDecoration(
                      color: const Color(0xFFfbbf24).withAlpha(30),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(wtype, style: const TextStyle(color: Color(0xFFfbbf24), fontSize: 10)),
                  ),
                Expanded(
                  child: Text(content,
                    style: TextStyle(
                      color: isDone ? const Color(0xFF6b7280) : Colors.white,
                      fontSize: 14,
                      decoration: isDone ? TextDecoration.lineThrough : null,
                      decorationColor: const Color(0xFF6b7280),
                    ),
                  ),
                ),
              ]),
              if (notes.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(notes, style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
              ],
            ])),
            IconButton(
              icon: const Icon(Icons.delete_outline, color: Color(0xFF6b7280), size: 18),
              onPressed: onDelete,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
          ]),
        ),
      ),
    );
  }
}

InputDecoration _inputDeco(String hint) => InputDecoration(
  hintText: hint,
  hintStyle: const TextStyle(color: Color(0xFF4b5563)),
  filled: true,
  fillColor: const Color(0xFF1a1a2e),
  border: OutlineInputBorder(borderRadius: BorderRadius.circular(10), borderSide: BorderSide.none),
  focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(10),
      borderSide: const BorderSide(color: Color(0xFFfbbf24))),
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
          style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFFfbbf24)),
          child: const Text('重试', style: TextStyle(color: Colors.black))),
    ],
  ));
}
