import 'package:flutter/material.dart';

/// Brand tokens from the AAWEN identity board.
class Brand {
  static const petrol = Color(0xFF123F46);
  static const petrolDeep = Color(0xFF0C2E33);
  static const teal = Color(0xFF20B7A5);
  static const tealInk = Color(0xFF0B6E64); // AA-contrast teal for text on ivory
  static const tealWash = Color(0xFFDDF2EE);
  static const yellow = Color(0xFFF4B544);
  static const yellowWash = Color(0xFFFCEFD3);
  static const yellowInk = Color(0xFF6B4800);
  static const ivory = Color(0xFFF6F3EC);
  static const line = Color(0xFFE1DACB);
  static const muted = Color(0xFF56676A);
  static const danger = Color(0xFFA8261B);
  static const ok = Color(0xFF1C6E45);
}

ThemeData buildTheme() {
  final base = ThemeData(
    useMaterial3: true,
    fontFamily: 'IBMPlexSansArabic',
    colorScheme: ColorScheme.fromSeed(
      seedColor: Brand.petrol,
      primary: Brand.petrol,
      onPrimary: Brand.ivory,
      secondary: Brand.teal,
      onSecondary: Brand.petrol,
      tertiary: Brand.yellow,
      surface: Colors.white,
      error: Brand.danger,
    ),
    scaffoldBackgroundColor: Brand.ivory,
  );
  return base.copyWith(
    appBarTheme: const AppBarTheme(backgroundColor: Brand.ivory, foregroundColor: Brand.petrol, elevation: 0, centerTitle: false),
    cardTheme: CardTheme(
      color: Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16), side: const BorderSide(color: Brand.line)),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: Brand.petrol,
        foregroundColor: Brand.ivory,
        minimumSize: const Size(48, 48),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontFamily: 'IBMPlexSansArabic'),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(foregroundColor: Brand.petrol, minimumSize: const Size(48, 48), shape: const StadiumBorder()),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: Colors.white,
      indicatorColor: Brand.tealWash,
      labelTextStyle: WidgetStateProperty.all(const TextStyle(fontSize: 12, fontFamily: 'IBMPlexSansArabic')),
    ),
  );
}
