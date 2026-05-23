import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/auth_service.dart';
import '../services/api_service.dart';

const _colors = [
  '#8b7cf6', '#f472b6', '#34d399', '#60a5fa', '#fbbf24',
  '#f87171', '#a78bfa', '#2dd4bf', '#fb923c', '#e879f9',
  '#4ade80', '#38bdf8', '#facc15', '#c084fc', '#fb7185', '#a3e635',
];

const _tags = ['带本', '下组', '打工'];
const _tagColors = {
  '带本': Color(0xFFfb923c),
  '下组': Color(0xFF60a5fa),
  '打工': Color(0xFFa78bfa),
};
const _castingStatuses = ['观望中', '一表中', '已录取'];
const _castingStatusColors = {
  '观望中': Color(0xFF9ca3af),
  '一表中': Color(0xFF60a5fa),
  '已录取': Color(0xFF8b7cf6),
};

const _deadlines = [
  ('deadline_form2',    '二表截止',    Color(0xFFfbbf24)),
  ('deadline_public',   '公知截止',    Color(0xFF38bdf8)),
  ('deadline_relation', '关系线截止',  Color(0xFF4ade80)),
];

const _genderSuggestions   = ['男', '女', '无性别', '非人类', '双性'];
const _outcomeSuggestions  = ['HE', 'BE', 'TE', '开放结局', '未定'];
const _orientSuggestions   = ['直向', '百合', 'BL', '双向', '无性向'];

class ScheduleFormScreen extends StatefulWidget {
  final Map<String, dynamic>? existing;
  const ScheduleFormScreen({super.key, this.existing});

  @override
  State<ScheduleFormScreen> createState() => _ScheduleFormScreenState();
}

class _ScheduleFormScreenState extends State<ScheduleFormScreen> {
  // 必填
  final _showNameCtrl  = TextEditingController();
  DateTime? _startDate;
  DateTime? _endDate;

  // 颜色
  String _color = _colors[0];

  // 角色信息
  final _roleNameCtrl = TextEditingController();
  final _roleTypeCtrl = TextEditingController();
  final _genderCtrl   = TextEditingController();
  final _charCtrl     = TextEditingController();

  // 档期信息
  final _outcomeCtrl  = TextEditingController();
  final _orientCtrl   = TextEditingController();
  final _themeCtrl    = TextEditingController();

  // 投设状态（空字符串 = 未定）
  String _castingStatus = '';

  // 档期标签（空字符串 = 无）
  String _tag = '';

  // 截止日期
  final Map<String, DateTime?> _deadlineDates = {
    'deadline_form2':    null,
    'deadline_public':   null,
    'deadline_relation': null,
  };

  // 备注
  final _notesCtrl = TextEditingController();

  // 可见范围
  String _visibility = 'public';

  bool   _saving = false;
  String? _error;

  bool get _isEdit => widget.existing != null;

  @override
  void initState() {
    super.initState();
    final e = widget.existing;
    if (e != null) {
      _showNameCtrl.text = e['show_name'] as String? ?? '';
      _notesCtrl.text    = e['notes']     as String? ?? '';
      _charCtrl.text     = _known(e['character']);
      _roleNameCtrl.text = _known(e['role_name']);
      _roleTypeCtrl.text = _known(e['role_type']);
      _genderCtrl.text   = _known(e['gender']);
      _outcomeCtrl.text  = _known(e['outcome']);
      _orientCtrl.text   = _known(e['orientation']);
      _themeCtrl.text    = _known(e['theme']);
      _castingStatus     = e['casting_status'] as String? ?? '';
      _visibility        = e['visibility']     as String? ?? 'public';

      final rawColor = e['color'] as String? ?? '';
      _color = rawColor.isNotEmpty ? rawColor : _colors[0];

      // 解析 time_range
      final tr = e['time_range'] as String? ?? '';
      final sy = e['start_year'] as int? ?? DateTime.now().year;
      if (tr.length == 9) {
        final sm = int.tryParse(tr.substring(0, 2)) ?? 1;
        final sd = int.tryParse(tr.substring(2, 4)) ?? 1;
        final em = int.tryParse(tr.substring(5, 7)) ?? 1;
        final ed = int.tryParse(tr.substring(7, 9)) ?? 1;
        _startDate = DateTime(sy, sm, sd);
        final ey   = em < sm ? sy + 1 : sy;
        _endDate   = DateTime(ey, em, ed);
      }

      // 标签
      final tags = e['schedule_tags'] as String? ?? '[]';
      if (tags.contains('带本'))      _tag = '带本';
      else if (tags.contains('下组')) _tag = '下组';
      else if (tags.contains('打工')) _tag = '打工';

      // 截止日期
      for (final deadline in _deadlines) {
        final col = deadline.$1;
        final v = e[col];
        if (v is String && v.isNotEmpty) {
          final parts = v.split('-');
          if (parts.length == 3) {
            _deadlineDates[col] = DateTime(
              int.tryParse(parts[0]) ?? 2025,
              int.tryParse(parts[1]) ?? 1,
              int.tryParse(parts[2]) ?? 1,
            );
          }
        }
      }
    }
  }

