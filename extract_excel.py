import pandas as pd

# Load the Excel file
excel_file = 'Cost Breakdown .xlsx'

# Read each sheet
egg_rolls_df = pd.read_excel(excel_file, sheet_name='Egg Rolls')
sheet4_df = pd.read_excel(excel_file, sheet_name='Sheet4')
overhead_df = pd.read_excel(excel_file, sheet_name='Overhead Cost')
labor_df = pd.read_excel(excel_file, sheet_name='Labor')

print("Egg Rolls Sheet:")
print(egg_rolls_df.head(20))  # First 20 rows
print("\nSheet4:")
print(sheet4_df.head(20))
print("\nOverhead Cost:")
print(overhead_df.head(20))
print("\nLabor:")
print(labor_df.head(20))