from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
from openpyxl import Workbook
import multiprocessing as mp
from multiprocessing import Pool, Manager, Lock
import time
import os
from datetime import datetime

def setup_driver():
    """Thiết lập driver Chrome"""
    options = Options()
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    # options.add_argument("--headless")  # Bỏ comment nếu muốn chạy ẩn
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    
    driver = webdriver.Chrome(options=options)
    return driver

def crawl_batch(args):
    """Hàm crawl một batch số báo danh"""
    sbd_list, process_id, shared_data, lock = args
    
    # Thiết lập driver riêng cho mỗi process
    driver = setup_driver()
    wait = WebDriverWait(driver, 5)
    
    # Tạo workbook riêng cho process
    wb = Workbook()
    ws = wb.active
    tieu_de = ["Số báo danh", "Họ tên", "Ngày sinh"]
    ws.append(tieu_de)
    cac_mon = []
    record_count = 0
    
    print(f"🚀 Process {process_id} bắt đầu với {len(sbd_list)} SBD")
    
    try:
        driver.get("https://diemthi.hcm.edu.vn/")
        
        for i, sbd in enumerate(sbd_list):
            try:
                # Nhập SBD
                sbd_input = wait.until(EC.presence_of_element_located((By.ID, "SoBaoDanh")))
                sbd_input.clear()
                sbd_input.send_keys(sbd)

                # Bấm nút tìm
                submit_btn = driver.find_element(By.CLASS_NAME, "g-recaptcha")
                submit_btn.click()

                # Đợi kết quả
                try:
                    WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, "//table//tr[2]")))
                except:
                    print(f"⏭️ P{process_id}-{sbd}: Không có kết quả")
                    driver.get("https://diemthi.hcm.edu.vn/")
                    continue

                # Lấy dữ liệu
                rows = driver.find_elements(By.XPATH, "//table//tr")
                if len(rows) < 2:
                    print(f"P{process_id}-{sbd}: Không có dữ liệu")
                    driver.get("https://diemthi.hcm.edu.vn/")
                    continue

                cols = rows[1].find_elements(By.TAG_NAME, "td")
                if len(cols) < 3:
                    print(f"P{process_id}-{sbd}: Không đủ cột")
                    driver.get("https://diemthi.hcm.edu.vn/")
                    continue

                ho_ten = cols[0].text.strip()
                ngay_sinh = cols[1].text.strip()
                ket_qua = cols[2].text.strip()

                # Phân tích điểm
                matches = re.findall(r'([A-Za-zÀ-Ỹà-ỹ\s]+):\s*([\d.]+)', ket_qua)
                diem_dict = {mon.strip(): diem for mon, diem in matches}

                # Cập nhật tiêu đề môn học
                for mon in diem_dict:
                    if mon not in cac_mon:
                        cac_mon.append(mon)
                        col_index = len(tieu_de) + cac_mon.index(mon) + 1
                        ws.cell(row=1, column=col_index, value=mon)

                # Ghi dữ liệu
                row_data = [sbd, ho_ten, ngay_sinh]
                for mon in cac_mon:
                    row_data.append(diem_dict.get(mon, ""))

                ws.append(row_data)
                record_count += 1

                print(f"✅ P{process_id}-{sbd}: {ho_ten} - {len(diem_dict)} môn")

                # Cập nhật progress vào shared data
                with lock:
                    shared_data['completed'] += 1
                    if shared_data['completed'] % 50 == 0:
                        print(f"📊 Tổng tiến độ: {shared_data['completed']}/{shared_data['total']}")

                # Nghỉ ngắn để tránh spam
                time.sleep(0.5)
                driver.get("https://diemthi.hcm.edu.vn/")

            except Exception as e:
                print(f"❌ P{process_id}-{sbd}: Lỗi - {e}")
                driver.get("https://diemthi.hcm.edu.vn/")
                time.sleep(1)

    except Exception as e:
        print(f"❌ Process {process_id} gặp lỗi nghiêm trọng: {e}")
    
    finally:
        # Lưu file cho process này
        if record_count > 0:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"diem_process_{process_id}_{timestamp}.xlsx"
            wb.save(file_name)
            print(f"💾 Process {process_id} đã lưu {file_name} với {record_count} bản ghi")
        
        driver.quit()
        return record_count

def split_list(lst, n):
    """Chia list thành n phần bằng nhau"""
    k, m = divmod(len(lst), n)
    return [lst[i*k+min(i, m):(i+1)*k+min(i+1, m)] for i in range(n)]

def main():
    # Cấu hình
    START_NUM = 95000
    END_NUM = 98499
    NUM_PROCESSES = 2  # Số tiến trình song song
    
    print(f"🔧 Cấu hình: {NUM_PROCESSES} tiến trình, SBD từ 02{START_NUM:06d} đến 02{END_NUM:06d}")
    
    # Tạo danh sách SBD
    ds_sbd = [f"02{str(i).zfill(6)}" for i in range(START_NUM, END_NUM)]
    
    # Chia SBD thành các batch cho mỗi process
    sbd_batches = split_list(ds_sbd, NUM_PROCESSES)
    
    # Shared data để theo dõi tiến độ
    manager = Manager()
    shared_data = manager.dict()
    shared_data['completed'] = 0
    shared_data['total'] = len(ds_sbd)
    lock = manager.Lock()
    
    # Chuẩn bị arguments cho mỗi process
    process_args = []
    for i, batch in enumerate(sbd_batches):
        process_args.append((batch, i+1, shared_data, lock))
    
    print(f"📋 Chia thành {len(sbd_batches)} batch:")
    for i, batch in enumerate(sbd_batches):
        print(f"   Process {i+1}: {len(batch)} SBD ({batch[0]} -> {batch[-1]})")
    
    # Chạy đa tiến trình
    start_time = time.time()
    
    with Pool(processes=NUM_PROCESSES) as pool:
        results = pool.map(crawl_batch, process_args)
    
    end_time = time.time()
    
    # Tổng kết
    total_records = sum(results)
    duration = end_time - start_time
    
    print(f"""
    ✅ HOÀN THÀNH!
    ⏰ Thời gian: {duration:.2f} giây ({duration/60:.2f} phút)
    📊 Tổng bản ghi: {total_records}
    🚀 Tốc độ trung bình: {total_records/duration:.2f} bản ghi/giây
    """)

if __name__ == "__main__":
    # Kiểm tra hỗ trợ multiprocessing
    mp.set_start_method('spawn', force=True)  # Quan trọng trên Windows
    main()