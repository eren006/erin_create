import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'services/auth_service.dart';
import 'services/api_service.dart';
import 'services/notification_service.dart';
import 'services/widget_service.dart';
import 'screens/login_screen.dart';
import 'screens/main_screen.dart';
import 'utils/theme_utils.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 初始化通知服务 + 小组件
  await NotificationService.init();
  await WidgetService.init();

  final authService = AuthService();
  await authService.loadToken();

  // 如果本地有 token，去服务器验证并恢复用户信息
  if (authService.isLoggedIn) {
    try {
      final user = await ApiService(authService).getMe();
      authService.setUser(user);
    } catch (_) {
      // token 失效，清除登录状态，跳到登录页
      await authService.logout();
    }
  }

  runApp(
    ChangeNotifierProvider.value(
      value: authService,
      child: const YucaApp(),
    ),
  );
}


class YucaApp extends StatelessWidget {
  const YucaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthService>(
      builder: (context, auth, _) {
        final themeId = auth.user?.theme ?? '';
        final seedColor = themeToColor(themeId);
        final isDay = themeId.endsWith('-day');
        final brightness = isDay ? Brightness.light : Brightness.dark;
        final scheme = ColorScheme.fromSeed(
          seedColor: seedColor,
          brightness: brightness,
        );
        // 背景：白日主题用浅色，夜间用深色
        final scaffoldBg = isDay
            ? Color.lerp(const Color(0xFFF8F6FF), seedColor, 0.08)!
            : Color.lerp(const Color(0xFF0d0d1a), seedColor, 0.08)!;
        final surfaceBg = isDay
            ? Color.lerp(const Color(0xFFEEEBFF), seedColor, 0.10)!
            : Color.lerp(const Color(0xFF111827), seedColor, 0.10)!;
        final onSurface = scheme.onSurface;
        final mutedColor = isDay ? const Color(0xFF6b6b80) : const Color(0xFF6b7280);

        return MaterialApp(
          title: 'Yuca Helper',
          debugShowCheckedModeBanner: false,
          theme: ThemeData(
            colorScheme: scheme,
            useMaterial3: true,
            brightness: brightness,
            scaffoldBackgroundColor: scaffoldBg,
            // ── 底部导航 ──────────────────────────────────────────
            bottomNavigationBarTheme: BottomNavigationBarThemeData(
              backgroundColor: surfaceBg,
              selectedItemColor: seedColor,
              unselectedItemColor: mutedColor,
              selectedLabelStyle: const TextStyle(fontSize: 11),
              unselectedLabelStyle: const TextStyle(fontSize: 11),
              type: BottomNavigationBarType.fixed,
            ),
            // ── AppBar ───────────────────────────────────────────
            appBarTheme: AppBarTheme(
              backgroundColor: surfaceBg,
              foregroundColor: onSurface,
              iconTheme: IconThemeData(color: seedColor),
              actionsIconTheme: IconThemeData(color: seedColor),
              elevation: 0,
            ),
            // ── TabBar ───────────────────────────────────────────
            tabBarTheme: TabBarThemeData(
              indicatorColor: seedColor,
              labelColor: seedColor,
              unselectedLabelColor: const Color(0xFF6b7280),
            ),
            // ── FAB ──────────────────────────────────────────────
            floatingActionButtonTheme: FloatingActionButtonThemeData(
              backgroundColor: seedColor,
              foregroundColor: Colors.white,
            ),
            // ── 按钮 ─────────────────────────────────────────────
            elevatedButtonTheme: ElevatedButtonThemeData(
              style: ElevatedButton.styleFrom(
                backgroundColor: seedColor,
                foregroundColor: Colors.white,
                elevation: 0,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
              ),
            ),
            textButtonTheme: TextButtonThemeData(
              style: TextButton.styleFrom(foregroundColor: seedColor),
            ),
            // ── 进度指示器 ────────────────────────────────────────
            progressIndicatorTheme:
                ProgressIndicatorThemeData(color: seedColor),
            // ── 勾选 / 开关 ───────────────────────────────────────
            checkboxTheme: CheckboxThemeData(
              fillColor: WidgetStateProperty.resolveWith(
                  (s) => s.contains(WidgetState.selected) ? seedColor : null),
            ),
            // ── 文字默认色 ────────────────────────────────────────────
            textTheme: TextTheme(
              bodyLarge:   TextStyle(color: onSurface),
              bodyMedium:  TextStyle(color: onSurface),
              bodySmall:   TextStyle(color: onSurface.withAlpha(180)),
              titleLarge:  TextStyle(color: onSurface),
              titleMedium: TextStyle(color: onSurface),
              titleSmall:  TextStyle(color: onSurface.withAlpha(200)),
              labelLarge:  TextStyle(color: onSurface),
              labelMedium: TextStyle(color: onSurface.withAlpha(180)),
              labelSmall:  TextStyle(color: onSurface.withAlpha(150)),
            ),
            // ── 对话框 / 底部弹出 ──────────────────────────────────
            dialogTheme: DialogThemeData(
              backgroundColor: surfaceBg,
              titleTextStyle: TextStyle(
                  color: onSurface, fontSize: 18, fontWeight: FontWeight.w600),
              contentTextStyle: TextStyle(color: onSurface.withAlpha(180), fontSize: 14),
            ),
            // ── 卡片 ──────────────────────────────────────────────
            cardColor: surfaceBg,
            // ── 输入框 ────────────────────────────────────────────
            inputDecorationTheme: InputDecorationTheme(
              filled: true,
              fillColor: isDay ? const Color(0xFFEEEBFF) : const Color(0xFF1a1a2e),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide(color: isDay ? seedColor.withAlpha(80) : const Color(0xFF374151)),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide(color: isDay ? seedColor.withAlpha(80) : const Color(0xFF374151)),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide(color: seedColor),
              ),
              labelStyle: TextStyle(color: onSurface.withAlpha(150)),
              hintStyle: const TextStyle(color: Color(0xFF6b7280)),
            ),
          ),
          home: auth.isLoggedIn
              ? const _RulesGate(child: MainScreen())
              : const _RulesGate(child: LoginScreen()),
          routes: {
            '/login': (_) => const LoginScreen(),
            '/main':  (_) => const MainScreen(),
          },
        );
      },
    );
  }
}

