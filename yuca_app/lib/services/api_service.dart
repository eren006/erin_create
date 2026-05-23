import 'package:dio/dio.dart';
import '../config/api.dart';
import '../models/user.dart';
import 'auth_service.dart';

// ApiService 负责所有网络请求
// 每次请求自动带上 Authorization: Bearer <token>

class ApiService {
  final AuthService _auth;
  late final Dio _dio;

  ApiService(this._auth) {
    _dio = Dio(BaseOptions(
      baseUrl:        ApiConfig.baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 15),
      headers: {'Content-Type': 'application/json'},
    ));

    // 拦截器：每次请求自动加 Token，401 时自动登出
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        final token = _auth.token;
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
      onError: (error, handler) async {
        if (error.response?.statusCode == 401) {
          // Token 无效或过期，清除登录状态
          await _auth.logout();
        }
        handler.next(error);
      },
    ));
  }

  // ── 认证 ──────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> login(String username, String password) async {
    final resp = await _dio.post(ApiConfig.login, data: {
      'username': username,
      'password': password,
    });
    return resp.data as Map<String, dynamic>;
  }

  Future<User> getMe() async {
    final resp = await _dio.get(ApiConfig.me);
    return User.fromJson(resp.data['user'] as Map<String, dynamic>);
  }

  // ── 主题 ──────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> setTheme(String theme) async {
    final resp = await _dio.post('/api/v1/theme', data: {'theme': theme});
    return resp.data as Map<String, dynamic>;
  }

  // ── 日历 ──────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getCalendar(int year, int month) async {
    final resp = await _dio.get(ApiConfig.calendar,
        queryParameters: {'year': year, 'month': month});
    return resp.data as Map<String, dynamic>;
  }

  // ── 日程 ──────────────────────────────────────────────────────────────────

  Future<List<dynamic>> getSchedules() async {
    final resp = await _dio.get(ApiConfig.schedules);
    return resp.data['schedules'] as List<dynamic>;
  }

  Future<Map<String, dynamic>> addSchedule(Map<String, dynamic> data) async {
    final resp = await _dio.post(ApiConfig.schedules, data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> editSchedule(int id, Map<String, dynamic> data) async {
    final resp = await _dio.put('${ApiConfig.schedules}/$id', data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<void> deleteSchedule(int id) async {
    await _dio.delete('${ApiConfig.schedules}/$id');
  }

  // ── 统计 ──────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getStats(int year) async {
    final resp = await _dio.get(ApiConfig.stats, queryParameters: {'year': year});
    return resp.data as Map<String, dynamic>;
  }

  // ── 搭档（必吃榜） ────────────────────────────────────────────────────────

  Future<List<dynamic>> getPartners() async {
    final resp = await _dio.get(ApiConfig.partners);
    return resp.data['partners'] as List<dynamic>;
  }

  Future<Map<String, dynamic>> addPartner(Map<String, dynamic> data) async {
    final resp = await _dio.post(ApiConfig.partners, data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<void> deletePartner(int id) async {
    await _dio.delete('${ApiConfig.partners}/$id');
  }

  // ── 日记 ──────────────────────────────────────────────────────────────────

  Future<List<dynamic>> getDiary() async {
    final resp = await _dio.get(ApiConfig.diary);
    return resp.data['entries'] as List<dynamic>;
  }

  Future<Map<String, dynamic>> addDiaryEntry(Map<String, dynamic> data) async {
    final resp = await _dio.post(ApiConfig.diary, data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<void> deleteDiaryEntry(int id) async {
    await _dio.delete('${ApiConfig.diary}/$id');
  }

  // ── 愿望单 ────────────────────────────────────────────────────────────────

  Future<List<dynamic>> getWishlist() async {
    final resp = await _dio.get(ApiConfig.wishlist);
    return resp.data['items'] as List<dynamic>;
  }

  Future<Map<String, dynamic>> addWishlistItem(Map<String, dynamic> data) async {
    final resp = await _dio.post(ApiConfig.wishlist, data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<void> toggleWishlistItem(int id) async {
    await _dio.post('${ApiConfig.wishlist}/$id/toggle');
  }

  Future<void> deleteWishlistItem(int id) async {
    await _dio.delete('${ApiConfig.wishlist}/$id');
  }

  // ── 公会 ──────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getMyGuilds() async {
    final resp = await _dio.get('/api/v1/guilds');
    return resp.data as Map<String, dynamic>;
  }

  Future<List<dynamic>> discoverGuilds({String q = ''}) async {
    final resp = await _dio.get('/api/v1/guilds/discover',
        queryParameters: q.isNotEmpty ? {'q': q} : {});
    return resp.data['guilds'] as List<dynamic>;
  }

  Future<Map<String, dynamic>> createGuild(
      String name, String slug, String sig) async {
    final resp = await _dio.post('/api/v1/guilds',
        data: {'name': name, 'slug': slug, 'signature': sig});
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getGuildDetail(int gid) async {
    final resp = await _dio.get('/api/v1/guilds/$gid');
    return resp.data as Map<String, dynamic>;
  }

  Future<void> joinGuild(int gid) async {
    await _dio.post('/api/v1/guilds/$gid/join');
  }

  Future<void> leaveGuild(int gid) async {
    await _dio.post('/api/v1/guilds/$gid/leave');
  }

  Future<void> approveGuildMember(int gid, int uid) async {
    await _dio.post('/api/v1/guilds/$gid/approve/$uid');
  }

  Future<void> rejectGuildMember(int gid, int uid) async {
    await _dio.post('/api/v1/guilds/$gid/reject/$uid');
  }

  Future<Map<String, dynamic>> getGuildSchedules(int gid) async {
    final resp = await _dio.get('/api/v1/guilds/$gid/schedules');
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getGuildPartners(int gid) async {
    final resp = await _dio.get('/api/v1/guilds/$gid/partners');
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getGuildBlacklist(int gid) async {
    final resp = await _dio.get('/api/v1/guilds/$gid/blacklist');
    return resp.data as Map<String, dynamic>;
  }

  // ── 戏录 ──────────────────────────────────────────────────────────────────

  Future<List<dynamic>> getDrama() async {
    final resp = await _dio.get(ApiConfig.drama);
    return resp.data['entries'] as List<dynamic>;
  }

  Future<Map<String, dynamic>> addDrama(Map<String, dynamic> data) async {
    final resp = await _dio.post(ApiConfig.drama, data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateDrama(int id, Map<String, dynamic> data) async {
    final resp = await _dio.put('${ApiConfig.drama}/$id', data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<void> updateDramaStatus(int id, String status) async {
    await _dio.patch('${ApiConfig.drama}/$id/status', data: {'status': status});
  }

  Future<void> deleteDrama(int id) async {
    await _dio.delete('${ApiConfig.drama}/$id');
  }

  // ── 黑名单 ────────────────────────────────────────────────────────────────

  Future<List<dynamic>> getBlacklist() async {
    final resp = await _dio.get(ApiConfig.blacklist);
    return resp.data['items'] as List<dynamic>;
  }

  Future<Map<String, dynamic>> addBlacklistItem(Map<String, dynamic> data) async {
    final resp = await _dio.post(ApiConfig.blacklist, data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<void> deleteBlacklistItem(int id) async {
    await _dio.delete('${ApiConfig.blacklist}/$id');
  }

  // ── 公开检举 ──────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getReports() async {
    final resp = await _dio.get('/api/v1/reports');
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> submitReport(
      String targetQq, String tag, String reason) async {
    final resp = await _dio.post('/api/v1/reports',
        data: {'target_qq': targetQq, 'tag': tag, 'reason': reason});
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> deleteReport(int rid) async {
    final resp = await _dio.delete('/api/v1/reports/$rid');
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> editReport(
      int rid, String tag, String reason) async {
    final resp = await _dio.put('/api/v1/reports/$rid',
        data: {'tag': tag, 'reason': reason});
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> appealReport(int rid, String reason) async {
    final resp = await _dio.post('/api/v1/reports/$rid/appeal',
        data: {'reason': reason});
    return resp.data as Map<String, dynamic>;
  }

  // ── 卡包 ──────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getCards({String type = ''}) async {
    final resp = await _dio.get(ApiConfig.cards,
        queryParameters: type.isNotEmpty ? {'type': type} : {});
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> addCard(Map<String, dynamic> data) async {
    final resp = await _dio.post(ApiConfig.cards, data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> editCard(int cid, Map<String, dynamic> data) async {
    final resp = await _dio.put('${ApiConfig.cards}/$cid', data: data);
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> consumeCard(int cid, {int count = 1}) async {
    final resp = await _dio.post('${ApiConfig.cards}/$cid/consume',
        data: {'count': count});
    return resp.data as Map<String, dynamic>;
  }

  Future<void> deleteCard(int cid) async {
    await _dio.delete('${ApiConfig.cards}/$cid');
  }

  Future<Map<String, dynamic>> cleanCards() async {
    final resp = await _dio.post('${ApiConfig.cards}/clean');
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> randomCard({String type = ''}) async {
    final resp = await _dio.get('${ApiConfig.cards}/random',
        queryParameters: type.isNotEmpty ? {'type': type} : {});
    return resp.data as Map<String, dynamic>;
  }
}
