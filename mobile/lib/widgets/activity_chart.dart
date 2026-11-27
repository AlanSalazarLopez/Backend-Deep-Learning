import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:yt_trends_app/models/admin.dart';

/// Barras de predicciones por día (activity_by_day, últimos 14 días).
class ActivityChart extends StatelessWidget {
  const ActivityChart({super.key, required this.days});

  final List<DayActivity> days;

  String _label(String date) => date.length >= 10
      ? '${date.substring(8, 10)}/${date.substring(5, 7)}'
      : date;

  @override
  Widget build(BuildContext context) {
    if (days.isEmpty) {
      return const Text('Sin actividad en los últimos 14 días.');
    }
    final theme = Theme.of(context);
    final maxN = days.map((d) => d.n).fold<int>(1, (a, b) => b > a ? b : a);
    final step = maxN <= 4 ? 1 : (maxN / 4).ceil();
    final maxY = ((maxN / step).ceil() * step).toDouble();

    return SizedBox(
      height: 220,
      child: BarChart(
        BarChartData(
          maxY: maxY,
          alignment: BarChartAlignment.spaceAround,
          gridData: const FlGridData(show: true, drawVerticalLine: false),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 32,
                interval: step.toDouble(),
                getTitlesWidget: (v, meta) =>
                    Text(v.toInt().toString(), style: theme.textTheme.bodySmall),
              ),
            ),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 28,
                getTitlesWidget: (v, meta) {
                  final i = v.toInt();
                  if (i < 0 || i >= days.length || i % 2 != 0) {
                    return const SizedBox.shrink();
                  }
                  return Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(_label(days[i].date),
                        style: theme.textTheme.bodySmall),
                  );
                },
              ),
            ),
          ),
          barGroups: [
            for (var i = 0; i < days.length; i++)
              BarChartGroupData(
                x: i,
                barRods: [
                  BarChartRodData(
                    toY: days[i].n.toDouble(),
                    width: 12,
                    color: theme.colorScheme.primary,
                    borderRadius: BorderRadius.circular(3),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}