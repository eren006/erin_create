import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../services/auth_service.dart';
import '../../services/api_service.dart';

class PartnersScreen extends StatefulWidget {
  const PartnersScreen({super.key});
  @override
  State<PartnersScreen> createState() => _PartnersScreenState();
}

class _PartnersScreenState extends State<PartnersScreen> {
  bool _loading = true;
  String? _error;
  List<dynamic> _partners = [];

  @override
  void initState() { super.initState(); _load(); }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final auth = context.read<AuthService>();
      final data = await ApiService(auth).getPartners();
      if (!mounted) return;
      setState(() { _partners = data; _loading = false; });
    } catch (_) {
      if (!mounted) return;
      setState(() { _error = '加载失败，请重试'; _loading = false; });
    }
  }

  void _showAddDialog() {
    final nicknameCtrl = TextEditingController();
    final qqCtrl       = TextEditingController();
    final notesCtrl    = TextEditingController();
    int rating = 0;

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
                const Text('添加必吃榜', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
                const Spacer(),
                IconButton(icon: const Icon(Icons.close, color: Color(0xFF9ca3af)),
                    onPressed: () => Navigator.pop(ctx)),
              ]),
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
              const SizedBox(height: 12),
              const Text('心动指数', style: TextStyle(color: Color(0xFF9ca3af), fontSize: 12)),
              const SizedBox(height: 8),
              Row(
                children: List.generate(5, (i) => GestureDetector(
                  onTap: () => setS(() => rating = i + 1 == rating ? 0 : i + 1),
                  child: Padding(
                    padding: const EdgeInsets.only(right: 4),
                    child: Icon(
                      Icons.favorite,
                      size: 28,
                      color: i < rating
                          ? const Color(0xFFf472b6)
                          : const Color(0xFF374151),
                    ),
                  ),
                )),
              ),
              const SizedBox(height: 12),
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
                    backgroundColor: const Color(0xFF34d399),
                    foregroundColor: Colors.black,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                  ),
                  onPressed: () async {
                    if (nicknameCtrl.text.trim().isEmpty) return;
                    try {
                      final auth = context.read<AuthService>();
                      await ApiService(auth).addPartner({
                        'nickname': nicknameCtrl.text.trim(),
                        'qq':       qqCtrl.text.trim(),
                        'rating':   rating,
                        'notes':    notesCtrl.text.trim(),
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

  Future<void> _delete(int id) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('移除搭档', style: TextStyle()),
        content: const Text('确定从必吃榜移除吗？', style: TextStyle(color: Color(0xFF9ca3af))),
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
    await ApiService(auth).deletePartner(id);
    _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('必吃榜', style: TextStyle()),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            icon: const Icon(Icons.add, color: Color(0xFF34d399)),
            onPressed: _showAddDialog,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: Color(0xFF34d399)))
          : _error != null
              ? _ErrorView(msg: _error!, onRetry: _load)
              : _partners.isEmpty
                  ? _empty()
                  : RefreshIndicator(
                      onRefresh: _load,
                      color: const Color(0xFF34d399),
                      child: ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: _partners.length,
                        itemBuilder: (ctx, i) => _PartnerCard(
                          partner: _partners[i] as Map<String, dynamic>,
                          onDelete: () => _delete(_partners[i]['id'] as int),
                        ),
                      ),
                    ),
      floatingActionButton: _partners.isNotEmpty
          ? FloatingActionButton(
              backgroundColor: const Color(0xFF34d399),
              foregroundColor: Colors.black,
              onPressed: _showAddDialog,
              child: const Icon(Icons.add),
            )
          : null,
    );
  }

  Widget _empty() => Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
    const Icon(Icons.people_outline, size: 56, color: Color(0xFF374151)),
    const SizedBox(height: 12),
    const Text('必吃榜空空如也', style: TextStyle(color: Color(0xFF6b7280), fontSize: 16)),
    const SizedBox(height: 4),
    const Text('记录你最想再次搭档的人', style: TextStyle(color: Color(0xFF4b5563), fontSize: 13)),
    const SizedBox(height: 16),
    ElevatedButton.icon(
      style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF34d399), foregroundColor: Colors.black),
      onPressed: _showAddDialog,
      icon: const Icon(Icons.add, size: 18),
      label: const Text('添加搭档'),
    ),
  ]));
}

class _PartnerCard extends StatelessWidget {
  final Map<String, dynamic> partner;
  final VoidCallback onDelete;
  const _PartnerCard({required this.partner, required this.onDelete});

  @override
  Widget build(BuildContext context) {
    final nickname = partner['nickname'] as String? ?? '';
    final qq       = partner['qq']       as String? ?? '';
    final notes    = partner['notes']    as String? ?? '';
    final rating   = partner['rating']   as int?    ?? 0;
    final tags     = partner['tags_list'] as List<dynamic>? ?? [];

    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: const Color(0xFF34d399).withAlpha(60)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(children: [
          // 头像
          Container(
            width: 44, height: 44,
            decoration: BoxDecoration(
              color: const Color(0xFF34d399).withAlpha(30),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: Text(
                nickname.isNotEmpty ? nickname[0].toUpperCase() : '?',
                style: const TextStyle(color: Color(0xFF34d399), fontSize: 18, fontWeight: FontWeight.bold),
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Text(nickname, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
              if (qq.isNotEmpty) ...[
                const SizedBox(width: 8),
                Text('QQ: $qq', style: const TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
              ],
            ]),
            if (rating > 0) ...[
              const SizedBox(height: 4),
              Row(
                children: List.generate(5, (i) => Icon(
                  Icons.favorite,
                  size: 14,
                  color: i < rating ? const Color(0xFFf472b6) : const Color(0xFF374151),
                )),
              ),
            ],
            if (notes.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(notes, style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 12)),
            ],
            if (tags.isNotEmpty) ...[
              const SizedBox(height: 6),
              Wrap(
                spacing: 6,
                children: tags.map((t) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0xFF34d399).withAlpha(25),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(t.toString(), style: const TextStyle(color: Color(0xFF34d399), fontSize: 11)),
                )).toList(),
              ),
            ],
          ])),
          IconButton(
            icon: const Icon(Icons.delete_outline, color: Color(0xFF6b7280), size: 20),
            onPressed: onDelete,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(),
          ),
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
      borderSide: const BorderSide(color: Color(0xFF34d399))),
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
          style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF34d399)),
          child: const Text('重试', style: TextStyle(color: Colors.black))),
    ],
  ));
}
