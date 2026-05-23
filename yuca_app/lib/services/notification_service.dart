import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/timezone.dart' as tz;
import 'package:timezone/data/latest.dart' as tz_data;

class NotificationService {
  static final _plugin = FlutterLocalNotificationsPlugin();
  static bool _initialized = false;

  // 通知渠道
  static const _channelId = 'yuca_schedule_reminder';
  static const _channelName = '档期提醒';
  static const _channelDesc = '档期结束前一天提醒';

  static Future<void> init() async {
    if (_initialized) return;
    tz_data.initializeTimeZones();
    // 尝试设为中国时区
    try {
      tz.setLocalLocation(tz.getLocation('Asia/Shanghai'));
    } catch (_) {}

    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const settings = InitializationSettings(android: android);
    await _plugin.initialize(settings);

    // 请求 Android 13+ 通知权限
    final androidImpl = _plugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();
    await androidImpl?.requestNotificationsPermission();
    await androidImpl?.requestExactAlarmsPermission();

    _initialized = true;
  }

  /// 根据档期列表，重新安排所有"提前一天"提醒
  /// schedules 格式：[{'id': int, 'show_name': str, 'end_date': 'YYYY-MM-DD', ...}]
  static Future<void> scheduleReminders(List<dynamic> schedules) async {
    if (!_initialized) await init();
    await _plugin.cancelAll(); // 先清空旧的

    final now = tz.TZDateTime.now(tz.local);
    int notifId = 1000; // 从 1000 开始，避免和其他通知冲突

    for (final s in schedules) {
      final endDateStr = s['end_date'] as String?;
      if (endDateStr == null || endDateStr.isEmpty) continue;

      DateTime endDate;
      try {
        endDate = DateTime.parse(endDateStr);
      } catch (_) {
        continue;
      }

      // 提醒时间：结束日的前一天上午 9:00
      final reminderDay = endDate.subtract(const Duration(days: 1));
      final scheduledTime = tz.TZDateTime(
        tz.local,
        reminderDay.year,
        reminderDay.month,
        reminderDay.day,
        9, 0, 0,
      );

      // 只安排未来的提醒
      if (scheduledTime.isBefore(now)) continue;

      final showName = s['show_name'] as String? ?? '档期';
      final myChar  = s['my_char']   as String? ?? '';
      final body = myChar.isNotEmpty
          ? '明天：「$showName」（$myChar）到期'
          : '明天：「$showName」到期';

      await _plugin.zonedSchedule(
        notifId++,
        '⏰ 档期提醒',
        body,
        scheduledTime,
        NotificationDetails(
          android: AndroidNotificationDetails(
            _channelId,
            _channelName,
            channelDescription: _channelDesc,
            importance: Importance.high,
            priority: Priority.high,
            styleInformation: BigTextStyleInformation(body),
          ),
        ),
        androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
      );
    }

    debugPrint('[NotificationService] 安排了 ${notifId - 1000} 条提醒');
  }

  /// 根据卡包列表，在到期前 10/5/3/1 天各发一次提醒
  /// cards 格式：[{'id': int, 'name': str, 'expiry': 'YYYY-MM-DD', 'card_type': str, 'quantity': int, ...}]
  static Future<void> scheduleCardReminders(List<dynamic> cards) async {
    if (!_initialized) await init();

    // 取消已有的卡包提醒（id 范围 2000–2999）
    for (int i = 2000; i < 3000; i++) {
      await _plugin.cancel(i);
    }

    final now = tz.TZDateTime.now(tz.local);
    int notifId = 2000;
    const milestones = [10, 5, 3, 1]; // 提前 N 天提醒

    for (final c in cards) {
      final expiryStr = c['expiry'] as String?;
      if (expiryStr == null || expiryStr.isEmpty) continue;

      DateTime expiry;
      try {
        expiry = DateTime.parse(expiryStr);
      } catch (_) {
        continue;
      }

      final name  = c['name']      as String? ?? '卡片';
      final ctype = c['card_type'] as String? ?? '';
      final qty   = c['quantity']  as int?    ?? 0;

      for (final days in milestones) {
        final reminderDay  = expiry.subtract(Duration(days: days));
        final scheduledTime = tz.TZDateTime(
          tz.local,
          reminderDay.year, reminderDay.month, reminderDay.day, 9, 0, 0,
        );
        if (scheduledTime.isBefore(now)) continue;
        if (notifId >= 3000) break;

        final typeTag = ctype.isNotEmpty ? '[$ctype] ' : '';
        final body    = '「$typeTag$name」还有 $days 天到期，库存 $qty 张，记得及时使用！';

        await _plugin.zonedSchedule(
          notifId++,
          '🃏 卡包到期提醒',
          body,
          scheduledTime,
          NotificationDetails(
            android: AndroidNotificationDetails(
              _channelId,
              _channelName,
              channelDescription: _channelDesc,
              importance: Importance.high,
              priority: Priority.high,
              styleInformation: BigTextStyleInformation(body),
            ),
          ),
          androidScheduleMode: AndroidScheduleMode.exactAllowWhileIdle,
          uiLocalNotificationDateInterpretation:
              UILocalNotificationDateInterpretation.absoluteTime,
        );
      }
    }

    debugPrint('[NotificationService] 卡包提醒安排了 ${notifId - 2000} 条');
  }

  /// 立即发一条测试通知
  static Future<void> sendTestNotification() async {
    if (!_initialized) await init();
    await _plugin.show(
      0,
      '⏰ 档期提醒测试',
      '提醒功能正常工作！',
      const NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId, _channelName,
          channelDescription: _channelDesc,
          importance: Importance.high,
          priority: Priority.high,
        ),
      ),
    );
  }
}
