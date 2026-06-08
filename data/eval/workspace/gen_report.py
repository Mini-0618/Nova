import csv
import os

csv_path = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'sales.csv')
report_path = os.path.join(os.path.dirname(__file__), 'E09_report.txt')

with open(csv_path) as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total_rows = len(rows)
amounts = [float(r['amount']) for r in rows]
total_amount = sum(amounts)
max_row = max(rows, key=lambda r: float(r['amount']))

with open(report_path, 'w') as f:
    f.write(f"Total rows: {total_rows}\n")
    f.write(f"Sum of amount: {total_amount}\n")
    f.write(f"Row with highest amount: {max_row}\n")

print("Report generated successfully.")
print(f"Total rows: {total_rows}")
print(f"Sum of amount: {total_amount}")
print(f"Row with highest amount: {max_row}")
