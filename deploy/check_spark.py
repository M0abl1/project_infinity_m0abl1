"""Validate locally on the game host; print only non-sensitive aggregate counts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from panel.config import Settings
from panel.spark import SparkReports

reports = SparkReports(Settings.load().root)
items = reports.listing()
if not items:
    raise SystemExit('No completed local spark profile available')
result = reports.read(items[0]['name'])
print('profile_parsed=True', 'components=' + str(len(result['rows'])),
      'threads=' + str(len(result['threads'])), 'source_maps=' + str(result['mapped']),
      'direct_total_percent=' + str(round(sum(r['direct_percent'] for r in result['rows']), 2)))
