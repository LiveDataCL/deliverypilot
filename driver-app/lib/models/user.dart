/// Mirrors backend UserOut (app/schemas/auth.py).
class User {
  const User({
    required this.id,
    required this.businessId,
    required this.role,
    required this.email,
    required this.phone,
    required this.isActive,
  });

  final int id;
  final int businessId;
  final String role;
  final String email;
  final String? phone;
  final bool isActive;

  factory User.fromJson(Map<String, dynamic> json) => User(
        id: json['id'] as int,
        businessId: json['business_id'] as int,
        role: json['role'] as String,
        email: json['email'] as String,
        phone: json['phone'] as String?,
        isActive: json['is_active'] as bool,
      );

  bool get isDriver => role == 'driver';
}
