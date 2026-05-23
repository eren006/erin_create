import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:dio/dio.dart';
import '../../services/auth_service.dart';
import '../../services/api_service.dart';
import '../../services/notification_service.dart';
import '../../utils/theme_utils.dart';

const _kCardTypes = ['板写', '溶图', '溶写', '其他'];

const _kTypeColors = {
  '板写': Color(0xFF60a5fa),
  '溶图': Color(0xFF34d399),
  '溶写': Color(0xFFfbbf24),
  '其他': Color(0xFFa78bfa),
};

class CardScreen extends StatefulWidget {
  const CardScreen({super.key});

  @override
  State<CardScreen> createState() => _CardScreenState();
}

class _CardScreenState extends State<CardScreen> {
  List<dynamic> _cards = [];
  bool _loading = true;
  String? _error;
  String _typeFilter = '';

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
      final data = await ApiService(auth).getCards(type: _typeFilter);
      if (!mounted) return;
      final cards = data['cards'] as List<dynamic>? ?? [];
      setState(() {
        _cards   = cards;
        _loading = false;
      });
      NotificationService.scheduleCardReminders(cards);
    } catch (e) {
      if (!mounted) return;
      String msg = '加载失败，请检查网络';
      if (e is DioException && e.response != null) {
        msg = e.response!.data?['error'] ?? '服务器错误 ${e.response!.statusCode}';
      }
      setState(() { _error = msg; _loading = false; });
    }
  }

  Future<void> _openForm({Map<String, dynamic>? existing}) async {
    final result = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).colorScheme.surfaceContainer,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => _CardForm(existing: existing),
    );
    if (result == true) _load();
  }

  Future<void> _rollRandom() async {
    try {
      final auth = context.read<AuthService>();
      final data = await ApiService(auth).randomCard(type: _typeFilter);
      if (!mounted) return;
      if (data['ok'] == true) {
        final card = data['card'] as Map<String, dynamic>;
        _showRandomResult(card);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(data['error'] ?? '没有可用的卡片')));
      }
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('获取失败')));
    }
  }

  void _showRandomResult(Map<String, dynamic> card) {
    final accent = themeToColor(context.read<AuthService>().user?.theme);
    final cs = Theme.of(context).colorScheme;
    final name     = card['name']      as String? ?? '';
    final ctype    = card['card_type'] as String? ?? '';
    final qty      = card['quantity']  as int?    ?? 0;
    final daysLeft = card['days_left'] as int?    ?? 0;
    final color    = _kTypeColors[ctype] ?? const Color(0xFFa78bfa);

    const lines = ['命运之手为你选中了它！', '今天就用它吧，别再纠结了~',
                   '它在卡包里等你很久了。', '就决定是你了！', '缘分天注定，出手吧！'];
    final flavor = lines[(DateTime.now().millisecond) % lines.length];

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(children: [
          const Text('🎲 急救箱', style: TextStyle(fontSize: 16)),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
                color: color.withAlpha(40),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: color.withAlpha(100))),
            child: Text(ctype, style: TextStyle(color: color, fontSize: 11)),
          ),
        ]),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(flavor, style: TextStyle(color: cs.onSurface.withAlpha(150), fontSize: 12)),
          const SizedBox(height: 12),
          Text(name, style: TextStyle(color: accent, fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Row(children: [
            _InfoChip(Icons.inventory_2_outlined,
                '库存 $qty 张', cs.onSurface.withAlpha(180)),
            const SizedBox(width: 8),
            _InfoChip(Icons.timer_outlined,
                daysLeft >= 0 ? '还剩 $daysLeft 天' : '已过期',
                daysLeft <= 3 ? const Color(0xFFf87171) : cs.onSurface.withAlpha(180)),
          ]),
        ]),
        actions: [
          TextButton(
            onPressed: () { Navigator.pop(ctx); _rollRandom(); },
            child: const Text('再来一张'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('好的'),
          ),
        ],
      ),
    );
  }

  Future<void> _cleanExpired() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('清理过期卡片'),
        content: const Text('将删除所有已过期的卡片，确认吗？'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(ctx, true),
              child: const Text('清理', style: TextStyle(color: Color(0xFFf87171)))),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      final auth = context.read<AuthService>();
      final data = await ApiService(auth).cleanCards();
      if (!mounted) return;
      final n = data['cleaned'] as int? ?? 0;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(n > 0 ? '已清理 $n 张过期卡片' : '没有过期卡片，卡包干净~')));
      if (n > 0) _load();
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    final accent = themeToColor(context.watch<AuthService>().user?.theme);
    final cs     = Theme.of(context).colorScheme;

    // 统计紧急卡（3天内）
    final urgentCount = _cards.where((c) {
      final d = c['days_left'] as int?;
      return d != null && d >= 0 && d <= 3;
    }).length;

    return Scaffold(
      appBar: AppBar(
        title: Row(children: [
          const Text('卡救星'),
          if (urgentCount > 0) ...[
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
              decoration: BoxDecoration(
                  color: const Color(0xFFf87171),
                  borderRadius: BorderRadius.circular(10)),
              child: Text('$urgentCount 张急！',
                  style: const TextStyle(color: Colors.white, fontSize: 11,
                      fontWeight: FontWeight.bold)),
            ),
          ],
        ]),
        actions: [
          IconButton(
            icon: Icon(Icons.casino_outlined, color: accent),
            tooltip: '急救箱（随机）',
            onPressed: _cards.isEmpty ? null : _rollRandom,
          ),
          IconButton(
            icon: Icon(Icons.cleaning_services_outlined,
                color: cs.onSurface.withAlpha(150)),
            tooltip: '清理过期',
            onPressed: _cleanExpired,
          ),
          IconButton(
            icon: Icon(Icons.add, color: accent),
            onPressed: () => _openForm(),
          ),
        ],
      ),
      body: Column(children: [
        // ── 类型筛选栏 ──────────────────────────────────────────
        SizedBox(
          height: 44,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            children: [
              _TypeChip(label: '全部', active: _typeFilter.isEmpty,
                  accent: accent, onTap: () { setState(() => _typeFilter = ''); _load(); }),
              ..._kCardTypes.map((t) => _TypeChip(
                  label: t,
                  active: _typeFilter == t,
                  accent: _kTypeColors[t] ?? accent,
                  onTap: () { setState(() => _typeFilter = t); _load(); })),
            ],
          ),
        ),
        // ── 列表 ───────────────────────────────────────────────
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? Center(child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(_error!, style: TextStyle(color: cs.onSurface.withAlpha(150))),
                        const SizedBox(height: 16),
                        ElevatedButton(onPressed: _load, child: const Text('重试')),
                      ],
                    ))
                  : _cards.isEmpty
                      ? Center(
                          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                            const Text('🃏', style: TextStyle(fontSize: 40)),
                            const SizedBox(height: 12),
                            Text('卡包空空如也', style: TextStyle(color: cs.onSurface.withAlpha(150))),
                            const SizedBox(height: 8),
                            ElevatedButton.icon(
                              icon: const Icon(Icons.add),
                              label: const Text('录入卡片'),
                              onPressed: () => _openForm(),
                            ),
                          ]),
                        )
                      : RefreshIndicator(
                          onRefresh: _load,
                          child: ListView.builder(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                            itemCount: _cards.length,
                            itemBuilder: (ctx, i) => _CardItem(
                              card: _cards[i],
                              onEdit: () => _openForm(
                                  existing: Map<String, dynamic>.from(_cards[i])),
                              onDelete: () => _deleteCard(_cards[i]['id'] as int),
                              onConsume: () => _consumeCard(_cards[i]),
                            ),
                          ),
                        ),
        ),
      ]),
    );
  }

  Future<void> _deleteCard(int cid) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('删除卡片'),
        content: const Text('确认删除这张卡片吗？'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          TextButton(onPressed: () => Navigator.pop(ctx, true),
              child: const Text('删除', style: TextStyle(color: Color(0xFFf87171)))),
        ],
      ),
    );
    if (ok == true && mounted) {
      await ApiService(context.read<AuthService>()).deleteCard(cid);
      _load();
    }
  }

  Future<void> _consumeCard(Map<String, dynamic> card) async {
    final name = card['name'] as String? ?? '';
    int count  = 1;
    final ctrl = TextEditingController(text: '1');
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('使用「$name」'),
        content: TextField(
          controller: ctrl,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: '消耗数量', suffixText: '张'),
          onChanged: (v) => count = int.tryParse(v) ?? 1,
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('取消')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('确认使用')),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      final data = await ApiService(context.read<AuthService>())
          .consumeCard(card['id'] as int, count: count);
      if (!mounted) return;
      final newQty = data['card']?['quantity'] as int? ?? 0;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已使用 $count 张，剩余 $newQty 张')));
      _load();
    }
  }
}

