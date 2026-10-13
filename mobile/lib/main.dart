import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'api.dart';
import 'auth.dart';
import 'drafts.dart';
import 'screens/shell.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Api.instance.loadTokens();
  await AuthState.instance.refresh();
  runApp(const AawenApp());
  // Resend queued reports whenever connectivity returns (idempotent by client id).
  Connectivity().onConnectivityChanged.listen((r) {
    if (!r.contains(ConnectivityResult.none)) unawaited(DraftStore.instance.flush());
  });
  unawaited(DraftStore.instance.flush());
}

class AawenApp extends StatelessWidget {
  const AawenApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: AuthState.instance,
      builder: (context, _) => MaterialApp(
        title: 'عاون',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(),
        locale: AuthState.instance.locale,
        supportedLocales: const [Locale('ar'), Locale('en')],
        localizationsDelegates: const [
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        home: const Shell(),
      ),
    );
  }
}