  String _known(dynamic v) {
    final s = v as String? ?? '';
    return (s == '未知') ? '' : s;
  }

  @override
  void dispose() {
    _showNameCtrl.dispose(); _notesCtrl.dispose();
    _charCtrl.dispose();     _roleNameCtrl.dispose();
    _roleTypeCtrl.dispose(); _genderCtrl.dispose();
    _outcomeCtrl.dispose();  _orientCtrl.dispose();
    _themeCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickDate(bool isStart) async {
    final now  = DateTime.now();
    final init = isStart
        ? (_startDate ?? now)
        : (_endDate ?? (_startDate?.add(const Duration(days: 30)) ?? now));
    final picked = await showDatePicker(
      context: context,
      initialDate: init,
      firstDate: DateTime(2020),
      lastDate:  DateTime(2030),
      builder: (ctx, child) => Theme(
        data: Theme.of(ctx).copyWith(
          colorScheme: const ColorScheme.dark(
            primary: Color(0xFF8b7cf6),
            surface: Color(0xFF16213e),
          ),
        ),
        child: child!,
      ),
    );
    if (picked != null) {
      setState(() {
        if (isStart) {
          _startDate = picked;
          if (_endDate != null && _endDate!.isBefore(picked)) _endDate = null;
        } else {
          _endDate = picked;
        }
      });
    }
  }

  Future<void> _pickDeadline(String col) async {
    final now  = DateTime.now();
    final init = _deadlineDates[col] ?? now;
    final picked = await showDatePicker(
      context: context,
      initialDate: init,
      firstDate: DateTime(2020),
      lastDate:  DateTime(2030),
      builder: (ctx, child) => Theme(
        data: Theme.of(ctx).copyWith(
          colorScheme: const ColorScheme.dark(
            primary: Color(0xFF8b7cf6),
            surface: Color(0xFF16213e),
          ),
        ),
        child: child!,
      ),
    );
    if (picked != null) setState(() => _deadlineDates[col] = picked);
  }

  String _fmt(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2,'0')}-${d.day.toString().padLeft(2,'0')}';

