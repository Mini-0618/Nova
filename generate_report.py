import csv
import os

os.makedirs('data/eval/workspace', exist_ok=True)

with open('data/eval/fixtures/sales.csv', newline='') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total_rows = len(rows)
amounts = [float(r['amount']) for r in rows]
sum_amount = sum(amounts)
max_row = max(rows, key=lambda r: float(r['amount']))

report = f"""Sales Summary Report
====================
Total rows: {total_rows}
Sum of amount: {sum_amount:.2f}
Row with highest amount: {max_row}
"""

with open('data/eval/workspace/E09_report.txt', 'w') as f:
    f.write(report)

print(report)
