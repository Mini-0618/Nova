import csv
import os

# Ensure output directory exists
os.makedirs('data/eval/workspace', exist_ok=True)

# Read the CSV
rows = []
with open('data/eval/fixtures/sales.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

# Compute summary
total_rows = len(rows)
amounts = [float(row['amount']) for row in rows]
total_amount = sum(amounts)
max_idx = amounts.index(max(amounts))
max_row = rows[max_idx]

# Build report
report = f"""Sales Summary Report
====================
Total rows: {total_rows}
Sum of 'amount': {total_amount:.2f}
Row with highest amount:
  Date: {max_row['date']}, Product: {max_row['product']}, Amount: {max_row['amount']}, Quantity: {max_row['quantity']}
"""

print(report)

# Write report
with open('data/eval/workspace/E09_report.txt', 'w') as f:
    f.write(report)

print('Report written successfully!')
