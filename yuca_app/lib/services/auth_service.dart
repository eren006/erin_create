import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../models/user.dart';

// AuthService 负责管理登录状态和 Token 存储
// 继承 ChangeNotifier 是为了让 UI 能感知到登录/登出的变化

class AuthService extends ChangeNotifier {
  static const _tokenKey = 'yuca_token';

  final _storage = const FlutterSecureStorage();

  String? _token;
  User?   _user;

  String? get token => _token;
  User?   get user  => _user;
  bool    get isLoggedIn => _token != null;

  // App 启动时从本地存储读取 Token
  Future<void> loadToken() async {
    _token = await _storage.read(key: _tokenKey);
    notifyListeners();
  }

  // 登录成功后保存 Token 和用户信息
  Future<void> saveLogin(String token, User user) async {
    _token = token;
    _user  = user;
    await _storage.write(key: _tokenKey, value: token);
    notifyListeners();
  }

  // 恢复已登录会话时直接设置用户（不更新 token）
  void setUser(User user) {
    _user = user;
    notifyListeners();
  }

  // 仅更新本地缓存的主题（API 已保存后调用）
  void updateTheme(String theme) {
    if (_user == null) return;
    _user = _user!.copyWith(theme: theme);
    notifyListeners();
  }

  // 登出
  Future<void> logout() async {
    _token = null;
    _user  = null;
    await _storage.delete(key: _tokenKey);
    notifyListeners();
  }
}
