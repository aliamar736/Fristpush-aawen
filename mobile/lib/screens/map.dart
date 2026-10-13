import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../api.dart';
import '../l10n.dart';
import '../theme.dart';
import 'report_detail.dart';
import 'road_alert.dart';

const tileUrl = String.fromEnvironment('AAWEN_TILES', defaultValue: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
const tripoli = LatLng(32.8872, 13.1913);

class _Pt {
  _Pt(this.lat, this.lng, this.color, this.label, this.onTap, {this.square = false});
  final double lat, lng;
  final Color color;
  final String label;
  final VoidCallback onTap;
  final bool square;
}

/// Map tab: independent layers (services, road-now, walkability), status filter, and grid clustering when zoomed out.
class MapTab extends StatefulWidget {
  const MapTab({super.key});
  @override
  State<MapTab> createState() => _MapTabState();
}

class _MapTabState extends State<MapTab> {
  final _ctrl = MapController();
  bool services = true, road = true, pedestrian = true;
  String status = 'open';
  List<Map<String, dynamic>> _reports = [], _alerts = [];
  Map<int, String> _layerOf = {};
  double _zoom = 13;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final cats = ((await Api.instance.getCached('/categories/')).data as Map)['results'] as List;
      _layerOf = {for (final c in cats) c['id'] as int: c['layer'] as String};
      final st = status == 'all' ? '' : '&status=$status';
      _reports = ((await Api.instance.getCached('/reports/?view=map&since=30$st')).data as List).cast<Map<String, dynamic>>();
      _alerts = ((await Api.instance.getCached('/road-alerts/')).data as List).cast<Map<String, dynamic>>();
      _error = null;
    } catch (e) {
      _error = e.toString();
    }
    if (mounted) setState(() {});
  }

  List<_Pt> _points() {
    final out = <_Pt>[];
    for (final r in _reports) {
      final layer = _layerOf[r['category_id']] ?? 'services';
      if (layer == 'pedestrian' ? !pedestrian : !services) continue;
      out.add(_Pt((r['lat'] as num).toDouble(), (r['lng'] as num).toDouble(),
          r['status'] == 'resolved' ? Brand.petrol : layer == 'pedestrian' ? const Color(0xFF2D5A61) : Brand.tealInk,
          r['tracking_number'] as String? ?? '', () => Navigator.push(context, MaterialPageRoute(builder: (_) => ReportDetail(id: r['id'] as int)))));
    }
    if (road) {
      for (final a in _alerts) {
        out.add(_Pt((a['lat'] as num).toDouble(), (a['lng'] as num).toDouble(),
            a['type'] == 'accident' ? Brand.danger : a['type'] == 'obstacle' ? Brand.yellow : Brand.petrolDeep, a['type_label'] as String,
            () => Navigator.push(context, MaterialPageRoute(builder: (_) => RoadAlertDetail(id: a['id'] as int))), square: true));
      }
    }
    return out;
  }

  /// Simple grid clustering: points within the same ~60px cell at the current zoom are merged.
  List<Marker> _markers() {
    final pts = _points();
    if (_zoom >= 16) return pts.map(_single).toList();
    final cell = 60 / (256 * math.pow(2, _zoom)) * 360;
    final groups = <String, List<_Pt>>{};
    for (final p in pts) {
      groups.putIfAbsent('${(p.lat / cell).floor()}:${(p.lng / cell).floor()}', () => []).add(p);
    }
    return groups.values.map((g) {
      if (g.length == 1) return _single(g.first);
      final lat = g.map((p) => p.lat).reduce((a, b) => a + b) / g.length;
      final lng = g.map((p) => p.lng).reduce((a, b) => a + b) / g.length;
      return Marker(point: LatLng(lat, lng), width: 44, height: 44, child: Semantics(
        button: true, label: tr(context, '${g.length} علامات — اضغط للتكبير', '${g.length} markers — tap to zoom'),
        child: GestureDetector(onTap: () => _ctrl.move(LatLng(lat, lng), _zoom + 2),
          child: Container(decoration: BoxDecoration(color: Brand.petrol, shape: BoxShape.circle, border: Border.all(color: Brand.teal, width: 3)),
            alignment: Alignment.center, child: Text('${g.length}', style: const TextStyle(color: Brand.ivory, fontWeight: FontWeight.w700))))));
    }).toList();
  }

  Marker _single(_Pt p) => Marker(point: LatLng(p.lat, p.lng), width: 40, height: 40, child: Semantics(button: true, label: p.label,
      child: GestureDetector(onTap: p.onTap, child: Icon(p.square ? Icons.warning_rounded : Icons.location_on, color: p.color, size: 36))));

  @override
  Widget build(BuildContext context) {
    return Stack(children: [
      FlutterMap(
        mapController: _ctrl,
        options: MapOptions(initialCenter: tripoli, initialZoom: 13, onPositionChanged: (pos, _) => setState(() => _zoom = pos.zoom)),
        children: [
          TileLayer(urlTemplate: tileUrl, userAgentPackageName: 'ly.aawen.app'),
          MarkerLayer(markers: _markers()),
          const RichAttributionWidget(attributions: [TextSourceAttribution('OpenStreetMap contributors')]),
        ],
      ),
      Positioned(top: 8, left: 8, right: 8, child: Wrap(spacing: 6, runSpacing: 6, children: [
        FilterChip(label: Text(tr(context, 'مشاكل الخدمات', 'Services')), selected: services, onSelected: (v) => setState(() => services = v)),
        FilterChip(label: Text(tr(context, 'الطريق توّا', 'Road now')), selected: road, onSelected: (v) => setState(() => road = v)),
        FilterChip(label: Text(tr(context, 'طريق للكل', 'Walkability')), selected: pedestrian, onSelected: (v) => setState(() => pedestrian = v)),
        DropdownButton<String>(value: status, items: [
          DropdownMenuItem(value: 'open', child: Text(tr(context, 'المفتوحة', 'Open'))),
          DropdownMenuItem(value: 'resolved', child: Text(tr(context, 'المحلولة', 'Resolved'))),
          DropdownMenuItem(value: 'all', child: Text(tr(context, 'الكل', 'All'))),
        ], onChanged: (v) { status = v!; _load(); }),
        ActionChip(avatar: const Icon(Icons.add), label: Text(tr(context, 'تنبيه طريق', 'Road alert')),
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const RoadAlertNew()))),
      ])),
      if (_error != null) Positioned(bottom: 8, left: 8, right: 8, child: Material(color: Brand.yellowWash, child: Padding(padding: const EdgeInsets.all(8), child: Text(_error!)))),
    ]);
  }
}