// ── 须知守则拦截器（首次打开弹出） ──────────────────────────────────────────────

class _RulesGate extends StatefulWidget {
  final Widget child;
  const _RulesGate({required this.child});
  @override
  State<_RulesGate> createState() => _RulesGateState();
}

class _RulesGateState extends State<_RulesGate> {
  static const _key = 'yuca_rules_v1_accepted';
  final _storage = const FlutterSecureStorage();
  bool _checked = false;

  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    final accepted = await _storage.read(key: _key);
    if (!mounted) return;
    if (accepted != '1') {
      // 未接受，弹出须知
      WidgetsBinding.instance.addPostFrameCallback((_) => _showRules());
    }
    setState(() => _checked = true);
  }

  Future<void> _accept() async {
    await _storage.write(key: _key, value: '1');
    if (mounted) Navigator.of(context).pop();
  }

  void _showRules() {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => _RulesDialog(onAccept: _accept),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_checked) {
      return const Scaffold(
        backgroundColor: Color(0xFF1a1a2e),
        body: Center(
          child: CircularProgressIndicator(color: Color(0xFF8b7cf6)),
        ),
      );
    }
    return widget.child;
  }
}

// ── 须知弹窗 ──────────────────────────────────────────────────────────────────

class _RulesDialog extends StatefulWidget {
  final VoidCallback onAccept;
  const _RulesDialog({required this.onAccept});
  @override
  State<_RulesDialog> createState() => _RulesDialogState();
}

class _RulesDialogState extends State<_RulesDialog> {
  bool _scrolledToBottom = false;
  final _scrollCtrl = ScrollController();

