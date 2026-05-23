import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../services/auth_service.dart';
import '../../services/api_service.dart';

const _moods = ['😊', '😢', '😍', '😤', '😴', '🤔', '🥳', '😰'];

class DiaryScreen extends StatefulWidget {
  const DiaryScreen({super.key});
  @override
  State<DiaryScreen> createState() => _DiaryScreenState();
}

class _DiaryScreenState extends State<DiaryScreen> {
  bool _loading = true;
  String? _error;
  List<dynamic> _entries = [];

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final auth = context.read<AuthService>();
      final data = await ApiService(auth).getDiary();
      if (!mounted) return;
      setState(() { _entries = data; _loading = false; });
    } catch (_) {
      if (!mounted) return;
      setState(() { _error = '加载失败，请重试'; _loading = false; });
    }
  }

  void _showAddDialog() {
    final contentCtrl = TextEditingController();
    final titleCtrl   = TextEditingController();
    String selectedMood = '';

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF16213e),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
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
                const Text('写日记', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.close, color: Color(0xFF9ca3af)),
                  onPressed: () => Navigator.pop(ctx),
                ),
              ]),
              const SizedBox(height: 12),
              TextField(
                controller: titleCtrl,
                style: const TextStyle(),
                decoration: _inputDeco('标题（可选）'),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: contentCtrl,
                style: const TextStyle(),
                maxLines: 5,
                autofocus: true,
                decoration: _inputDeco('写下今天的语擦心情……'),
              ),
              const SizedBox(height: 12),
              const Text('心情', style: TextStyle(color: Color(0xFF9ca3af), fontSize: 12)),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                children: _moods.map((m) => GestureDetector(
                  onTap: () => setS(() => selectedMood = selectedMood == m ? '' : m),
                  child: Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: selectedMood == m
                          ? const Color(0xFF60a5fa).withAlpha(40)
                          : const Color(0xFF1a1a2e),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: selectedMood == m
                            ? const Color(0xFF60a5fa)
                            : const Color(0xFF374151),
                      ),
                    ),
                    child: Text(m, style: const TextStyle(fontSize: 20)),
                  ),
                )).toList(),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF60a5fa),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  onPressed: () async {
                    if (contentCtrl.text.trim().isEmpty) return;
                    try {
                      final auth = context.read<AuthService>();
                      await ApiService(auth).addDiaryEntry({
                        'title':   titleCtrl.text.trim(),
                        'content': contentCtrl.text.trim(),
                        'mood':    selectedMood,
                      });
                      if (!ctx.mounted) return;
                      Navigator.pop(ctx);
                      _load();
                    } catch (_) {}
                  },
                  child: const Text('保存'),
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
        title: const Text('删除日记', style: TextStyle()),
        content: const Text('确定删除这篇日记吗？', style: TextStyle(color: Color(0xFF9ca3af))),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消', style: TextStyle(color: Color(0xFF9ca3af)))),
          TextButton(onPressed: () => Navigator.pop(ctx, true),
              child: const Text('删除', style: TextStyle(color: Color(0xFFf87171)))),
        ],
      ),
    );
    if (ok != true) return;
    final auth = context.read<AuthService>();
    await ApiService(auth).deleteDiaryEntry(id);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('日记', style: TextStyle()),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            icon: const Icon(Icons.add, color: Color(0xFF60a5fa)),
            onPressed: _showAddDialog,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF60a5fa)))
          : _error != null
              ? _ErrorView(msg: _error!, onRetry: _load)
              : _entries.isEmpty
                  ? _empty()
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: const Color(0xFF60a5fa),
                      child: ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: _entries.length,
                        itemBuilder: (ctx, i) => _DiaryCard(
                          entry: _entries[i] as Map<String, dynamic>,
                          onDelete: () => _delete(_entries[i]['id'] as int),
                        ),
                      ),
                    ),
      floatingActionButton: _entries.isNotEmpty
          ? FloatingActionButton(
              backgroundColor: const Color(0xFF60a5fa),
              onPressed: _showAddDialog,
              child: const Icon(Icons.add),
            )
          : null,
    );
  }

  Widget _empty() => Center(
    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
      const Icon(Icons.book_outlined, size: 56, color: Color(0xFF374151)),
      const SizedBox(height: 12),
      const Text('还没有日记', style: TextStyle(color: Color(0xFF6b7280), fontSize: 16)),
      const SizedBox(height: 8),
      ElevatedButton.icon(
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF60a5fa),
          foregroundColor: Colors.white,
        ),
        onPressed: _showAddDialog,
        icon: const Icon(Icons.add, size: 18),
        label: const Text('写第一篇'),
      ),
    ]),
  );
}

class _DiaryCard extends StatelessWidget {
  final Map<String, dynamic> entry;
  final VoidCallback onDelete;
  const _DiaryCard({required this.entry, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final ts      = entry['created_at'] as int? ?? 0;
    final date    = ts > 0
        ? DateTime.fromMillisecondsSinceEpoch(ts * 1000).toLocal()
        : DateTime.now();
    final dateStr = '${date.year}/${date.month}/${date.day}';
    final title   = entry['title'] as String? ?? '';
    final content = entry['content'] as String? ?? '';
    final mood    = entry['mood'] as String? ?? '';

    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: Color(0xFF374151)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text(dateStr, style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
            if (mood.isNotEmpty) ...[
              const SizedBox(width: 8),
              Text(mood, style: const TextStyle(fontSize: 16)),
            ],
            const Spacer(),
            IconButton(
              icon: const Icon(Icons.delete_outline, color: Color(0xFF6b7280), size: 18),
              onPressed: onDelete,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
          ]),
          if (title.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(title, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
          ],
          const SizedBox(height: 8),
          Text(content, style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 13, height: 1.6)),
        ]),
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
      borderSide: const BorderSide(color: Color(0xFF60a5fa))),
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
          style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF60a5fa)),
          child: const Text('重试')),
    ],
  ));
}