  Future<void> _save() async {
    if (_showNameCtrl.text.trim().isEmpty) {
      setState(() => _error = '恋综名不能为空'); return;
    }
    if (_startDate == null || _endDate == null) {
      setState(() => _error = '请选择开始和结束日期'); return;
    }
    if (!_endDate!.isAfter(_startDate!)) {
      setState(() => _error = '结束日期必须晚于开始日期'); return;
    }

    setState(() { _saving = true; _error = null; });

    final data = <String, dynamic>{
      'show_name':      _showNameCtrl.text.trim(),
      'start_date':     _fmt(_startDate!),
      'end_date':       _fmt(_endDate!),
      'color':          _color,
      'role_name':      _roleNameCtrl.text.trim(),
      'role_type':      _roleTypeCtrl.text.trim(),
      'gender':         _genderCtrl.text.trim(),
      'character':      _charCtrl.text.trim(),
      'outcome':        _outcomeCtrl.text.trim(),
      'orientation':    _orientCtrl.text.trim(),
      'theme':          _themeCtrl.text.trim(),
      'casting_status': _castingStatus,
      'stag':           _tag,
      'notes':          _notesCtrl.text.trim(),
      'visibility':     _visibility,
      for (final d in _deadlines)
        d.$1: _deadlineDates[d.$1] != null ? _fmt(_deadlineDates[d.$1]!) : '',
    };

    try {
      final auth = context.read<AuthService>();
      final api  = ApiService(auth);
      if (_isEdit) {
        await api.editSchedule(widget.existing!['id'] as int, data);
      } else {
        await api.addSchedule(data);
      }
      if (!mounted) return;
      Navigator.pop(context, true);
    } catch (e) {
      if (!mounted) return;
      setState(() { _error = '保存失败，请重试'; _saving = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_isEdit ? '编辑档期' : '新增档期',
            style: const TextStyle()),
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          TextButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(width: 18, height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF8b7cf6)))
                : const Text('保存',
                    style: TextStyle(color: Color(0xFF8b7cf6), fontWeight: FontWeight.bold)),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_error != null)
              Container(
                width: double.infinity,
                margin: const EdgeInsets.only(bottom: 12),
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: const Color(0xFF7f1d1d),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(_error!, style: const TextStyle(color: Color(0xFFfca5a5))),
              ),

