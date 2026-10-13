import 'package:flutter/material.dart';

import '../api.dart';
import '../auth.dart';
import '../l10n.dart';
import '../theme.dart';

/// Phone + one-time code. Returns true when signed in.
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  static Future<bool> ensure(BuildContext context) async {
    if (AuthState.instance.signedIn) return true;
    return await Navigator.push<bool>(context, MaterialPageRoute(builder: (_) => const LoginScreen())) ?? false;
  }

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _phone = TextEditingController();
  final _code = TextEditingController();
  final _name = TextEditingController();
  bool _sent = false, _busy = false;
  String? _err, _devCode;

  Future<void> _request() async {
    setState(() { _busy = true; _err = null; });
    try {
      final r = await Api.instance.post('/auth/otp/request', {'phone': _phone.text}) as Map;
      _phone.text = r['phone'] as String;
      _devCode = r['dev_code'] as String?;
      _sent = true;
    } catch (e) {
      _err = e.toString();
    }
    setState(() => _busy = false);
  }

  Future<void> _verify() async {
    setState(() { _busy = true; _err = null; });
    try {
      final r = await Api.instance.post('/auth/otp/verify', {'phone': _phone.text, 'code': _code.text, 'display_name': _name.text}) as Map;
      await AuthState.instance.signIn(r['access'] as String, r['refresh'] as String);
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      setState(() { _err = e.toString(); _busy = false; });
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(tr(context, 'الدخول إلى عاون', 'Sign in'))),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          Text(tr(context, 'التصفح متاح دون حساب. نحتاج رقمك فقط عند الإرسال أو الحجز أو المساهمة، ولا يظهر لأحد.',
              'We only need your phone to report, book or contribute — it is never shown publicly.'), style: const TextStyle(color: Brand.muted)),
          const SizedBox(height: 16),
          if (_err != null) Text(_err!, style: const TextStyle(color: Brand.danger)),
          if (!_sent) ...[
            TextField(controller: _phone, keyboardType: TextInputType.phone, textDirection: TextDirection.ltr,
                decoration: InputDecoration(labelText: tr(context, 'رقم الهاتف', 'Phone'), hintText: '0912345678')),
            const SizedBox(height: 12),
            FilledButton(onPressed: _busy ? null : _request, child: Text(tr(context, 'أرسل رمز الدخول', 'Send code'))),
          ] else ...[
            if (_devCode != null) Container(color: Brand.yellowWash, padding: const EdgeInsets.all(8),
                child: Text(tr(context, 'بيئة تطوير (محاكي الرسائل): الرمز $_devCode', 'Dev SMS simulator: code $_devCode'))),
            TextField(controller: _code, keyboardType: TextInputType.number, maxLength: 6, textDirection: TextDirection.ltr,
                autofillHints: const [AutofillHints.oneTimeCode], decoration: InputDecoration(labelText: tr(context, 'رمز الدخول', 'Code'))),
            TextField(controller: _name, decoration: InputDecoration(labelText: tr(context, 'اسمك (اختياري)', 'Your name (optional)'))),
            const SizedBox(height: 12),
            FilledButton(onPressed: _busy ? null : _verify, child: Text(tr(context, 'دخول', 'Sign in'))),
          ],
        ]),
      );
}