// ── 卡片列表项 ─────────────────────────────────────────────────────────────────

class _CardItem extends StatelessWidget {
  final Map<String, dynamic> card;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final VoidCallback onConsume;

  const _CardItem({
    required this.card,
    required this.onEdit,
    required this.onDelete,
    required this.onConsume,
  });

  @override
  Widget build(BuildContext context) {
    final cs      = Theme.of(context).colorScheme;
    final name    = card['name']      as String? ?? '';
    final ctype   = card['card_type'] as String? ?? '其他';
    final qty     = card['quantity']  as int?    ?? 0;
    final price   = card['price']     as double? ?? 0.0;
    final expiry  = card['expiry']    as String? ?? '';
    final notes   = card['notes']     as String? ?? '';
    final daysLeft = card['days_left'] as int?   ?? 0;
    final color   = _kTypeColors[ctype] ?? const Color(0xFFa78bfa);

    final isExpired = daysLeft < 0;
    final isUrgent  = !isExpired && daysLeft <= 3;
    final statusColor = isExpired
        ? const Color(0xFF6b7280)
        : isUrgent
            ? const Color(0xFFf87171)
            : daysLeft <= 10
                ? const Color(0xFFfbbf24)
                : color;

    return Card(
      color: cs.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: isUrgent
              ? const Color(0xFFf87171).withAlpha(120)
              : color.withAlpha(80),
        ),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onLongPress: () => _showActions(context),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(children: [
            // 左侧彩色条
            Container(
              width: 4, height: 60,
              decoration: BoxDecoration(
                  color: color, borderRadius: BorderRadius.circular(2)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(
                    child: Text(name, style: const TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w600)),
                  ),
                  // 类型标签
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                    decoration: BoxDecoration(
                        color: color.withAlpha(30),
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: color.withAlpha(80))),
                    child: Text(ctype, style: TextStyle(color: color, fontSize: 10)),
                  ),
                  if (isUrgent)
                    const Padding(
                      padding: EdgeInsets.only(left: 4),
                      child: Icon(Icons.warning_amber_rounded,
                          color: Color(0xFFf87171), size: 16),
                    ),
                ]),
                const SizedBox(height: 4),
                Row(children: [
                  _InfoChip(Icons.timer_outlined,
                      isExpired ? '已过期 ($expiry)' : '还剩 $daysLeft 天 ($expiry)',
                      statusColor),
                  const SizedBox(width: 10),
                  _InfoChip(Icons.inventory_2_outlined,
                      '$qty 张', cs.onSurface.withAlpha(160)),
                  if (price > 0) ...[
                    const SizedBox(width: 10),
                    _InfoChip(Icons.attach_money,
                        '¥${price.toStringAsFixed(price % 1 == 0 ? 0 : 1)}',
                        cs.onSurface.withAlpha(120)),
                  ],
                ]),
                if (notes.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 3),
                    child: Text(notes,
                        style: TextStyle(
                            color: cs.onSurface.withAlpha(120), fontSize: 12),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis),
                  ),
              ]),
            ),
            // 使用按钮
            IconButton(
              icon: Icon(Icons.play_circle_outline, color: color, size: 26),
              onPressed: onConsume,
              tooltip: '使用',
            ),
          ]),
        ),
      ),
    );
  }

  void _showActions(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surfaceContainer,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      builder: (_) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          ListTile(
            leading: const Icon(Icons.play_circle_outline, color: Color(0xFF34d399)),
            title: const Text('使用卡片'),
            onTap: () { Navigator.pop(context); onConsume(); },
          ),
          ListTile(
            leading: const Icon(Icons.edit_outlined, color: Color(0xFF8b7cf6)),
            title: const Text('编辑'),
            onTap: () { Navigator.pop(context); onEdit(); },
          ),
          ListTile(
            leading: const Icon(Icons.delete_outline, color: Color(0xFFf87171)),
            title: const Text('删除', style: TextStyle(color: Color(0xFFf87171))),
            onTap: () { Navigator.pop(context); onDelete(); },
          ),
        ]),
      ),
    );
  }
}

