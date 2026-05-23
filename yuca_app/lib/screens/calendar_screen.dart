import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:table_calendar/table_calendar.dart';
import 'package:dio/dio.dart';
import '../services/auth_service.dart';
import '../services/api_service.dart';
import '../utils/theme_utils.dart';
import '../services/notification_service.dart';
import '../services/widget_service.dart';
import '../services/calendar_sync_service.dart';
import 'schedule_form_screen.dart';

class CalendarScreen extends StatefulWidget {
  const CalendarScreen({super.key});

  @override
  State<CalendarScreen> createState() => _CalendarScreenState();
}

class _CalendarScreenState extends State<CalendarScreen> {
  DateTime _focusedDay  = DateTime.now();
  DateTime? _selectedDay;
  bool _loading = true;
  String? _error;

  List<dynamic> _monthSchedules = [];
  Map<String, List<int>> _dayMarkers = {}; // "day" → [schedule_id, ...]
  List<int> _conflictIds = [];

  @override
  void initState() {
    super.initState();
    _selectedDay = _focusedDay;
    _load(_focusedDay.year, _focusedDay.month);
  }

  Future<void> _load(int year, int month) async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final auth = context.read<AuthService>();
      final data = await ApiService(auth).getCalendar(year, month);
      if (!mounted) return;
      final markers = (data['day_markers'] as Map<String, dynamic>? ?? {});
      final schedules = data['month_schedules'] as List<dynamic>? ?? [];
      setState(() {
        _monthSchedules = schedules;
        _dayMarkers     = markers.map((k, v) =>
            MapEntry(k, (v as List).map((e) => e as int).toList()));
        _conflictIds    = (data['conflict_ids'] as List<dynamic>? ?? [])
            .map((e) => e as int).toList();
        _loading = false;
      });
      // 每次加载档期后重新安排提醒 + 更新桌面小组件
      NotificationService.scheduleReminders(schedules);
      WidgetService.updateWidget(schedules, year, month);
    } catch (e) {
      if (!mounted) return;
      String msg = '加载失败，请检查网络';
      if (e is DioException && e.response != null) {
        msg = '服务器错误 ${e.response!.statusCode}';
      }
      setState(() { _error = msg; _loading = false; });
    }
  }

  // 当天的档期
  List<dynamic> _schedulesForDay(DateTime day) {
    final ids = _dayMarkers[day.day.toString()] ?? [];
    if (ids.isEmpty) return [];
    return _monthSchedules
        .where((s) => ids.contains(s['id'] as int))
        .toList();
  }

  Color _hexColor(String hex) {
    try {
      return Color(int.parse(hex.replaceFirst('#', '0xFF')));
    } catch (_) {
      return const Color(0xFF8b7cf6);
    }
  }

  Future<void> _openForm({Map<String, dynamic>? existing}) async {
    final result = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
          builder: (_) => ScheduleFormScreen(existing: existing)),
    );
    if (result == true) {
      _load(_focusedDay.year, _focusedDay.month);
    }
  }

  Future<void> _syncToSystemCalendar() async {
    if (_monthSchedules.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('本月暂无档期可同步')));
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('正在同步到系统日历...')));
    final result = await CalendarSyncService.syncSchedules(_monthSchedules);
    if (!mounted) return;
    final err = result['error'] as String?;
    final n   = result['synced'] as int? ?? 0;
    ScaffoldMessenger.of(context).clearSnackBars();
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(err != null ? '同步失败：$err' : '已同步 $n 个档期到系统日历 ✓'),
      duration: const Duration(seconds: 3),
    ));
  }

  Future<void> _deleteSchedule(int sid) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(

        title: const Text('删除档期', style: TextStyle()),
        content: const Text('确认删除这条档期吗？',
            style: TextStyle(color: Color(0xFF9ca3af))),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('取消',
                  style: TextStyle(color: Color(0xFF9ca3af)))),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('删除',
                  style: TextStyle(color: Color(0xFFf87171)))),
        ],
      ),
    );
    if (ok == true) {
      final auth = context.read<AuthService>();
      await ApiService(auth).deleteSchedule(sid);
      _load(_focusedDay.year, _focusedDay.month);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();
    final accent = themeToColor(auth.user?.theme);
    return Scaffold(
      appBar: AppBar(
        title: Text(
          '你好，${auth.user?.displayName ?? ''}',
          style: const TextStyle(fontSize: 18),
        ),
        actions: [
          IconButton(
            icon: Icon(Icons.calendar_month, color: accent.withAlpha(180)),
            tooltip: '同步到系统日历',
            onPressed: _syncToSystemCalendar,
          ),
          IconButton(
            icon: Icon(Icons.add, color: accent),
            onPressed: () => _openForm(),
          ),
        ],
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: Color(0xFF8b7cf6)))
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(_error!,
                          style: const TextStyle(color: Color(0xFF9ca3af))),
                      const SizedBox(height: 16),
                      ElevatedButton(
                        onPressed: () =>
                            _load(_focusedDay.year, _focusedDay.month),
                        style: ElevatedButton.styleFrom(
                            backgroundColor: accent),
                        child: const Text('重试'),
                      ),
                    ],
                  ),
                )
              : Column(
                  children: [
                    // ── 日历 ──────────────────────────────────────────────
                    TableCalendar(
                      firstDay: DateTime(2020),
                      lastDay:  DateTime(2030),
                      focusedDay:  _focusedDay,
                      selectedDayPredicate: (d) => isSameDay(_selectedDay, d),
                      onDaySelected: (selected, focused) => setState(() {
                        _selectedDay = selected;
                        _focusedDay  = focused;
                      }),
                      onPageChanged: (focused) {
                        _focusedDay = focused;
                        _load(focused.year, focused.month);
                      },
                      calendarStyle: CalendarStyle(
                        defaultTextStyle: TextStyle(
                            color: Theme.of(context).colorScheme.onSurface),
                        weekendTextStyle: TextStyle(color: accent.withAlpha(200)),
                        selectedDecoration: BoxDecoration(
                          color: accent,
                          shape: BoxShape.circle,
                        ),
                        todayDecoration: BoxDecoration(
                          color: accent.withAlpha(80),
                          shape: BoxShape.circle,
                        ),
                        markerDecoration: BoxDecoration(
                          color: accent,
                          shape: BoxShape.circle,
                        ),
                        outsideDaysVisible: false,
                      ),
                      headerStyle: HeaderStyle(
                        formatButtonVisible: false,
                        titleCentered: true,
                        titleTextStyle: TextStyle(
                            color: Theme.of(context).colorScheme.onSurface,
                            fontSize: 16),
                        leftChevronIcon: Icon(Icons.chevron_left,
                            color: Theme.of(context).colorScheme.onSurface),
                        rightChevronIcon: Icon(Icons.chevron_right,
                            color: Theme.of(context).colorScheme.onSurface),
                      ),
                      daysOfWeekStyle: DaysOfWeekStyle(
                        weekdayStyle: TextStyle(
                            color: Theme.of(context).colorScheme.onSurface.withAlpha(150),
                            fontSize: 12),
                        weekendStyle: TextStyle(
                            color: accent.withAlpha(180), fontSize: 12),
                      ),
                      // 彩色小点
                      calendarBuilders: CalendarBuilders(
                        markerBuilder: (ctx, day, _) {
                          final ids = _dayMarkers[day.day.toString()] ?? [];
                          if (ids.isEmpty) return const SizedBox.shrink();
                          final scheds = _monthSchedules
                              .where((s) => ids.contains(s['id'] as int))
                              .take(4)
                              .toList();
                          return Positioned(
                            bottom: 4,
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: scheds.map((s) {
                                final c = _hexColor(
                                    s['color'] as String? ?? '#8b7cf6');
                                return Container(
                                  width: 5,
                                  height: 5,
                                  margin: const EdgeInsets.symmetric(
                                      horizontal: 1),
                                  decoration: BoxDecoration(
                                    color: c,
                                    shape: BoxShape.circle,
                                  ),
                                );
                              }).toList(),
                            ),
                          );
                        },
                      ),
                    ),

                    const Divider(color: Color(0xFF374151), height: 1),

                    // ── 选中日当天的档期 / 本月所有档期 ─────────────────────
                    Expanded(
                      child: Builder(builder: (ctx) {
                        final dayScheds = _selectedDay != null
                            ? _schedulesForDay(_selectedDay!)
                            : <dynamic>[];
                        final list = dayScheds.isNotEmpty
                            ? dayScheds
                            : _monthSchedules;
                        final title = dayScheds.isNotEmpty
                            ? '${_selectedDay!.month}月${_selectedDay!.day}日的档期'
                            : '本月档期（${_monthSchedules.length}）';

                        return Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Padding(
                              padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
                              child: Text(title,
                                  style: const TextStyle(
                                      color: Color(0xFF9ca3af),
                                      fontSize: 12)),
                            ),
                            Expanded(
                              child: list.isEmpty
                                  ? const Center(
                                      child: Text('暂无档期',
                                          style: TextStyle(
                                              color: Color(0xFF6b7280))))
                                  : ListView.builder(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 12),
                                      itemCount: list.length,
                                      itemBuilder: (ctx, i) =>
                                          _ScheduleCard(
                                            schedule: list[i],
                                            hasConflict: _conflictIds.contains(
                                                list[i]['id'] as int),
                                            onEdit: () => _openForm(
                                                existing: Map<String,
                                                    dynamic>.from(list[i])),
                                            onDelete: () => _deleteSchedule(
                                                list[i]['id'] as int),
                                            hexColor: _hexColor,
                                          ),
                                    ),
                            ),
                          ],
                        );
                      }),
                    ),
                  ],
                ),
    );
  }
}

