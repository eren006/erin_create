import 'dart:convert';
import 'package:flutter/widgets.dart';
import 'package:home_widget/home_widget.dart';

class WidgetService {
  static const _appGroupId = 'com.yuca.yuca_app';
  static const _providerName = 'com.yuca.yuca_app.YucaWidgetProvider';

  static Future<void> init() async {
    await HomeWidget.setAppGroupId(_appGroupId);
  }

  /// 把当前月档期数据推送到桌面小组件
  /// schedules: getCalendar 返回的 month_schedules 列表
  static Future<void> updateWidget(List<dynamic> schedules, int year, int month) async {
    try {
      final monthStr = '$year年$month月';

      // 转成小组件需要的格式
      final items = schedules.map((s) {
        final tr  = s['time_range'] as String? ?? '';
        final sy  = s['start_year'] as int? ?? year;
        String dateStr = '';
        if (tr.length == 9) {
          final sm = tr.substring(0, 2).replaceFirst(RegExp('^0'), '');
          final sd = tr.substring(2, 4).replaceFirst(RegExp('^0'), '');
          final em = tr.substring(5, 7).replaceFirst(RegExp('^0'), '');
          final ed = tr.substring(7, 9).replaceFirst(RegExp('^0'), '');
          final eyear = int.parse(tr.substring(5, 7)) < int.parse(tr.substring(0, 2))
              ? sy + 1 : sy;
          dateStr = eyear != sy ? '$sm/$sd-$eyear/$em/$ed' : '$sm/$sd-$em/$ed';
        }
        return {
          'name':  s['show_name'] as String? ?? '',
          'date':  dateStr,
          'color': s['color']     as String? ?? '#8b7cf6',
        };
      }).toList();

      await HomeWidget.saveWidgetData('yuca_month', monthStr);
      await HomeWidget.saveWidgetData('yuca_schedules', jsonEncode(items));
      await HomeWidget.updateWidget(
        androidName: _providerName,
      );
    } catch (e) {
      debugPrint('[WidgetService] 更新失败: $e');
    }
  }
}
