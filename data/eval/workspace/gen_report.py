import csv
import os

csv_path = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'sales.csv')
output_path = os.path.join(os.path.dirname(__file__), 'E09_report.txt')

with open(csv_path, 'r', newline='') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total_rows = len(rows)
total_amount = sum(float(r['amount']) for r in rows)
max_row = max(rows, key=lambda r: float(r['amount']))

with open(output_path, 'w') as f:
    f.write(f'Total rows: {total_rows}\n')
    f.write(f'Sum of amount: {total_amount:.2f}\n')
    f.write(f'Highest amount row: {max_row}\n')

print('Report generated successfully')
print(f'Total rows: {total_rows}')
print(f'Sum of amount: {total_amount:.2f}')
print(f'Highest amount row: {max_row}')