// ── 截止日期常量 ──────────────────────────────────────────────────────────────────
const _deadlineFields = [
  ('deadline_form2',    '二表截止',    Color(0xFFfbbf24)),
  ('deadline_public',   '公知截止',    Color(0xFF38bdf8)),
  ('deadline_relation', '关系线截止',  Color(0xFF4ade80)),
];

// ── 档期卡片 ──────────────────────────────────────────────────────────────────────

class _ScheduleCard extends StatelessWidget {
  final dynamic schedule;
  final bool hasConflict;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final Color Function(String) hexColor;

  const _ScheduleCard({
    required this.schedule,
    required this.hasConflict,
    required this.onEdit,
    required this.onDelete,
    required this.hexColor,
  });

  String _formatDateStr() {
    final tr = schedule['time_range'] as String? ?? '';
    final sy = schedule['start_year'] as int? ?? DateTime.now().year;
    if (tr.length != 9) return tr;
    final sm = tr.substring(0, 2).replaceFirst(RegExp('^0'), '');
    final sd = tr.substring(2, 4).replaceFirst(RegExp('^0'), '');
    final em = tr.substring(5, 7).replaceFirst(RegExp('^0'), '');
    final ed = tr.substring(7, 9).replaceFirst(RegExp('^0'), '');
    final ey = int.parse(tr.substring(5, 7)) < int.parse(tr.substring(0, 2))
        ? sy + 1 : sy;
    return ey != sy ? '$sy/$sm/$sd - $ey/$em/$ed' : '$sy/$sm/$sd - $em/$ed';
  }

