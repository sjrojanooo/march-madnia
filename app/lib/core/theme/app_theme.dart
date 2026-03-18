import 'package:flutter/material.dart';

class AppTheme {
  static const Color _orange = Color(0xFFFF6D00);
  static const Color _darkBg = Color(0xFF121212);
  static const Color _surfaceDark = Color(0xFF1E1E1E);
  static const Color _cardDark = Color(0xFF2A2A2A);

  static ThemeData get dark => ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: _darkBg,
        colorScheme: const ColorScheme.dark(
          primary: _orange,
          secondary: _orange,
          surface: _surfaceDark,
          onPrimary: Colors.black,
          onSecondary: Colors.black,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: _surfaceDark,
          elevation: 0,
          centerTitle: true,
        ),
        cardTheme: const CardThemeData(
          color: _cardDark,
          elevation: 2,
          margin: EdgeInsets.symmetric(
            horizontal: 8,
            vertical: 4,
          ),
        ),
        bottomNavigationBarTheme:
            const BottomNavigationBarThemeData(
          backgroundColor: _surfaceDark,
          selectedItemColor: _orange,
          unselectedItemColor: Colors.grey,
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: _cardDark,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: const BorderSide(
              color: _orange,
            ),
          ),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: _orange,
            foregroundColor: Colors.black,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
        useMaterial3: true,
      );
}
