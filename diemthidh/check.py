import pandas as pd

# Đọc file Excel
file_path = "Điểm thi chung.xlsx"
df = pd.read_excel(file_path)

# Giả sử cột chứa số báo danh tên là "SBD" (có thể đổi tên nếu khác)
sbd_list = df['Số báo danh'].dropna().astype(int).sort_values().tolist()

# Tìm min và max để tạo dãy liên tục
sbd_min = min(sbd_list)
sbd_max = max(sbd_list)

# Tìm các SBD bị thiếu
full_range = set(range(sbd_min, sbd_max + 1))
missing_sbd = sorted(full_range - set(sbd_list))

print("Các số báo danh bị thiếu là:")
print(missing_sbd)
print(len(missing_sbd))
