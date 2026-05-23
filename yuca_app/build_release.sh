#!/bin/bash
# 构建并输出带版本号的 APK

VERSION=$(grep "^version:" pubspec.yaml | sed 's/version: //' | sed 's/+.*//' | tr -d ' ')
OUTPUT="build/app/outputs/flutter-apk/yuca_v${VERSION}.apk"

echo "🔨 构建中..."
flutter build apk --release

if [ $? -eq 0 ]; then
  cp build/app/outputs/flutter-apk/app-release.apk "$OUTPUT"
  echo ""
  echo "✅ 完成！APK 路径："
  echo "   $(pwd)/$OUTPUT"
else
  echo "❌ 构建失败"
fi