            // ── 必填信息 ────────────────────────────────────────
            _section('必填信息'),
            _label('恋综名 *'),
            _field(_showNameCtrl, '如：长日将尽第三季'),
            const SizedBox(height: 14),
            _label('档期时间 *'),
            Row(children: [
              Expanded(child: _dateTile(
                label: _startDate == null ? '开始日期' : '${_startDate!.month}/${_startDate!.day}',
                isSet: _startDate != null,
                onTap: () => _pickDate(true),
              )),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 8),
                child: Text('→', style: TextStyle(color: Color(0xFF6b7280))),
              ),
              Expanded(child: _dateTile(
                label: _endDate == null ? '结束日期' : '${_endDate!.month}/${_endDate!.day}',
                isSet: _endDate != null,
                onTap: () => _pickDate(false),
              )),
            ]),
            const SizedBox(height: 4),
            const Text('跨年档期直接选跨年日期即可',
                style: TextStyle(color: Color(0xFF4b5563), fontSize: 11)),

            // ── 档期颜色 ────────────────────────────────────────
            _section('档期颜色'),
            _label('在日历上显示的颜色'),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _colors.map((c) {
                final selected = c == _color;
                return GestureDetector(
                  onTap: () => setState(() => _color = c),
                  child: Container(
                    width: 32, height: 32,
                    decoration: BoxDecoration(
                      color: _hexColor(c),
                      shape: BoxShape.circle,
                      border: selected ? Border.all(color: Colors.white, width: 3) : null,
                    ),
                    child: selected ? const Icon(Icons.check, color: Colors.white, size: 16) : null,
                  ),
                );
              }).toList(),
            ),

            // ── 角色信息 ────────────────────────────────────────
            _section('角色信息'),
            Row(children: [
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                _label('角色名'),
                _field(_roleNameCtrl, '角色名称'),
              ])),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                _label('角色类型'),
                _field(_roleTypeCtrl, '自由填写'),
              ])),
            ]),
            const SizedBox(height: 12),
            Row(children: [
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                _label('性别'),
                _suggField(_genderCtrl, '如：男 / 女', _genderSuggestions),
              ])),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                _label('扮演的明星'),
                _field(_charCtrl, '扮演的明星艺人'),
              ])),
            ]),

            // ── 档期信息 ────────────────────────────────────────
            _section('档期信息'),
            Row(children: [
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                _label('结局'),
                _suggField(_outcomeCtrl, 'HE / BE / TE', _outcomeSuggestions),
              ])),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                _label('性向'),
                _suggField(_orientCtrl, '直向 / 百合 / BL', _orientSuggestions),
              ])),
            ]),
            const SizedBox(height: 12),
            _label('主题'),
            _field(_themeCtrl, '如：古风 / 现代 / 架空'),

            // ── 投设状态 ────────────────────────────────────────
            _section('投设状态'),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _castingChip('', '未定', const Color(0xFF6b7280)),
                ..._castingStatuses.map((s) =>
                    _castingChip(s, s, _castingStatusColors[s]!)),
              ],
            ),
            const SizedBox(height: 4),
            const Text('影响档期在日历上的显示样式',
                style: TextStyle(color: Color(0xFF4b5563), fontSize: 11)),

            // ── 档期标签 ────────────────────────────────────────
            _section('档期标签'),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _tagChip('', '无', const Color(0xFF9ca3af)),
                ..._tags.map((t) => _tagChip(t, t, _tagColors[t]!)),
              ],
            ),

            // ── 截止时间 ────────────────────────────────────────
            _section('截止时间'),
            ..._deadlines.map((row) {
              final (col, label, color) = row;
              final dt = _deadlineDates[col];
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(children: [
                  Expanded(child: Text(label,
                      style: TextStyle(color: color, fontSize: 13))),
                  GestureDetector(
                    onTap: () => _pickDeadline(col),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.surfaceContainer,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: dt != null ? color.withOpacity(0.5) : const Color(0xFF374151),
                        ),
                      ),
                      child: Row(mainAxisSize: MainAxisSize.min, children: [
                        Icon(Icons.calendar_today, size: 13,
                            color: dt != null ? color : const Color(0xFF6b7280)),
                        const SizedBox(width: 6),
                        Text(
                          dt != null ? '${dt.month}/${dt.day}' : '不设',
                          style: TextStyle(
                            color: dt != null ? Colors.white : const Color(0xFF4b5563),
                            fontSize: 13,
                          ),
                        ),
                        if (dt != null) ...[
                          const SizedBox(width: 6),
                          GestureDetector(
                            onTap: () => setState(() => _deadlineDates[col] = null),
                            child: const Icon(Icons.close, size: 14, color: Color(0xFF6b7280)),
                          ),
                        ],
                      ]),
                    ),
                  ),
                ]),
              );
            }),
            const Text('截止日期会在日历对应日期上显示提醒标记',
                style: TextStyle(color: Color(0xFF4b5563), fontSize: 11)),

            // ── 备注 ──────────────────────────────────────────
            _section('备注'),
            _field(_notesCtrl, '可以填写任何补充说明……', maxLines: 3),

            // ── 可见范围 ──────────────────────────────────────
            _section('可见范围'),
            Row(children: [
              Expanded(child: _visChip('public',  '🌐 所有人可见')),
              const SizedBox(width: 10),
              Expanded(child: _visChip('private', '🔒 仅自己可见')),
            ]),
            const SizedBox(height: 4),
            const Text('设为「仅自己可见」的档期不出现在公会视图和年度统计共享中',
                style: TextStyle(color: Color(0xFF4b5563), fontSize: 11)),

            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }

  // ── Helpers ─────────────────────────────────────────────────────────────────

  Widget _section(String title) => Padding(
        padding: const EdgeInsets.only(top: 24, bottom: 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title.toUpperCase(),
                style: const TextStyle(
                    color: Color(0xFF6b7280),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.8)),
            const SizedBox(height: 6),
            const Divider(color: Color(0xFF374151), height: 1),
          ],
        ),
      );

  Widget _label(String text) => Padding(
        padding: const EdgeInsets.only(bottom: 6),
        child: Text(text,
            style: const TextStyle(color: Color(0xFF9ca3af), fontSize: 13, fontWeight: FontWeight.w500)),
      );

  Widget _field(TextEditingController ctrl, String hint, {int maxLines = 1}) =>
      TextField(
        controller: ctrl,
        maxLines: maxLines,
        style: const TextStyle(),
        decoration: InputDecoration(
          hintText: hint,
          hintStyle: const TextStyle(color: Color(0xFF4b5563)),
          filled: true,
          fillColor: const Color(0xFF16213e),
          border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: BorderSide.none),
          focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide: const BorderSide(color: Color(0xFF8b7cf6))),
          contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        ),
      );

  Widget _suggField(TextEditingController ctrl, String hint, List<String> suggestions) =>
      Autocomplete<String>(
        optionsBuilder: (val) => val.text.isEmpty
            ? const Iterable.empty()
            : suggestions.where((s) => s.contains(val.text)),
        onSelected: (s) => ctrl.text = s,
        fieldViewBuilder: (ctx, techCtrl, focusNode, onSubmit) {
          techCtrl.text = ctrl.text;
          techCtrl.addListener(() => ctrl.text = techCtrl.text);
          return TextField(
            controller: techCtrl,
            focusNode: focusNode,
            onEditingComplete: onSubmit,
            style: const TextStyle(),
            decoration: InputDecoration(
              hintText: hint,
              hintStyle: const TextStyle(color: Color(0xFF4b5563)),
              filled: true,
              fillColor: const Color(0xFF16213e),
              border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: BorderSide.none),
              focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(10),
                  borderSide: const BorderSide(color: Color(0xFF8b7cf6))),
              contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            ),
          );
        },
        optionsViewBuilder: (ctx, onSel, opts) => Align(
          alignment: Alignment.topLeft,
          child: Material(
            color: const Color(0xFF16213e),
            borderRadius: BorderRadius.circular(8),
            elevation: 4,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 180),
              child: ListView(
                padding: EdgeInsets.zero,
                shrinkWrap: true,
                children: opts.map((s) => ListTile(
                  dense: true,
                  title: Text(s, style: const TextStyle(fontSize: 13)),
                  onTap: () => onSel(s),
                )).toList(),
              ),
            ),
          ),
        ),
      );

  Widget _dateTile({required String label, required bool isSet, required VoidCallback onTap}) =>
      GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainer,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isSet ? const Color(0xFF8b7cf6).withOpacity(0.5) : Colors.transparent,
            ),
          ),
          child: Row(children: [
            Icon(Icons.calendar_today, size: 14,
                color: isSet ? const Color(0xFF8b7cf6) : const Color(0xFF6b7280)),
            const SizedBox(width: 6),
            Text(label,
                style: TextStyle(
                    color: isSet ? Colors.white : const Color(0xFF4b5563),
                    fontSize: 14)),
          ]),
        ),
      );

  Widget _tagChip(String value, String label, Color color) {
    final selected = _tag == value;
    return GestureDetector(
      onTap: () => setState(() => _tag = value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(
          color: selected ? color.withOpacity(0.2) : const Color(0xFF16213e),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: selected ? color : const Color(0xFF374151)),
        ),
        child: Text(label,
            style: TextStyle(
                color: selected ? color : const Color(0xFF9ca3af),
                fontSize: 13,
                fontWeight: selected ? FontWeight.w600 : FontWeight.normal)),
      ),
    );
  }

  Widget _castingChip(String value, String label, Color color) {
    final selected = _castingStatus == value;
    return GestureDetector(
      onTap: () => setState(() => _castingStatus = value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(
          color: selected ? color.withOpacity(0.2) : const Color(0xFF16213e),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: selected ? color : const Color(0xFF374151),
          ),
        ),
        child: Text(label,
            style: TextStyle(
                color: selected ? color : const Color(0xFF9ca3af),
                fontSize: 13,
                fontWeight: selected ? FontWeight.w600 : FontWeight.normal)),
      ),
    );
  }

  Widget _visChip(String value, String label) {
    final selected = _visibility == value;
    return GestureDetector(
      onTap: () => setState(() => _visibility = value),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: selected ? const Color(0xFF8b7cf6).withOpacity(0.15) : const Color(0xFF16213e),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(
            color: selected ? const Color(0xFF8b7cf6) : const Color(0xFF374151),
          ),
        ),
        child: Text(label,
            textAlign: TextAlign.center,
            style: TextStyle(
                color: selected ? const Color(0xFF8b7cf6) : const Color(0xFF9ca3af),
                fontSize: 13,
                fontWeight: selected ? FontWeight.w600 : FontWeight.normal)),
      ),
    );
  }

  Color _hexColor(String hex) {
    try {
      return Color(int.parse(hex.replaceFirst('#', '0xFF')));
    } catch (_) {
      return const Color(0xFF8b7cf6);
    }
  }
}
