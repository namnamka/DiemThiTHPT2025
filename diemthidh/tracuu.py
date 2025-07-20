from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

# Cấu hình để Chrome không hiển thị
chrome_options = Options()
chrome_options.add_argument("--headless")  # chạy không giao diện
chrome_options.add_argument("--disable-gpu")  # tắt tăng tốc phần cứng
chrome_options.add_argument("--window-size=1920x1080")  # kích thước cửa sổ ảo

# Tạo trình duyệt
driver = webdriver.Chrome(options=chrome_options)

# Truy cập trang tra cứu
sbd = "02000001"
url = f"https://tracuudiem.hcm.edu.vn/tra-cuu?SoBaoDanh={sbd}"
driver.get(url)

# Đợi hoặc thao tác lấy dữ liệu
time.sleep(2)  # nếu cần chờ trang tải JS

# In ra HTML để kiểm tra
print(driver.page_source)

# Đừng quên đóng trình duyệt
driver.quit()
