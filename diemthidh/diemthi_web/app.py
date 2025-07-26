# ==============================================================================
# PHẦN 1: IMPORT THƯ VIỆN VÀ KHAI BÁO ỨNG DỤNG
# ==============================================================================
from flask import Flask, render_template, request, jsonify
import pandas as pd
import numpy as np
import time

app = Flask(__name__)

# ==============================================================================
# PHẦN 2: TẢI DỮ LIỆU VÀ ĐỊNH NGHĨA CÁC HẰNG SỐ
# ==============================================================================

# Định nghĩa các tổ hợp môn
TỔ_HỢP_XÉT_TUYỂN = {
    "A00": ["Toán", "Vật lí", "Hóa học"], "A01": ["Toán", "Vật lí", "Tiếng Anh"], "B00": ["Toán", "Hóa học", "Sinh học"],
    "C00": ["Ngữ văn", "Lịch sử", "Địa lí"], "C01": ["Ngữ văn", "Toán", "Vật lí"], "D01": ["Ngữ văn", "Toán", "Tiếng Anh"],
    "D07": ["Toán", "Hóa học", "Tiếng Anh"],
}

# Tải dữ liệu
try:
    df_diem_thi = pd.read_excel("Điểm thi chung.xlsx", sheet_name="Sheet", dtype={'Số báo danh': str})
    df_quy_doi = pd.read_csv("quy_doi_diem.csv")
except FileNotFoundError as e:
    print(f"LỖI: Không tìm thấy file {e.filename}. Vui lòng kiểm tra lại.")
    df_diem_thi = pd.DataFrame()
    df_quy_doi = pd.DataFrame()

# Biến cache
analytics_cache = {"data": None, "timestamp": 0}
top_students_cache = {"data": None, "timestamp": 0}

# ==============================================================================
# PHẦN 3: CÁC HÀM XỬ LÝ LOGIC
# ==============================================================================

def tinh_diem_to_hop_cho_df(df):
    """Tính điểm tất cả các tổ hợp cho toàn bộ DataFrame."""
    df_result = df.copy()
    for combo, subjects in TỔ_HỢP_XÉT_TUYỂN.items():
        # Kiểm tra xem các cột môn học có tồn tại không
        if all(sub in df_result.columns for sub in subjects):
            # Chuyển đổi các cột sang dạng số, lỗi sẽ thành NaN
            numeric_subjects = df_result[subjects].apply(pd.to_numeric, errors='coerce')
            # Chỉ tính tổng cho các hàng không có NaN
            df_result[combo] = numeric_subjects.sum(axis=1).round(2)
    return df_result

def tra_cuu_diem_tuong_duong(ma_to_hop_goc, diem_goc):
    """Tra cứu điểm tương đương từ bảng quy đổi."""
    if df_quy_doi.empty or ma_to_hop_goc not in df_quy_doi.columns:
        return None
    closest_row_index = (df_quy_doi[ma_to_hop_goc] - diem_goc).abs().idxmin()
    return df_quy_doi.loc[closest_row_index].to_dict()

# Thay thế hàm analyze_dataset trong file app.py

def analyze_dataset():
    """Thực hiện các phân tích trên toàn bộ dữ liệu điểm thi."""
    global analytics_cache
    current_time = time.time()
    
    if analytics_cache["data"] and (current_time - analytics_cache["timestamp"] < 3600):
        print("Sử dụng dữ liệu phân tích từ cache."); return analytics_cache["data"]

    print("Tính toán dữ liệu phân tích mới...")
    if df_diem_thi.empty: return {}

    subject_cols = [col for col in df_diem_thi.columns if df_diem_thi[col].dtype in ['float64', 'int64']]
    
    # 1. Các phân tích cũ (giữ nguyên)
    perfect_scores = {col: int((df_diem_thi[col] == 10).sum()) for col in subject_cols if (df_diem_thi[col] == 10).sum() > 0}
    sorted_perfect_scores = dict(sorted(perfect_scores.items(), key=lambda item: item[1], reverse=True))

    all_distributions = {}
    for subject in subject_cols:
        if not df_diem_thi[subject].dropna().empty:
            dist = pd.cut(df_diem_thi[subject], bins=np.arange(0, 11, 1), right=False).value_counts().sort_index()
            all_distributions[subject] = {"labels": [str(i) for i in dist.index], "data": [int(v) for v in dist.values]}
            
    average_scores = df_diem_thi[subject_cols].mean().round(2).to_dict()
    sorted_average_scores = dict(sorted(average_scores.items(), key=lambda item: item[1], reverse=True))
    
    family_name_data, first_name_data = {}, {}
    if 'Họ' in df_diem_thi.columns:
        top_10 = df_diem_thi['Họ'].dropna().value_counts().head(10)
        family_name_data = {"labels": list(top_10.index), "data": [int(v) for v in top_10.values]}

    if 'Tên' in df_diem_thi.columns:
        top_10 = df_diem_thi['Tên'].dropna().value_counts().head(10)
        first_name_data = {"labels": list(top_10.index), "data": [int(v) for v in top_10.values]}

    # 2. PHÂN TÍCH THEO NGÀY VÀ THÁNG SINH (ĐÃ CẬP NHẬT LOGIC)
    birth_month_data, birth_day_data = {}, {}
    if 'Ngày sinh' in df_diem_thi.columns:
        temp_df = df_diem_thi.copy()
        temp_df['datetime_ngaysinh'] = pd.to_datetime(temp_df['Ngày sinh'], dayfirst=True, errors='coerce')
        temp_df.dropna(subset=['datetime_ngaysinh'], inplace=True)
        
        # Bỏ dòng tính điểm trung bình, không cần thiết nữa
        # temp_df['DiemTBChung'] = temp_df[subject_cols].mean(axis=1)

        # Phân tích theo Tháng sinh
        # THAY ĐỔI: Dùng .size() để đếm số lượng thí sinh thay vì .mean()
        by_month = temp_df.groupby(temp_df['datetime_ngaysinh'].dt.month).size()
        by_month = by_month.sort_index()
        birth_month_data = {
            "labels": [f"Tháng {i}" for i in by_month.index],
            "data": [int(v) for v in by_month.values] # Dữ liệu bây giờ là số lượng (int)
        }
        
        # Phân tích theo Ngày sinh
        # THAY ĐỔI: Dùng .size() để đếm số lượng thí sinh thay vì .mean()
        by_day = temp_df.groupby(temp_df['datetime_ngaysinh'].dt.day).size()
        by_day = by_day.sort_index()
        birth_day_data = {
            "labels": [str(i) for i in by_day.index],
            "data": [int(v) for v in by_day.values] # Dữ liệu bây giờ là số lượng (int)
        }

    # 3. Gom tất cả kết quả phân tích
    analysis_results = {
        "perfect_scores": {"labels": list(sorted_perfect_scores.keys()), "data": [int(v) for v in sorted_perfect_scores.values()]},
        "score_distributions": all_distributions,
        "average_scores": {"labels": list(sorted_average_scores.keys()), "data": [float(v) for v in sorted_average_scores.values()]},
        "family_name_distribution": family_name_data,
        "first_name_distribution": first_name_data,
        "birth_month_analysis": birth_month_data,
        "birth_day_analysis": birth_day_data
    }
    
    analytics_cache["data"] = analysis_results
    analytics_cache["timestamp"] = current_time
    return analysis_results