  @override
  void initState() {
    super.initState();
    _scrollCtrl.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollCtrl.removeListener(_onScroll);
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollCtrl.position.pixels >=
        _scrollCtrl.position.maxScrollExtent - 10) {
      if (!_scrolledToBottom) setState(() => _scrolledToBottom = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: Dialog(
        backgroundColor: const Color(0xFF16213e),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        insetPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 40),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          // 标题
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
            decoration: const BoxDecoration(
              border: Border(
                  bottom: BorderSide(color: Color(0xFF374151))),
            ),
            child: Column(children: [
              Container(
                width: 48, height: 48,
                decoration: BoxDecoration(
                  color: const Color(0xFF8b7cf6).withAlpha(30),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.shield_outlined,
                    color: Color(0xFF8b7cf6), size: 26),
              ),
              const SizedBox(height: 10),
              const Text('使用须知 & 社区守则',
                  style: TextStyle(
                      color: Colors.white,
                      fontSize: 17,
                      fontWeight: FontWeight.bold)),
              const SizedBox(height: 4),
              const Text('请阅读完整内容后方可使用',
                  style: TextStyle(color: Color(0xFF6b7280), fontSize: 12)),
            ]),
          ),

          // 正文（可滚动）
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 380),
            child: SingleChildScrollView(
              controller: _scrollCtrl,
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
              child: _RulesContent(),
            ),
          ),

          // 底部按钮
          Container(
            width: double.infinity,
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
            decoration: const BoxDecoration(
              border: Border(top: BorderSide(color: Color(0xFF374151))),
            ),
            child: Column(children: [
              if (!_scrolledToBottom)
                const Padding(
                  padding: EdgeInsets.only(bottom: 8),
                  child: Text('↓ 滚动阅读全部内容',
                      style: TextStyle(
                          color: Color(0xFF6b7280), fontSize: 12)),
                ),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: _scrolledToBottom
                        ? const Color(0xFF8b7cf6)
                        : const Color(0xFF374151),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10)),
                    padding: const EdgeInsets.symmetric(vertical: 14),
                    elevation: 0,
                  ),
                  onPressed: _scrolledToBottom ? widget.onAccept : null,
                  child: Text(
                    _scrolledToBottom ? '我已阅读并同意，进入应用' : '请先阅读完所有内容',
                    style: const TextStyle(fontSize: 14),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => SystemNavigator.pop(),
                child: const Text('不同意，退出应用',
                    style: TextStyle(
                        color: Color(0xFF6b7280), fontSize: 12)),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}

class _RulesContent extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _section('📌 关于本应用', [
        '语擦日历 App 是一款专为语c（语言 cosplay）爱好者设计的个人档期管理工具，帮助大家记录、整理日常语擦安排。',
        '本应用为私人工具，所有数据仅供个人使用。',
      ]),
      _section('🔞 年龄要求', [
        '本应用所涉及的语c（角色扮演）内容可能包含成人向情境，使用者须年满 18 周岁。',
        '未满 18 周岁者请立即退出。继续使用即视为确认已达法定年龄。',
      ]),
      _section('📜 社区行为守则', [
        '1. 尊重他人。禁止骚扰、辱骂、威胁或歧视任何用户。',
        '2. 禁止在公会或公开功能中传播他人隐私（QQ 号、真实信息等）。',
        '3. 黑名单与检举功能仅用于记录真实的不良经历，禁止捏造、诬陷。',
        '4. 禁止利用本 App 传播违法违规内容，包括但不限于涉及未成年人的不当内容。',
        '5. 禁止恶意刷屏、攻击服务器或破坏他人数据。',
      ]),
      _section('⚠️ 免责声明', [
        '本应用不对用户填写的内容承担法律责任，用户须自行为其行为负责。',
        '应用内的搭档、黑名单、公会等功能产生的数据，由用户本人管理，请谨慎填写。',
        '开发者保留在不通知的情况下对违规账号进行封禁的权利。',
      ]),
      _section('🔒 隐私说明', [
        '您的数据（档期、日记、戏录等）仅用于本应用功能展示，不会出售或分享给第三方。',
        '公会、公开检举等功能中的内容对其他用户可见，填写前请自行考虑。',
      ]),
      const SizedBox(height: 4),
      const Text(
        '继续使用本应用即代表您已阅读、理解并同意以上全部内容。',
        style: TextStyle(
            color: Color(0xFF8b7cf6),
            fontSize: 12,
            fontStyle: FontStyle.italic,
            height: 1.6),
      ),
    ]);
  }

  Widget _section(String title, List<String> items) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title,
            style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w600)),
        const SizedBox(height: 6),
        ...items.map((t) => Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Text(t,
                  style: const TextStyle(
                      color: Color(0xFF9ca3af),
                      fontSize: 12,
                      height: 1.65)),
            )),
      ]),
    );
  }
}
