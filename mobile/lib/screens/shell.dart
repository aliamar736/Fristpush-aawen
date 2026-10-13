import 'package:flutter/material.dart';

import '../auth.dart';
import '../l10n.dart';
import '../theme.dart';
import '../widgets.dart';
import 'aawen.dart';
import 'contribute.dart';
import 'home.dart';
import 'impact.dart';
import 'map.dart';
import 'report_wizard.dart';

/// Five tabs (حومتي، الخريطة، عاون، ساهم، أثري) with a prominent «بلّغ» button in the middle.
class Shell extends StatefulWidget {
  const Shell({super.key});
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  int _i = 0;
  @override
  Widget build(BuildContext context) {
    final pages = const [HomeTab(), MapTab(), AawenTab(), ContributeTab(), ImpactTab()];
    return Scaffold(
      appBar: AppBar(
        title: const BrandLogo(),
        actions: [
          IconButton(
            tooltip: tr(context, 'English', 'العربية'),
            icon: const Icon(Icons.language),
            onPressed: () => AuthState.instance.setLocale(AuthState.instance.locale.languageCode == 'ar' ? 'en' : 'ar'),
          ),
        ],
      ),
      body: IndexedStack(index: _i, children: pages),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,
      floatingActionButton: Semantics(
        button: true,
        label: tr(context, 'بلّغ عن مشكلة', 'Report a problem'),
        child: FloatingActionButton.large(
          backgroundColor: Brand.teal,
          foregroundColor: Brand.petrol,
          shape: const CircleBorder(side: BorderSide(color: Brand.ivory, width: 4)),
          onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const ReportWizard())),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.add, size: 30),
            Text(tr(context, 'بلّغ', 'Report'), style: const TextStyle(fontWeight: FontWeight.w700)),
          ]),
        ),
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _i,
        onDestinationSelected: (i) => setState(() => _i = i),
        destinations: [
          NavigationDestination(icon: const Icon(Icons.home_outlined), selectedIcon: const Icon(Icons.home), label: tr(context, 'حومتي', 'My area')),
          NavigationDestination(icon: const Icon(Icons.map_outlined), selectedIcon: const Icon(Icons.map), label: tr(context, 'الخريطة', 'Map')),
          NavigationDestination(icon: const Icon(Icons.volunteer_activism_outlined), selectedIcon: const Icon(Icons.volunteer_activism), label: tr(context, 'عاون', 'Help')),
          NavigationDestination(icon: const Icon(Icons.savings_outlined), selectedIcon: const Icon(Icons.savings), label: tr(context, 'ساهم', 'Contribute')),
          NavigationDestination(icon: const Icon(Icons.person_outline), selectedIcon: const Icon(Icons.person), label: tr(context, 'أثري', 'My impact')),
        ],
      ),
    );
  }
}
