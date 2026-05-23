import 'package:device_calendar/device_calendar.dart';
import 'package:flutter/material.dart';
import 'package:timezone/timezone.dart' as tz;

class CalendarSyncService {
  static final _plugin = DeviceCalendarPlugin();
  static const _calendarName = '语擦助手档期';

  /// 请求日历权限，返回是否获得授权
  static Future<bool> requestPermission() async {
    var result = await _plugin.requestPermissions();
    if (result.isSuccess && result.data == true) return true;
    result = await _plugin.requestPermissions();
    return result.isSuccess && result.data == true;
  }

  /// 找到或创建"语擦助手档期"日历，返回 calendarId
  static Future<String?> _getOrCreateCalendar() async {
    final cals = await _plugin.retrieveCalendars();
    if (!cals.isSuccess) return null;

    // 找已有的
    final existing = cals.data?.firstWhere(
      (c) => c.name == _calendarName,
      orElse: () => Calendar(),
    );
    if (existing?.id != null && existing!.id!.isNotEmpty) return existing.id;

    // 创建新日历
    final created = await _plugin.createCalendar(
      _calendarName,
      calendarColor: const Color(0xFF8b7cf6),
      localAccountName: '语擦助手',
    );
    return created.isSuccess ? created.data : null;
  }

  /// 把档期列表同步到系统日历
  /// 返回：{ 'synced': N, 'error': '...' }
  static Future<Map<String, dynamic>> syncSchedules(
      List<dynamic> schedules) async {
    try {
      final hasPermission = await requestPermission();
      if (!hasPermission) {
        return {'synced': 0, 'error': '未获得日历权限'};
      }

      final calId = await _getOrCreateCalendar();
      if (calId == null) {
        return {'synced': 0, 'error': '无法创建日历'};
      }

      // 清除旧的同步事件（通过标题前缀识别）
      final now = tz.TZDateTime.now(tz.local);
      final existing = await _plugin.retrieveEvents(
        calId,
        RetrieveEventsParams(
          startDate: now.subtract(const Duration(days: 365)),
          endDate: now.add(const Duration(days: 730)),
        ),
      );
      if (existing.isSuccess && existing.data != null) {
        for (final evt in existing.data!) {
          await _plugin.deleteEvent(calId, evt.eventId!);
        }
      }

      int synced = 0;
      for (final s in schedules) {
        final dates = _parseDates(s);
        if (dates == null) continue;

        final showName = s['show_name'] as String? ?? '';
        final character = s['character'] as String? ?? '';
        final colorHex = s['color'] as String? ?? '#8b7cf6';

        final event = Event(
          calId,
          title: character.isNotEmpty && character != '未知'
              ? '$showName · $character'
              : showName,
          start: tz.TZDateTime.from(dates['start']!, tz.local),
          end: tz.TZDateTime.from(dates['end']!, tz.local),
          allDay: true,
          description: '由语擦助手同步',
        );

        final result = await _plugin.createOrUpdateEvent(event);
        if (result?.isSuccess == true) synced++;
      }

      return {'synced': synced, 'error': null};
    } catch (e) {
      return {'synced': 0, 'error': e.toString()};
    }
  }

  static Map<String, DateTime>? _parseDates(dynamic s) {
    try {
      final tr = s['time_range'] as String? ?? '';
      final sy = s['start_year'] as int? ?? DateTime.now().year;
      if (tr.length != 9) return null;

      final sm = int.parse(tr.substring(0, 2));
      final sd = int.parse(tr.substring(2, 4));
      final em = int.parse(tr.substring(5, 7));
      final ed = int.parse(tr.substring(7, 9));
      final ey = em < sm ? sy + 1 : sy;

      return {
        'start': DateTime(sy, sm, sd),
        'end':   DateTime(ey, em, ed),
      };
    } catch (_) {
      return null;
    }
  }

  static Color _hexToColor(String hex) {
    try {
      return Color(int.parse(hex.replaceFirst('#', '0xFF')));
    } catch (_) {
      return const Color(0xFF8b7cf6);
    }
  }
}