def calculate_all_top_students():
    """Tính toán và cache danh sách top 10 thí sinh cho TẤT CẢ các khối."""
    global top_students_cache
    current_time = time.time()
    if top_students_cache["data"] and (current_time - top_students_cache["timestamp"] < 3600):
        print("Sử dụng dữ liệu top thí sinh từ cache."); return top_students_cache["data"]

    print("Tính toán dữ liệu top thí sinh mới...")
    if df_diem_thi.empty: return {}

    required_cols = ['Số báo danh']
    has_full_name_col = 'Họ và tên' in df_diem_thi.columns
    has_separate_name_cols = all(col in df_diem_thi.columns for col in ['Họ', 'Tên'])

    if has_full_name_col:
        required_cols.append('Họ và tên')
    elif has_separate_name_cols:
        required_cols.extend(['Họ', 'Tên'])
    else:
        print("CẢNH BÁO: Thiếu cột tên để tính top thí sinh.")
        return {}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    
    all_tops = {}
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            if has_full_name_col:
                df_with_scores['HoTen'] = df_with_scores['Họ và tên']
            else:
                df_with_scores['HoTen'] = df_with_scores['Họ'] + ' ' + df_with_scores['Tên']
            top_10 = df_with_scores.sort_values(by=combo, ascending=False).head(10)
            all_tops[combo] = top_10[['Số báo danh', 'HoTen', combo]].rename(columns={combo: 'TongDiem'}).to_dict('records')

    top_students_cache["data"] = all_tops
    top_students_cache["timestamp"] = current_time
    return all_tops

# ==============================================================================
# PHẦN 4: CÁC ROUTE CỦA FLASK
# ==============================================================================

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", TỔ_HỢP=TỔ_HỢP_XÉT_TUYỂN)

@app.route("/tra-cuu", methods=["POST"])
def tra_cuu():
    sbd = request.form.get("sbd")
    if not sbd or df_diem_thi.empty:
        return jsonify({"error": "Dữ liệu không hợp lệ."}), 400

    result_df = df_diem_thi.loc[df_diem_thi["Số báo danh"] == sbd.strip()]
    if result_df.empty:
        return jsonify({"error": f"Không tìm thấy SBD '{sbd}'."}), 404

    df_with_scores = tinh_diem_to_hop_cho_df(result_df)
    student_data_row = df_with_scores.iloc[0]
    
    diem_to_hop = {combo: student_data_row[combo] for combo in TỔ_HỢP_XÉT_TUYỂN.keys() if combo in student_data_row and pd.notna(student_data_row[combo])}
    
    diem_cac_mon = result_df.dropna(axis=1).to_html(classes='table table-bordered', index=False, border=0)
    
    return jsonify({"diem_cac_mon_html": diem_cac_mon, "diem_to_hop": diem_to_hop})

@app.route("/quy-doi", methods=["POST"])
def quy_doi():
    ma_to_hop_goc = request.form.get("ma_to_hop")
    diem_goc_str = request.form.get("diem")
    try:
        diem_goc = float(diem_goc_str)
    except (ValueError, TypeError):
        return jsonify({"error": "Điểm không hợp lệ."}), 400
    ket_qua_quy_doi = tra_cuu_diem_tuong_duong(ma_to_hop_goc, diem_goc)
    if not ket_qua_quy_doi: return jsonify({"error": "Không thể thực hiện quy đổi."}), 500
    return jsonify(ket_qua_quy_doi)

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")

@app.route("/analytics-data")
def analytics_data():
    data = analyze_dataset()
    return jsonify(data)

@app.route("/top-students-all")
def top_students_all():
    data = calculate_all_top_students()
    return jsonify(data)

# ==============================================================================
# PHẦN 5: CHẠY ỨNG DỤNG
# ==============================================================================

if __name__ == "__main__":
    app.run(debug=True)