// ── 卡片表单（添加/编辑） ───────────────────────────────────────────────────────

class _CardForm extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const _CardForm({this.existing});

  @override
  State<_CardForm> createState() => _CardFormState();
}

class _CardFormState extends State<_CardForm> {
  final _nameCtrl   = TextEditingController();
  final _expiryCtrl = TextEditingController();
  final _qtyCtrl    = TextEditingController(text: '1');
  final _priceCtrl  = TextEditingController(text: '0');
  final _notesCtrl  = TextEditingController();
  String _cardType  = '其他';
  bool _saving      = false;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _nameCtrl.text   = e['name']      as String? ?? '';
      _expiryCtrl.text = e['expiry']    as String? ?? '';
      _qtyCtrl.text    = '${e['quantity'] ?? 1}';
      _priceCtrl.text  = '${e['price'] ?? 0}';
      _notesCtrl.text  = e['notes']     as String? ?? '';
      _cardType        = e['card_type'] as String? ?? '其他';
    }
  }

  @override
  void dispose() {
    _nameCtrl.dispose(); _expiryCtrl.dispose();
    _qtyCtrl.dispose();  _priceCtrl.dispose(); _notesCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickDate() async {
    final now    = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _expiryCtrl.text.isNotEmpty
          ? DateTime.tryParse(_expiryCtrl.text) ?? now
          : now,
      firstDate: now,
      lastDate: DateTime(2030),
    );
    if (picked != null) {
      _expiryCtrl.text =
          '${picked.year}-${picked.month.toString().padLeft(2, '0')}-${picked.day.toString().padLeft(2, '0')}';
    }
  }

  Future<void> _save() async {
    final name   = _nameCtrl.text.trim();
    final expiry = _expiryCtrl.text.trim();
    if (name.isEmpty || expiry.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('名称和到期日不能为空')));
      return;
    }
    setState(() => _saving = true);
    try {
      final auth = context.read<AuthService>();
      final data = {
        'name':      name,
        'expiry':    expiry,
        'quantity':  int.tryParse(_qtyCtrl.text) ?? 1,
        'price':     double.tryParse(_priceCtrl.text) ?? 0,
        'card_type': _cardType,
        'notes':     _notesCtrl.text.trim(),
      };
      final isEdit = widget.existing != null;
      if (isEdit) {
        await ApiService(auth).editCard(widget.existing!['id'] as int, data);
      } else {
        await ApiService(auth).addCard(data);
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      if (!mounted) return;
      String msg = '保存失败';
      if (e is DioException && e.response != null) {
        msg = e.response!.data?['error'] ?? '服务器错误';
      }
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isEdit = widget.existing != null;
    final accent = themeToColor(context.watch<AuthService>().user?.theme);
    return Padding(
      padding: EdgeInsets.fromLTRB(
          20, 20, 20, MediaQuery.of(context).viewInsets.bottom + 20),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(isEdit ? '编辑卡片' : '录入卡片',
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const Spacer(),
          IconButton(
              icon: const Icon(Icons.close),
              onPressed: () => Navigator.pop(context)),
        ]),
        const SizedBox(height: 12),
        TextField(
          controller: _nameCtrl,
          decoration: const InputDecoration(labelText: '卡片名称 *'),
        ),
        const SizedBox(height: 10),
        // 类型选择
        Wrap(
          spacing: 8,
          children: _kCardTypes.map((t) {
            final active = _cardType == t;
            final color  = _kTypeColors[t] ?? accent;
            return GestureDetector(
              onTap: () => setState(() => _cardType = t),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                decoration: BoxDecoration(
                    color: active ? color.withAlpha(40) : Theme.of(context).colorScheme.surface,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                        color: active ? color : Theme.of(context).colorScheme.onSurface.withAlpha(50))),
                child: Text(t, style: TextStyle(
                    color: active ? color : Theme.of(context).colorScheme.onSurface.withAlpha(160),
                    fontSize: 13)),
              ),
            );
          }).toList(),
        ),
        const SizedBox(height: 10),
        // 到期日
        TextField(
          controller: _expiryCtrl,
          readOnly: true,
          onTap: _pickDate,
          decoration: InputDecoration(
            labelText: '到期日 *',
            suffixIcon: Icon(Icons.calendar_today, color: accent, size: 18),
          ),
        ),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _qtyCtrl,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: '数量（张）'),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextField(
              controller: _priceCtrl,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(labelText: '价格（¥）'),
            ),
          ),
        ]),
        const SizedBox(height: 10),
        TextField(
          controller: _notesCtrl,
          decoration: const InputDecoration(labelText: '备注'),
          maxLines: 2,
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(height: 18, width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : Text(isEdit ? '保存修改' : '录入'),
          ),
        ),
      ]),
    );
  }
}

// ── 小工具组件 ─────────────────────────────────────────────────────────────────

class _InfoChip extends StatelessWidget {
  final IconData icon;
  final String text;
  final Color color;
  const _InfoChip(this.icon, this.text, this.color);

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
    Icon(icon, size: 12, color: color),
    const SizedBox(width: 3),
    Text(text, style: TextStyle(color: color, fontSize: 11)),
  ]);
}

class _TypeChip extends StatelessWidget {
  final String label;
  final bool active;
  final Color accent;
  final VoidCallback onTap;
  const _TypeChip({required this.label, required this.active,
      required this.accent, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(right: 8),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
        decoration: BoxDecoration(
          color: active ? accent.withAlpha(40) : cs.surfaceContainer,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
              color: active ? accent : cs.onSurface.withAlpha(50)),
        ),
        child: Text(label, style: TextStyle(
            color: active ? accent : cs.onSurface.withAlpha(180),
            fontSize: 13,
            fontWeight: active ? FontWeight.w600 : FontWeight.normal)),
      ),
    );
  }
}
