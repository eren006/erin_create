import 'package:flutter/material.dart';

Color themeToColor(String? theme) {
  const map = {
    'default':           Color(0xFF8b7cf6),
    'spring':            Color(0xFFf472b6),
    'summer':            Color(0xFF06b6d4),
    'autumn':            Color(0xFFf59e0b),
    'winter':            Color(0xFF7dd3fc),
    'monet':             Color(0xFFa8d8ea),
    'vangogh':           Color(0xFFe8b840),
    'picasso':           Color(0xFFe06840),
    'davinci':           Color(0xFFc8882a),
    'gukaizhi':          Color(0xFFc03830),
    'michelangelo':      Color(0xFFc8a050),
    'warhol':            Color(0xFFffd700),
    'spring-day':        Color(0xFFdb2777),
    'summer-day':        Color(0xFF0284c7),
    'autumn-day':        Color(0xFFb45309),
    'winter-day':        Color(0xFF1d6fa0),
    'monet-day':         Color(0xFF4a8fa8),
    'vangogh-day':       Color(0xFF1a4a9a),
    'picasso-day':       Color(0xFFc04828),
    'davinci-day':       Color(0xFF8a3c10),
    'gukaizhi-day':      Color(0xFF9a2018),
    'michelangelo-day':  Color(0xFF7a3e18),
    'warhol-day':        Color(0xFFcc0000),
    'vip-gold':          Color(0xFFf59e0b),
    'vip-jade':          Color(0xFF10b981),
    'achieve-first-drama': Color(0xFFe879f9),
    'achieve-sched-10':    Color(0xFF22d3ee),
    'achieve-sched-50':    Color(0xFFf59e0b),
  };
  return map[theme ?? ''] ?? const Color(0xFF8b7cf6);
}
