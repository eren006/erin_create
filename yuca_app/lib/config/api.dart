// API 配置
// 开发时用本地电脑 IP，部署后换成服务器地址

class ApiConfig {
  // 调试时：换成你 Mac 的局域网 IP（手机和电脑要在同一个 WiFi）
  // 运行 `ipconfig getifaddr en0` 查看你的 IP
  static const String baseUrl = 'http://120.26.120.128:5002';

  // 各接口路径
  static const String login      = '/api/v1/login';
  static const String me         = '/api/v1/me';
  static const String calendar   = '/api/v1/calendar';
  static const String schedules  = '/api/v1/schedules';
  static const String stats      = '/api/v1/stats';
  static const String partners   = '/api/v1/partners';
  static const String diary      = '/api/v1/diary';
  static const String wishlist   = '/api/v1/wishlist';
  static const String blacklist  = '/api/v1/blacklist';
  static const String drama      = '/api/v1/drama';
  static const String cards      = '/api/v1/cards';
}
