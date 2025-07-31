# ==============================================================================
# PHẦN 1: IMPORT THƯ VIỆN VÀ KHAI BÁO ỨNG DỤNG
# ==============================================================================
from flask import Flask, render_template, request, jsonify
import pandas as pd
import numpy as np
import time
import json

app = Flask(__name__)

# Custom JSON encoder để xử lý NaN values
class NaNEncoder(json.JSONEncoder):
    def encode(self, obj):
        if isinstance(obj, float) and np.isnan(obj):
            return "null"
        return super().encode(obj)

app.json_encoder = NaNEncoder

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
    """
    Tính điểm tất cả các tổ hợp cho toàn bộ DataFrame.
    Chỉ tính tổng khi thí sinh có đủ điểm ở CẢ BA môn của tổ hợp.
    """
    df_result = df.copy()
    for combo, subjects in TỔ_HỢP_XÉT_TUYỂN.items():
        # Kiểm tra xem các cột môn học có tồn tại không
        if all(sub in df_result.columns for sub in subjects):
            # Tạo một DataFrame tạm chỉ chứa điểm các môn của khối
            combo_df = df_result[subjects].apply(pd.to_numeric, errors='coerce')
            
            # --- LOGIC MỚI QUAN TRỌNG ---
            # Dùng .dropna() để loại bỏ tất cả các hàng có ít nhất một môn bị thiếu điểm (NaN)
            # Sau đó mới tính tổng trên các hàng hợp lệ đó.
            valid_scores = combo_df.dropna()
            
            # Tính tổng và gán lại vào DataFrame kết quả
            # Các hàng bị drop sẽ có giá trị NaN trong cột tổng điểm này
            df_result[combo] = valid_scores.sum(axis=1).round(2)
            
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
            
    # Tính điểm trung bình và xử lý NaN
    average_scores = df_diem_thi[subject_cols].mean().round(2)
    # Thay thế NaN bằng 0
    average_scores = average_scores.fillna(0).to_dict()
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
        "birth_day_analysis": birth_day_data,
        
        # Thêm dữ liệu mới cho dashboard
        "combo_averages": analyze_combo_averages(),
        "combo_counts": analyze_combo_counts(),
        "combo_distributions": analyze_combo_distributions(),
        "top10_percentages": analyze_top10_percentages(),
        "high_scores_distribution": analyze_high_scores_distribution(),
        "combo_ranking": analyze_combo_ranking()
        # Bỏ raw_data vì quá lớn và gây lỗi NaN
    }
    
    analytics_cache["data"] = analysis_results
    analytics_cache["timestamp"] = current_time
    return analysis_results

def analyze_combo_averages():
    """Phân tích điểm trung bình của từng khối thi."""
    if df_diem_thi.empty:
        return {"labels": [], "data": []}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    combo_averages = {}
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            avg_score = df_with_scores[combo].dropna().mean()
            if not pd.isna(avg_score):
                combo_averages[combo] = round(avg_score, 2)
    
    sorted_averages = dict(sorted(combo_averages.items(), key=lambda x: x[1], reverse=True))
    return {"labels": list(sorted_averages.keys()), "data": list(sorted_averages.values())}

def analyze_combo_counts():
    """Phân tích số lượng thí sinh theo từng khối."""
    if df_diem_thi.empty:
        return {"labels": [], "data": []}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    combo_counts = {}
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            count = df_with_scores[combo].dropna().count()
            combo_counts[combo] = int(count)
    
    return {"labels": list(combo_counts.keys()), "data": list(combo_counts.values())}

def analyze_combo_distributions():
    """Phân tích phân phối điểm của từng khối."""
    if df_diem_thi.empty:
        return {}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    distributions = {}
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            scores = df_with_scores[combo].dropna()
            if len(scores) > 0:
                # Tạo bins từ 0 đến 30 với bước 2
                bins = np.arange(0, 31, 2)
                hist, _ = np.histogram(scores, bins=bins)
                labels = [f"{i}-{i+2}" for i in bins[:-1]]
                distributions[combo] = {
                    "labels": labels,
                    "data": [int(x) for x in hist]
                }
    
    return distributions

def analyze_top10_percentages():
    """Phân tích tỷ lệ thí sinh đạt top 10% mỗi khối."""
    if df_diem_thi.empty:
        return {"labels": [], "data": []}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    top10_data = {}
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            scores = df_with_scores[combo].dropna()
            if len(scores) > 0:
                top10_threshold = scores.quantile(0.9)  # Top 10%
                top10_count = (scores >= top10_threshold).sum()
                top10_data[combo] = int(top10_count)
    
    return {"labels": list(top10_data.keys()), "data": list(top10_data.values())}

