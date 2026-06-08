import csv
import os

with open("data/eval/fixtures/sales.csv", newline="") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

total_rows = len(rows)
amounts = [float(r["amount"]) for r in rows]
total_amount = sum(amounts)
max_row = max(rows, key=lambda r: float(r["amount"]))

report = f"""Sales Summary Report
====================
Total rows: {total_rows}
Sum of 'amount': {total_amount:.2f}
Row with highest amount: {max_row}
"""

os.makedirs("data/eval/workspace", exist_ok=True)
with open("data/eval/workspace/E09_report.txt", "w") as f:
    f.write(report)

print(report)
print("Report written to data/eval/workspace/E09_report.txt")