  // 返回有值的截止日期列表
  List<(String label, Color color, String date, bool isUrgent)> _activeDdls() {
    final today = DateTime.now();
    final result = <(String, Color, String, bool)>[];
    for (final (col, label, color) in _deadlineFields) {
      final v = schedule[col] as String? ?? '';
      if (v.isEmpty) continue;
      final parts = v.split('-');
      if (parts.length != 3) continue;
      final dt = DateTime(
        int.tryParse(parts[0]) ?? today.year,
        int.tryParse(parts[1]) ?? 1,
        int.tryParse(parts[2]) ?? 1,
      );
      final diff = dt.difference(DateTime(today.year, today.month, today.day)).inDays;
      result.add((label, color, v, diff <= 3 && diff >= 0));
    }
    return result;
  }

  @override
  Widget build(BuildContext context) {
    final color   = hexColor(schedule['color'] as String? ?? '#8b7cf6');
    final char    = schedule['character'] as String? ?? '';
    final dateStr = _formatDateStr();
    final ddls    = _activeDdls();

    return Card(
      color: Theme.of(context).colorScheme.surfaceContainer,
      margin: const EdgeInsets.only(bottom: 8),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: hasConflict
              ? const Color(0xFFf87171).withOpacity(0.5)
              : color.withOpacity(0.3),
        ),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: () => _showDetail(context),
        onLongPress: () => _showActions(context),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 颜色条
              Container(
                width: 4,
                height: ddls.isEmpty ? 52 : 52 + 20.0 * ddls.length,
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            schedule['show_name'] as String? ?? '',
                            style: const TextStyle(
                                fontWeight: FontWeight.w600, fontSize: 15),
                          ),
                        ),
                        if (hasConflict)
                          const Icon(Icons.warning_amber_rounded,
                              color: Color(0xFFf87171), size: 16),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(dateStr,
                        style: const TextStyle(
                            color: Color(0xFF9ca3af), fontSize: 12)),
                    if (char.isNotEmpty && char != '未知')
                      Text('角色：$char',
                          style: const TextStyle(
                              color: Color(0xFF6b7280), fontSize: 12)),
                    // DDL 行
                    if (ddls.isNotEmpty) ...[
                      const SizedBox(height: 6),
                      ...ddls.map((d) => Padding(
                        padding: const EdgeInsets.only(bottom: 2),
                        child: Row(children: [
                          Icon(Icons.alarm,
                              size: 11,
                              color: d.$4
                                  ? const Color(0xFFf87171)
                                  : d.$2.withOpacity(0.85)),
                          const SizedBox(width: 3),
                          Text(
                            '${d.$1}：${d.$3}',
                            style: TextStyle(
                              fontSize: 11,
                              color: d.$4
                                  ? const Color(0xFFf87171)
                                  : d.$2.withOpacity(0.85),
                              fontWeight: d.$4
                                  ? FontWeight.w600
                                  : FontWeight.normal,
                            ),
                          ),
                          if (d.$4)
                            const Text(' ⚡',
                                style: TextStyle(
                                    fontSize: 11,
                                    color: Color(0xFFf87171))),
                        ]),
                      )),
                    ],
                  ],
                ),
              ),
              // 操作按钮
              IconButton(
                icon: const Icon(Icons.more_vert,
                    color: Color(0xFF6b7280), size: 20),
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                onPressed: () => _showActions(context),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showDetail(BuildContext context) {
    final color   = hexColor(schedule['color'] as String? ?? '#8b7cf6');
    final dateStr = _formatDateStr();
    final ddls    = _activeDdls();

    String? _val(String key) {
      final v = schedule[key] as String? ?? '';
      return (v.isEmpty || v == '未知') ? null : v;
    }

    showModalBottomSheet(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surfaceContainer,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => DraggableScrollableSheet(
        initialChildSize: 0.6,
        minChildSize: 0.4,
        maxChildSize: 0.92,
        expand: false,
        builder: (ctx, ctrl) => Column(
          children: [
            // 拖拽把手
            Container(
              margin: const EdgeInsets.only(top: 12, bottom: 8),
              width: 36, height: 4,
              decoration: BoxDecoration(
                color: const Color(0xFF6b7280).withOpacity(0.5),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            // 标题栏
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 4, 12, 12),
              child: Row(children: [
                Container(
                  width: 12, height: 12,
                  margin: const EdgeInsets.only(right: 10),
                  decoration: BoxDecoration(
                    color: color, shape: BoxShape.circle),
                ),
                Expanded(
                  child: Text(
                    schedule['show_name'] as String? ?? '',
                    style: const TextStyle(
                        fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.edit_outlined, size: 20),
                  color: color,
                  onPressed: () { Navigator.pop(ctx); onEdit(); },
                ),
              ]),
            ),
            const Divider(height: 1),
            Expanded(
              child: ListView(
                controller: ctrl,
                padding: const EdgeInsets.all(20),
                children: [
                  // 档期时间
                  _detailRow(Icons.date_range, '档期时间', dateStr,
                      const Color(0xFF9ca3af)),
                  // 投设状态
                  if (_val('casting_status') != null)
                    _detailRow(Icons.how_to_reg, '投设状态',
                        _val('casting_status')!, const Color(0xFF8b7cf6)),
                  // 标签
                  if (_val('schedule_tags') != null &&
                      (schedule['schedule_tags'] as String) != '[]')
                    _detailRow(Icons.label_outline, '标签',
                        (schedule['schedule_tags'] as String)
                            .replaceAll(RegExp(r'[\[\]"]'), '')
                            .replaceAll(',', ' · '),
                        const Color(0xFF60a5fa)),
                  // 角色信息
                  if (_val('character') != null)
                    _detailRow(Icons.person_outline, '扮演明星',
                        _val('character')!, const Color(0xFF9ca3af)),
                  if (_val('role_name') != null)
                    _detailRow(Icons.face, '角色名',
                        _val('role_name')!, const Color(0xFF9ca3af)),
                  if (_val('role_type') != null)
                    _detailRow(Icons.category_outlined, '角色类型',
                        _val('role_type')!, const Color(0xFF9ca3af)),
                  if (_val('gender') != null)
                    _detailRow(Icons.wc, '性别',
                        _val('gender')!, const Color(0xFF9ca3af)),
                  // 档期信息
                  if (_val('outcome') != null)
                    _detailRow(Icons.favorite_outline, '结局',
                        _val('outcome')!, const Color(0xFFf472b6)),
                  if (_val('orientation') != null)
                    _detailRow(Icons.people_outline, '性向',
                        _val('orientation')!, const Color(0xFFf472b6)),
                  if (_val('theme') != null)
                    _detailRow(Icons.auto_stories_outlined, '主题',
                        _val('theme')!, const Color(0xFF9ca3af)),
                  // 截止日期区块
                  if (ddls.isNotEmpty) ...[
                    const SizedBox(height: 16),
                    const Text('⏰ 截止日期',
                        style: TextStyle(
                            color: Color(0xFF6b7280),
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.8)),
                    const SizedBox(height: 8),
                    ...ddls.map((d) {
                      final today = DateTime.now();
                      final parts = d.$3.split('-');
                      final dt = parts.length == 3
                          ? DateTime(
                              int.tryParse(parts[0]) ?? today.year,
                              int.tryParse(parts[1]) ?? 1,
                              int.tryParse(parts[2]) ?? 1)
                          : null;
                      final diff = dt != null
                          ? dt.difference(DateTime(
                                  today.year, today.month, today.day))
                              .inDays
                          : null;
                      final diffStr = diff == null
                          ? ''
                          : diff < 0
                              ? '（已过期 ${-diff} 天）'
                              : diff == 0
                                  ? '（今天）'
                                  : '（还有 $diff 天）';
                      return Container(
                        margin: const EdgeInsets.only(bottom: 8),
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 10),
                        decoration: BoxDecoration(
                          color: d.$2.withOpacity(0.08),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                              color: d.$2.withOpacity(
                                  d.$4 ? 0.7 : 0.3)),
                        ),
                        child: Row(children: [
                          Icon(Icons.alarm, size: 14, color: d.$2),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              '${d.$1}：${d.$3}',
                              style: TextStyle(
                                  color: d.$2,
                                  fontSize: 13,
                                  fontWeight: FontWeight.w500),
                            ),
                          ),
                          Text(diffStr,
                              style: TextStyle(
                                  color: d.$4
                                      ? const Color(0xFFf87171)
                                      : const Color(0xFF6b7280),
                                  fontSize: 12,
                                  fontWeight: d.$4
                                      ? FontWeight.w600
                                      : FontWeight.normal)),
                        ]),
                      );
                    }),
                  ],
                  // 备注
                  if (_val('notes') != null) ...[
                    const SizedBox(height: 16),
                    const Text('备注',
                        style: TextStyle(
                            color: Color(0xFF6b7280),
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.8)),
                    const SizedBox(height: 8),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFF6b7280).withOpacity(0.08),
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Text(_val('notes')!,
                          style: const TextStyle(
                              color: Color(0xFF9ca3af),
                              fontSize: 13,
                              height: 1.6)),
                    ),
                  ],
                  const SizedBox(height: 20),
                  // 删除按钮
                  TextButton.icon(
                    style: TextButton.styleFrom(
                      foregroundColor: const Color(0xFFf87171),
                    ),
                    icon: const Icon(Icons.delete_outline, size: 16),
                    label: const Text('删除这条档期', style: TextStyle(fontSize: 13)),
                    onPressed: () { Navigator.pop(ctx); onDelete(); },
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _detailRow(IconData icon, String label, String value, Color iconColor) =>
      Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, size: 15, color: iconColor),
          const SizedBox(width: 8),
          SizedBox(
            width: 72,
            child: Text(label,
                style: const TextStyle(
                    color: Color(0xFF6b7280),
                    fontSize: 13)),
          ),
          Expanded(
            child: Text(value,
                style: const TextStyle(fontSize: 13)),
          ),
        ]),
      );

  void _showActions(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Theme.of(context).colorScheme.surfaceContainer,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
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
          ],
        ),
      ),
    );
  }
}
