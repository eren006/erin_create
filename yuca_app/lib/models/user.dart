class User {
  final int id;
  final String username;
  final String displayName;
  final String theme;
  final bool isVip;
  final List<String> unlockedAchievements;

  User({
    required this.id,
    required this.username,
    required this.displayName,
    required this.theme,
    this.isVip = false,
    this.unlockedAchievements = const [],
  });

  factory User.fromJson(Map<String, dynamic> json) {
    return User(
      id:          json['id'] as int,
      username:    json['username'] as String,
      displayName: json['display_name'] as String,
      theme:       json['theme'] as String? ?? '',
      isVip:       json['is_vip'] as bool? ?? false,
      unlockedAchievements: (json['unlocked_achievements'] as List<dynamic>?)
              ?.map((e) => e as String)
              .toList() ??
          [],
    );
  }

  User copyWith({String? theme}) => User(
    id:                   id,
    username:             username,
    displayName:          displayName,
    theme:                theme ?? this.theme,
    isVip:                isVip,
    unlockedAchievements: unlockedAchievements,
  );
}
