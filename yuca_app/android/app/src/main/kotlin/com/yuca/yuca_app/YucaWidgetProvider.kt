package com.yuca.yuca_app

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.view.View
import android.widget.RemoteViews
import org.json.JSONArray

class YucaWidgetProvider : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        for (id in appWidgetIds) {
            updateWidget(context, appWidgetManager, id)
        }
    }

    companion object {
        fun updateWidget(context: Context, appWidgetManager: AppWidgetManager, widgetId: Int) {
            val prefs = context.getSharedPreferences("HomeWidgetPreferences", Context.MODE_PRIVATE)
            val views = RemoteViews(context.packageName, R.layout.yuca_widget_layout)

            // 点击小组件打开 App
            val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)
            if (launchIntent != null) {
                val pendingIntent = PendingIntent.getActivity(
                    context, 0, launchIntent,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
                )
                views.setOnClickPendingIntent(R.id.tv_title, pendingIntent)
            }

            // 月份
            val month = prefs.getString("yuca_month", "") ?: ""
            views.setTextViewText(R.id.tv_month, month)

            // 档期列表
            val schedulesJson = prefs.getString("yuca_schedules", "[]") ?: "[]"
            val rowIds    = listOf(R.id.row_0, R.id.row_1, R.id.row_2, R.id.row_3, R.id.row_4)
            val dotIds    = listOf(R.id.dot_0, R.id.dot_1, R.id.dot_2, R.id.dot_3, R.id.dot_4)
            val nameIds   = listOf(R.id.name_0, R.id.name_1, R.id.name_2, R.id.name_3, R.id.name_4)
            val dateIds   = listOf(R.id.date_0, R.id.date_1, R.id.date_2, R.id.date_3, R.id.date_4)

            try {
                val arr = JSONArray(schedulesJson)
                val count = arr.length()

                views.setTextViewText(
                    R.id.tv_count,
                    if (count == 0) "本月暂无档期" else "本月 $count 个档期"
                )

                val showCount = minOf(count, 5)
                for (i in 0 until 5) {
                    if (i < showCount) {
                        val item     = arr.getJSONObject(i)
                        val name     = item.optString("name", "")
                        val dateStr  = item.optString("date", "")
                        val colorHex = item.optString("color", "#8b7cf6")

                        val dotColor = try { Color.parseColor(colorHex) } catch (e: Exception) { Color.parseColor("#8b7cf6") }

                        views.setViewVisibility(rowIds[i], View.VISIBLE)
                        views.setTextViewText(nameIds[i], name)
                        views.setTextViewText(dateIds[i], dateStr)
                        views.setTextColor(dotIds[i], dotColor)
                    } else {
                        views.setViewVisibility(rowIds[i], View.GONE)
                    }
                }

                // 超出5条时显示"还有X个"
                if (count > 5) {
                    views.setViewVisibility(R.id.tv_more, View.VISIBLE)
                    views.setTextViewText(R.id.tv_more, "还有 ${count - 5} 个档期...")
                } else {
                    views.setViewVisibility(R.id.tv_more, View.GONE)
                }

            } catch (e: Exception) {
                views.setTextViewText(R.id.tv_count, "本月暂无档期")
            }

            appWidgetManager.updateAppWidget(widgetId, views)
        }
    }
}