def analyze_high_scores_distribution():
    """Phân tích số lượng thí sinh đạt điểm cao (>27) theo khối."""
    if df_diem_thi.empty:
        return {"labels": [], "data": []}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    high_scores = {}
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            scores = df_with_scores[combo].dropna()
            high_count = (scores > 27).sum()
            high_scores[combo] = int(high_count)
    
    sorted_high = dict(sorted(high_scores.items(), key=lambda x: x[1], reverse=True))
    return {"labels": list(sorted_high.keys()), "data": list(sorted_high.values())}

def analyze_combo_ranking():
    """Tạo bảng xếp hạng các khối thi."""
    if df_diem_thi.empty:
        return []
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    ranking_data = []
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            scores = df_with_scores[combo].dropna()
            if len(scores) > 0:
                avg_score = round(scores.mean(), 2)
                max_score = round(scores.max(), 2)
                student_count = len(scores)
                high_score_count = (scores > 25).sum()
                high_score_percentage = round((high_score_count / student_count) * 100, 1)
                
                ranking_data.append({
                    'combo': combo,
                    'subjects': ', '.join(TỔ_HỢP_XÉT_TUYỂN[combo]),
                    'average_score': avg_score,
                    'max_score': max_score,
                    'student_count': student_count,
                    'high_score_percentage': high_score_percentage
                })
    
    # Sắp xếp theo điểm trung bình
    ranking_data.sort(key=lambda x: x['average_score'], reverse=True)
    return ranking_data

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

def tinh_ranking_hoc_sinh(diem_to_hop):
    """
    Tính ranking của học sinh theo từng khối dựa trên điểm tổ hợp.
    Trả về dictionary chứa thông tin ranking cho từng khối.
    """
    if df_diem_thi.empty or not diem_to_hop:
        return {}
    
    # Tính điểm tổ hợp cho toàn bộ dữ liệu
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    
    ranking_info = {}
    
    for combo, diem_hoc_sinh in diem_to_hop.items():
        if combo in df_with_scores.columns and pd.notna(diem_hoc_sinh):
            # Lọc các thí sinh có điểm hợp lệ trong khối này
            valid_scores = df_with_scores[combo].dropna()
            
            if len(valid_scores) > 0:
                # Tính số thí sinh có điểm cao hơn
                so_nguoi_cao_hon = (valid_scores > diem_hoc_sinh).sum()
                
                # Tính số thí sinh có điểm bằng nhau
                so_nguoi_bang_nhau = (valid_scores == diem_hoc_sinh).sum()
                
                # Ranking = số người cao hơn + 1
                ranking = so_nguoi_cao_hon + 1
                
                # Tổng số thí sinh tham gia khối này
                tong_so_thi_sinh = len(valid_scores)
                
                # Tính phần trăm
                phan_tram = round((ranking / tong_so_thi_sinh) * 100, 2)
                
                ranking_info[combo] = {
                    'ranking': int(ranking),
                    'tong_so_thi_sinh': int(tong_so_thi_sinh),
                    'so_nguoi_cao_hon': int(so_nguoi_cao_hon),
                    'so_nguoi_bang_nhau': int(so_nguoi_bang_nhau),
                    'phan_tram': phan_tram,
                    'diem': float(diem_hoc_sinh)
                }
    
    return ranking_info

def analyze_combo_averages():
    """Phân tích điểm trung bình của từng khối thi."""
    if df_diem_thi.empty:
        return {"labels": [], "data": []}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    combo_averages = {}
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            avg_score = df_with_scores[combo].dropna().mean()
            if not pd.isna(avg_score):
                combo_averages[combo] = round(avg_score, 2)
    
    sorted_averages = dict(sorted(combo_averages.items(), key=lambda x: x[1], reverse=True))
    return {"labels": list(sorted_averages.keys()), "data": list(sorted_averages.values())}

def analyze_combo_counts():
    """Phân tích số lượng thí sinh theo từng khối."""
    if df_diem_thi.empty:
        return {"labels": [], "data": []}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    combo_counts = {}
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            count = df_with_scores[combo].dropna().count()
            combo_counts[combo] = int(count)
    
    return {"labels": list(combo_counts.keys()), "data": list(combo_counts.values())}

def analyze_combo_distributions():
    """Phân tích phân phối điểm của từng khối."""
    if df_diem_thi.empty:
        return {}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    distributions = {}
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            scores = df_with_scores[combo].dropna()
            if len(scores) > 0:
                # Tạo bins từ 0 đến 30 với bước 2
                bins = np.arange(0, 31, 2)
                hist, _ = np.histogram(scores, bins=bins)
                labels = [f"{i}-{i+2}" for i in bins[:-1]]
                distributions[combo] = {
                    "labels": labels,
                    "data": [int(x) for x in hist]
                }
    
    return distributions

def analyze_top10_percentages():
    """Phân tích tỷ lệ thí sinh đạt top 10% mỗi khối."""
    if df_diem_thi.empty:
        return {"labels": [], "data": []}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    top10_data = {}
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            scores = df_with_scores[combo].dropna()
            if len(scores) > 0:
                top10_threshold = scores.quantile(0.9)  # Top 10%
                top10_count = (scores >= top10_threshold).sum()
                top10_data[combo] = int(top10_count)
    
    return {"labels": list(top10_data.keys()), "data": list(top10_data.values())}

def analyze_high_scores_distribution():
    """Phân tích số lượng thí sinh đạt điểm cao (>27) theo khối."""
    if df_diem_thi.empty:
        return {"labels": [], "data": []}
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    high_scores = {}
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            scores = df_with_scores[combo].dropna()
            high_count = (scores > 27).sum()
            high_scores[combo] = int(high_count)
    
    sorted_high = dict(sorted(high_scores.items(), key=lambda x: x[1], reverse=True))
    return {"labels": list(sorted_high.keys()), "data": list(sorted_high.values())}

def analyze_combo_ranking():
    """Tạo bảng xếp hạng các khối thi."""
    if df_diem_thi.empty:
        return []
    
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    ranking_data = []
    
    for combo in TỔ_HỢP_XÉT_TUYỂN.keys():
        if combo in df_with_scores.columns:
            scores = df_with_scores[combo].dropna()
            if len(scores) > 0:
                avg_score = round(scores.mean(), 2)
                max_score = round(scores.max(), 2)
                student_count = len(scores)
                high_score_count = (scores > 25).sum()
                high_score_percentage = round((high_score_count / student_count) * 100, 1)
                
                ranking_data.append({
                    'combo': combo,
                    'subjects': ', '.join(TỔ_HỢP_XÉT_TUYỂN[combo]),
                    'average_score': avg_score,
                    'max_score': max_score,
                    'student_count': student_count,
                    'high_score_percentage': high_score_percentage
                })
    
    # Sắp xếp theo điểm trung bình
    ranking_data.sort(key=lambda x: x['average_score'], reverse=True)
    return ranking_data

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
    
    # Tính ranking cho học sinh
    ranking_info = tinh_ranking_hoc_sinh(diem_to_hop)
    
    diem_cac_mon = result_df.dropna(axis=1).to_html(classes='table table-bordered', index=False, border=0)
    
    return jsonify({
        "diem_cac_mon_html": diem_cac_mon, 
        "diem_to_hop": diem_to_hop,
        "ranking_info": ranking_info
    })

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

@app.route("/test-debug")
def test_debug():
    return render_template("test-debug.html")

@app.route("/analytics-data")
def analytics_data():
    data = analyze_dataset()
    return jsonify(data)

@app.route("/top-students-all")
def top_students_all():
    data = calculate_all_top_students()
    return jsonify(data)

@app.route("/estimate-ranking", methods=["POST"])
def estimate_ranking():
    """Ước tính ranking cho một điểm cụ thể của một tổ hợp."""
    ma_to_hop = request.form.get("ma_to_hop")
    diem_str = request.form.get("diem")
    
    try:
        diem = float(diem_str)
    except (ValueError, TypeError):
        return jsonify({"error": "Điểm không hợp lệ."}), 400
    
    if df_diem_thi.empty or ma_to_hop not in TỔ_HỢP_XÉT_TUYỂN:
        return jsonify({"error": "Dữ liệu không hợp lệ."}), 400
    
    # Tính điểm tổ hợp cho toàn bộ dữ liệu
    df_with_scores = tinh_diem_to_hop_cho_df(df_diem_thi)
    
    if ma_to_hop not in df_with_scores.columns:
        return jsonify({"error": "Khối không tồn tại."}), 400
    
    # Lọc các thí sinh có điểm hợp lệ trong khối này
    valid_scores = df_with_scores[ma_to_hop].dropna()
    
    if len(valid_scores) == 0:
        return jsonify({"error": "Không có dữ liệu cho khối này."}), 400
    
    # Tính ranking
    so_nguoi_cao_hon = (valid_scores > diem).sum()
    so_nguoi_bang_nhau = (valid_scores == diem).sum()
    ranking = so_nguoi_cao_hon + 1
    tong_so_thi_sinh = len(valid_scores)
    phan_tram = round((ranking / tong_so_thi_sinh) * 100, 2)
    
    return jsonify({
        'ranking': int(ranking),
        'tong_so_thi_sinh': int(tong_so_thi_sinh),
        'so_nguoi_cao_hon': int(so_nguoi_cao_hon),
        'so_nguoi_bang_nhau': int(so_nguoi_bang_nhau),
        'phan_tram': phan_tram,
        'diem': float(diem)
    })

# ==============================================================================
# PHẦN 5: CHẠY ỨNG DỤNG
# ==============================================================================

if __name__ == "__main__":
    app.run(debug=True)