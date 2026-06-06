"""
ml_engine.py — Mesin Machine Learning untuk Rekomendasi Anggaran Cerdas
=========================================================================
Pipeline:
  1. Load CSV → filter EXPENSE → agregasi bulanan per kategori
  2. K-Means Clustering → 3 profil gaya hidup (Hemat / Standar / Konsumtif)
  3. Fungsi recommend() → menerima income + profil keluarga lengkap
     → menghasilkan alokasi 50/30/20 yang disesuaikan secara dinamis
     → rincian Needs & Wants per-item berdasarkan data historis
"""

import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
import os
import google.generativeai as genai

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Memoles kalimat bahasa Indonesia agar terdengar luwes, santai, dan profesional menggunakan Gemini AI
def refine_sentence_with_gemini(text: str, context_prompt: str) -> str:
    if not GEMINI_API_KEY:
        return text
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = (
            "Ubah kalimat rekomendasi keuangan berikut menjadi sangat ramah, luwes, "
            "suportif, memotivasi, dan tidak kaku dalam bahasa Indonesia informal yang "
            "biasa digunakan perencana keuangan profesional yang akrab (seperti financial coach). "
            "Tetap pertahankan semua fakta angka, nominal rupiah, dan informasi penting lainnya.\n\n"
            f"Konteks: {context_prompt}\n"
            f"Kalimat asli: {text}\n\n"
            "Kalimat yang dipoles:"
        )
        response = model.generate_content(prompt)
        refined_text = response.text.strip()
        return refined_text if refined_text else text
    except Exception as e:
        print(f"[WARN] Gagal memoles dengan Gemini: {e}")
        return text

REQUIRED_COLUMNS = {"Date", "Title", "Amount", "Type", "Category"}
WANTS_CATEGORIES = ["Makan & Minum", "Hiburan", "Perawatan Diri", "Pakaian & Fashion", "Donasi & Amal"]
NEEDS_CATEGORIES = ["Tagihan", "Belanja Rumah Tangga", "Transportasi", "Kesehatan", "Edukasi"]
WANTS_MAPPING = {
    "Makan & Minum": {"icon": "hamburger", "color": "orange", "weight": 0.30},
    "Hiburan": {"icon": "film", "color": "purple", "weight": 0.22},
    "Pakaian & Fashion": {"icon": "tshirt", "color": "pink", "weight": 0.18},
    "Perawatan Diri": {"icon": "spa", "color": "amber", "weight": 0.15},
    "Donasi & Amal": {"icon": "hand-holding-heart", "color": "blue", "weight": 0.15},
}

# ============================================================
# KONSTANTA ESTIMASI BIAYA HIDUP (dalam Rupiah per bulan)
# Digunakan sebagai fallback jika data historis tidak tersedia
# ============================================================
COST_DEFAULTS = {
    # Makan per orang per bulan — mahasiswa rata-rata Rp 15.000/makan × 3x/hari
    "makan_per_orang": 450_000,
    # Biaya sekolah anak rata-rata
    "sekolah_per_anak": 500_000,
    # Biaya susu/pampers/kebutuhan balita
    "balita_per_anak": 400_000,
    # Bensin motor per bulan — mahasiswa rata-rata
    "bensin_motor": 150_000,
    # Bensin mobil per bulan
    "bensin_mobil": 500_000,
    # Listrik — kos biasanya sudah termasuk atau ringan
    "listrik_base": 100_000,
    "listrik_per_orang": 30_000,
    # Air PDAM
    "air_base": 50_000,
    "air_per_orang": 15_000,
    # Paket data / internet kos
    "internet": 100_000,
    # Kos/Kontrakan rata-rata mahasiswa
    "sewa_kos": 500_000,
    "sewa_kontrakan": 800_000,
    # Cicilan rumah rata-rata
    "cicilan_rumah": 2_000_000,
}


class BudgetRecommender:
    """
    Kelas utama yang mengelola training model ML dan inferensi rekomendasi.
    """

    def __init__(self, data_path="Data_Finance_6_Bulan.csv"):
        self.data_path = data_path
        self.profiles = ["Hemat", "Standar", "Konsumtif"]
        self.model_trained = False
        self.historical_costs = {}       # rata-rata biaya per Title
        self.historical_freq = {}        # rata-rata frekuensi per Title per bulan
        self.category_avg_monthly = {}   # rata-rata pengeluaran bulanan per Category
        self.category_avg_transaction = {}
        self.cluster_breakdown = None
        self.profile_mapping = {}
        self.cluster_category_avg_transaction = {}
        self.training_status = "not_started"
        self.training_message = "Model belum dilatih."
        self.train_model()

    # ============================================================
    # TRAINING: Preprocessing CSV + K-Means Clustering
    # ============================================================
    # Melatih model pengelompokan (K-Means) dari data transaksi historis di CSV
    def train_model(self):
        if not os.path.exists(self.data_path):
            self.training_status = "fallback"
            self.training_message = f"{self.data_path} tidak ditemukan. Mode fallback aktif."
            print(f"[WARN] {self.training_message}")
            return

        try:
            df = pd.read_csv(self.data_path)
            missing_columns = REQUIRED_COLUMNS - set(df.columns)
            if missing_columns:
                self.training_status = "fallback"
                self.training_message = (
                    "CSV tidak valid. Kolom hilang: " + ", ".join(sorted(missing_columns))
                )
                print(f"[WARN] {self.training_message}")
                return

            df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date", "Amount", "Type", "Category", "Title"])

            # --- 1. Filter hanya EXPENSE ---
            df_exp = df[df["Type"] == "EXPENSE"].copy()
            if df_exp.empty:
                self.training_status = "fallback"
                self.training_message = "Tidak ada data EXPENSE valid di CSV. Mode fallback aktif."
                print(f"[WARN] {self.training_message}")
                return

            df_exp["YearMonth"] = df_exp["Date"].dt.to_period("M")

            # --- 2. Rata-rata biaya per Title (untuk Actionable Insight) ---
            self.historical_costs = df_exp.groupby("Title")["Amount"].mean().to_dict()

            # --- 3. Frekuensi rata-rata per Title per bulan ---
            title_monthly_count = (
                df_exp.groupby(["YearMonth", "Title"]).size().reset_index(name="count")
            )
            self.historical_freq = (
                title_monthly_count.groupby("Title")["count"].mean().to_dict()
            )

            # --- 4. Rata-rata pengeluaran bulanan per Category ---
            cat_monthly = (
                df_exp.groupby(["YearMonth", "Category"])["Amount"]
                .sum()
                .reset_index()
            )
            self.category_avg_monthly = (
                cat_monthly.groupby("Category")["Amount"].mean().to_dict()
            )
            self.category_avg_transaction = (
                df_exp.groupby("Category")["Amount"].mean().to_dict()
            )

            # --- 5. Pivot mingguan untuk K-Means ---
            df_exp["Week"] = df_exp["Date"].dt.isocalendar().week
            weekly_spend = (
                df_exp.pivot_table(
                    index="Week", columns="Category", values="Amount", aggfunc="sum"
                )
                .fillna(0)
            )

            # Augmentasi data jika terlalu sedikit untuk clustering
            if len(weekly_spend) < 10:
                rng = np.random.default_rng(42)
                synthetic = []
                for _ in range(20):
                    noise = rng.normal(1, 0.05, weekly_spend.shape)
                    synthetic.append(weekly_spend * noise)
                weekly_spend = pd.concat(synthetic)

            wants_cols = [c for c in WANTS_CATEGORIES if c in weekly_spend.columns]
            needs_cols = [c for c in NEEDS_CATEGORIES if c in weekly_spend.columns]

            if not wants_cols and not needs_cols:
                self.training_status = "fallback"
                self.training_message = "Kategori EXPENSE tidak cocok dengan kategori demo. Mode fallback aktif."
                print(f"[WARN] {self.training_message}")
                return

            weekly_spend["Total_Wants"] = weekly_spend[wants_cols].sum(axis=1)
            weekly_spend["Total_Needs"] = weekly_spend[needs_cols].sum(axis=1)
            weekly_spend["Total"] = weekly_spend["Total_Wants"] + weekly_spend["Total_Needs"]
            weekly_spend = weekly_spend[weekly_spend["Total"] > 0]
            if weekly_spend.empty:
                self.training_status = "fallback"
                self.training_message = "Total pengeluaran mingguan kosong. Mode fallback aktif."
                print(f"[WARN] {self.training_message}")
                return

            # Fitur untuk K-Means: proporsi wants & total spend
            X = pd.DataFrame()
            X["Wants_Ratio"] = weekly_spend["Total_Wants"] / weekly_spend["Total"].replace(0, 1)
            X["Total_Spend"] = weekly_spend["Total"]

            # --- 6. K-Means Clustering (3 profil) ---
            kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
            weekly_spend["Cluster"] = kmeans.fit_predict(X)

            # Mapping cluster → profil berdasarkan rata-rata total pengeluaran
            cluster_means = weekly_spend.groupby("Cluster")[
                ["Total_Wants", "Total_Needs", "Total"]
            ].mean()
            sorted_clusters = cluster_means["Total"].sort_values().index.tolist()

            self.profile_mapping = {
                "Hemat": sorted_clusters[0],
                "Standar": sorted_clusters[1],
                "Konsumtif": sorted_clusters[2],
            }

            self.cluster_breakdown = weekly_spend.groupby("Cluster")[
                wants_cols + needs_cols
            ].mean()

            # Mapping transaksi riil ke kluster untuk menghitung rata-rata transaksi per kategori
            real_weekly_spend = (
                df_exp.pivot_table(
                    index="Week", columns="Category", values="Amount", aggfunc="sum"
                )
                .fillna(0)
            )
            real_wants_cols = [c for c in WANTS_CATEGORIES if c in real_weekly_spend.columns]
            real_needs_cols = [c for c in NEEDS_CATEGORIES if c in real_weekly_spend.columns]
            
            real_weekly_spend["Total_Wants"] = real_weekly_spend[real_wants_cols].sum(axis=1)
            real_weekly_spend["Total_Needs"] = real_weekly_spend[real_needs_cols].sum(axis=1)
            real_weekly_spend["Total"] = real_weekly_spend["Total_Wants"] + real_weekly_spend["Total_Needs"]
            real_weekly_spend = real_weekly_spend[real_weekly_spend["Total"] > 0]
            
            real_X = pd.DataFrame()
            real_X["Wants_Ratio"] = real_weekly_spend["Total_Wants"] / real_weekly_spend["Total"].replace(0, 1)
            real_X["Total_Spend"] = real_weekly_spend["Total"]
            
            real_weekly_spend["Cluster"] = kmeans.predict(real_X)
            week_to_cluster = real_weekly_spend["Cluster"].to_dict()
            
            df_exp["Cluster"] = df_exp["Week"].map(week_to_cluster)
            df_exp_mapped = df_exp.dropna(subset=["Cluster"])
            
            cluster_cat_means = df_exp_mapped.groupby(["Cluster", "Category"])["Amount"].mean()
            self.cluster_category_avg_transaction = {
                (int(cluster), str(cat)): int(amount)
                for (cluster, cat), amount in cluster_cat_means.items()
            }

            self.model_trained = True
            self.training_status = "trained"
            self.training_message = "Model K-Means berhasil dilatih dari data demo."
            print(f"[OK] Model K-Means dilatih. Profil mapping: {self.profile_mapping}")
            print(f"[OK] {len(self.historical_costs)} item historis terdeteksi.")

        except Exception as e:
            self.model_trained = False
            self.training_status = "fallback"
            self.training_message = f"Training gagal: {e}. Mode fallback aktif."
            print(f"[ERROR] {self.training_message}")
            import traceback
            traceback.print_exc()

    # ============================================================
    # INFERENCE: Rekomendasi Anggaran Lengkap
    # ============================================================
    # Menghasilkan rekomendasi anggaran dinamis berdasarkan pendapatan dan kondisi keluarga
    def recommend(
        self,
        income: int,
        profile: str,
        user_type: str = "anak_kos",
        city_tier: str = "sedang",
        budget_mode: str = "normal",
        family_size: int = 1,
        num_children: int = 0,
        children_ages: list = None,
        has_vehicle: str = "none",       # "none", "motor", "mobil", "both"
        housing_type: str = "kos",       # "kos", "kontrakan", "rumah_sendiri", "cicilan"
        water_source: str = "pdam",      # "pdam", "sumur"
        fixed_costs: dict = None,
    ):
        """
        Menghasilkan rekomendasi anggaran berdasarkan:
        - income: pendapatan bulanan
        - profile: profil gaya hidup dari ML (Hemat/Standar/Konsumtif)
        - family_size: jumlah anggota keluarga total (termasuk user)
        - num_children: jumlah anak
        - children_ages: list usia anak (untuk estimasi biaya sekolah vs balita)
        - has_vehicle: kepemilikan kendaraan
        - housing_type: tipe tempat tinggal
        - water_source: sumber air (pdam / sumur)
        """

        if children_ages is None:
            children_ages = []
        if fixed_costs is None:
            fixed_costs = {}

        city_multiplier = {"murah": 0.85, "sedang": 1.0, "mahal": 1.25}.get(city_tier, 1.0)
        mode_settings = {
            "normal": {"base_needs": 0.50, "base_wants": 0.30, "base_savings": 0.20, "min_savings": 0.10, "max_needs": 0.85},
            "hemat": {"base_needs": 0.55, "base_wants": 0.20, "base_savings": 0.25, "min_savings": 0.15, "max_needs": 0.85},
            "darurat": {"base_needs": 0.85, "base_wants": 0.05, "base_savings": 0.10, "min_savings": 0.05, "max_needs": 0.90},
            "agresif_menabung": {"base_needs": 0.45, "base_wants": 0.20, "base_savings": 0.35, "min_savings": 0.20, "max_needs": 0.80},
        }
        mode = mode_settings.get(budget_mode, mode_settings["normal"])

        if user_type == "anak_kos":
            housing_type = "kos"
            family_size = 1
            num_children = 0
            children_ages = []

        # -------------------------------------------------------
        # STEP 1: Hitung Needs secara bottom-up dari parameter keluarga
        # -------------------------------------------------------
        needs_detail = {}

        # 1a. MAKAN - berdasarkan jumlah anggota keluarga (dirinci)
        base_makan = int(COST_DEFAULTS["makan_per_orang"] * city_multiplier) * family_size
        profile_food_multiplier = {"Hemat": 0.8, "Standar": 1.0, "Konsumtif": 1.4}
        cost_makan_total = int(base_makan * profile_food_multiplier.get(profile, 1.0))

        if housing_type == "kos":
            daily_food = max(0, cost_makan_total // 30)
            needs_detail["Makan Harian"] = {
                "amount": int(cost_makan_total * 0.85),
                "desc": f"Warung/kantin sekitar Rp {daily_food:,.0f}/hari",
                "icon": "utensils",
            }
            needs_detail["Minum & Camilan"] = {
                "amount": int(cost_makan_total * 0.15),
                "desc": "Air minum, kopi, dan camilan ringan per bulan",
                "icon": "mug-hot",
            }
        else:
            # Breakdown Uang Makan
            needs_detail["Beras & Sembako"] = {
                "amount": int(cost_makan_total * 0.35),
                "desc": "Beras, minyak, telur, dll per bulan",
                "icon": "box-open",
            }
            needs_detail["Lauk & Sayuran"] = {
                "amount": int(cost_makan_total * 0.50),
                "desc": "Protein dan sayur segar per bulan",
                "icon": "leaf",
            }
            needs_detail["Gas & Bumbu"] = {
                "amount": int(cost_makan_total * 0.15),
                "desc": "Gas LPG dan bumbu dapur per bulan",
                "icon": "fire",
            }

        # 1b. TEMPAT TINGGAL
        if housing_type == "kos":
            cost_housing = int(COST_DEFAULTS["sewa_kos"] * city_multiplier)
            housing_label = "Sewa Kos"
        elif housing_type == "kontrakan":
            cost_housing = int(COST_DEFAULTS["sewa_kontrakan"] * city_multiplier)
            housing_label = "Sewa Kontrakan"
        elif housing_type == "cicilan":
            cost_housing = COST_DEFAULTS["cicilan_rumah"]
            housing_label = "Cicilan Rumah"
        else:
            cost_housing = 0
            housing_label = "Rumah Sendiri (Lunas)"

        if fixed_costs.get("housing") is not None:
            cost_housing = int(fixed_costs["housing"])
            housing_label = f"{housing_label} (manual)"

        needs_detail["Tempat Tinggal"] = {
            "amount": cost_housing,
            "desc": housing_label,
            "icon": "home",
        }

        # 1c. LISTRIK & AIR
        cost_listrik = int((COST_DEFAULTS["listrik_base"] + (COST_DEFAULTS["listrik_per_orang"] * family_size)) * city_multiplier)
        listrik_desc = f"Base + {family_size} orang"
        if fixed_costs.get("electricity") is not None:
            cost_listrik = int(fixed_costs["electricity"])
            listrik_desc = "Biaya manual"
        
        if water_source == "sumur":
            cost_air = 0
            air_desc = "Gratis (Air Sumur)"
        else:
            cost_air = int((COST_DEFAULTS["air_base"] + (COST_DEFAULTS["air_per_orang"] * family_size)) * city_multiplier)
            air_desc = f"Base + {family_size} orang"
        if fixed_costs.get("water") is not None:
            cost_air = int(fixed_costs["water"])
            air_desc = "Biaya manual"
            
        needs_detail["Listrik"] = {"amount": int(cost_listrik), "desc": listrik_desc, "icon": "bolt"}
        needs_detail["Air/Air Minum"] = {"amount": int(cost_air), "desc": air_desc, "icon": "tint"}

        # 1d. INTERNET
        cost_internet = int(COST_DEFAULTS["internet"] * city_multiplier)
        internet_desc = "WiFi rumah"
        if fixed_costs.get("internet") is not None:
            cost_internet = int(fixed_costs["internet"])
            internet_desc = "Biaya manual"
        needs_detail["Internet"] = {"amount": cost_internet, "desc": internet_desc, "icon": "wifi"}

        # 1e. TRANSPORTASI
        cost_transport = 0
        transport_desc = ""
        if has_vehicle in ("motor", "both"):
            cost_transport += int(COST_DEFAULTS["bensin_motor"] * city_multiplier)
            transport_desc += "Motor"
        if has_vehicle in ("mobil", "both"):
            cost_transport += int(COST_DEFAULTS["bensin_mobil"] * city_multiplier)
            transport_desc += (" + " if transport_desc else "") + "Mobil"
        if has_vehicle == "none":
            cost_transport = int(150_000 * city_multiplier)  # estimasi ojol/angkot
            transport_desc = "Transportasi umum/ojek online"
        if fixed_costs.get("transport") is not None:
            cost_transport = int(fixed_costs["transport"])
            transport_desc = "Biaya manual"

        needs_detail["Transportasi"] = {"amount": cost_transport, "desc": transport_desc or "-", "icon": "car"}

        # 1f. PENDIDIKAN ANAK
        cost_education = 0
        num_balita = 0
        num_sekolah = 0
        if num_children > 0 and children_ages:
            for age in children_ages:
                if age < 5:
                    cost_education += int(COST_DEFAULTS["balita_per_anak"] * city_multiplier)
                    num_balita += 1
                else:
                    cost_education += int(COST_DEFAULTS["sekolah_per_anak"] * city_multiplier)
                    num_sekolah += 1
        elif num_children > 0:
            # Jika tidak ada detail usia, asumsikan semua usia sekolah
            cost_education = int(COST_DEFAULTS["sekolah_per_anak"] * city_multiplier) * num_children
            num_sekolah = num_children

        if cost_education > 0:
            edu_parts = []
            if num_balita > 0:
                edu_parts.append(f"{num_balita} balita")
            if num_sekolah > 0:
                edu_parts.append(f"{num_sekolah} usia sekolah")
            needs_detail["Pendidikan Anak"] = {
                "amount": cost_education,
                "desc": ", ".join(edu_parts),
                "icon": "graduation-cap",
            }

        # -------------------------------------------------------
        # STEP 2: Hitung total Needs dan sesuaikan proporsi 50/30/20
        # -------------------------------------------------------
        for item in needs_detail.values():
            item["raw_amount"] = item["amount"]
        raw_needs_estimated = sum(item["amount"] for item in needs_detail.values())

        # Proporsi needs ideal = 50%, tapi jika kebutuhan riil lebih tinggi,
        # sesuaikan secara dinamis dengan tetap melindungi tabungan minimum 10%
        needs_ratio = raw_needs_estimated / income if income > 0 else 0.5
        min_savings_ratio = mode["min_savings"]  # minimal tabungan sesuai mode

        if needs_ratio <= mode["base_needs"]:
            # Ideal: kebutuhan riil di bawah batas mode
            final_needs_ratio = mode["base_needs"]
            final_wants_ratio = mode["base_wants"]
            final_savings_ratio = mode["base_savings"]
        elif needs_ratio <= 0.70:
            # Kebutuhan 50-70%: kurangi wants, pertahankan savings minimum
            final_needs_ratio = needs_ratio
            final_savings_ratio = max(min_savings_ratio, 1.0 - needs_ratio - 0.15)
            final_wants_ratio = 1.0 - final_needs_ratio - final_savings_ratio
        else:
            # Kebutuhan > 70%: mode darurat, savings minimal 10%
            final_needs_ratio = min(needs_ratio, mode["max_needs"])
            final_savings_ratio = min_savings_ratio
            final_wants_ratio = max(0.05, 1.0 - final_needs_ratio - final_savings_ratio)

        # Anggaran ideal awal
        ideal_needs_budget = int(round(income * final_needs_ratio))
        wants_budget = int(round(income * final_wants_ratio))
        savings_budget = max(0, income - ideal_needs_budget - wants_budget)
        needs_budget = ideal_needs_budget

        # Jika estimasi kebutuhan normal melebihi alokasi yang tersedia,
        # lakukan penyesuaian anggaran secara cerdas dengan melindungi biaya tetap manual.
        is_budget_adjusted = raw_needs_estimated > ideal_needs_budget
        if is_budget_adjusted and raw_needs_estimated > 0:
            # Identifikasi biaya tetap manual (fixed costs)
            fixed_keys = []
            if fixed_costs.get("housing") is not None:
                fixed_keys.append("Tempat Tinggal")
            if fixed_costs.get("electricity") is not None:
                fixed_keys.append("Listrik")
            if fixed_costs.get("water") is not None:
                fixed_keys.append("Air/Air Minum")
            if fixed_costs.get("internet") is not None:
                fixed_keys.append("Internet")
            if fixed_costs.get("transport") is not None:
                fixed_keys.append("Transportasi")

            fixed_total = sum(needs_detail[k]["amount"] for k in fixed_keys if k in needs_detail)
            variable_keys = [k for k in needs_detail.keys() if k not in fixed_keys]
            variable_total = sum(needs_detail[k]["amount"] for k in variable_keys)

            if fixed_total > ideal_needs_budget:
                # 1. Biaya tetap manual melebihi ideal needs_budget
                # Potong seluruh kebutuhan variabel menjadi 0
                for k in variable_keys:
                    needs_detail[k]["amount"] = 0
                    needs_detail[k]["desc"] = f"{needs_detail[k]['desc']} (disesuaikan budget)"
                
                # Defisit yang harus ditutupi dari Wants/Savings
                deficit_to_cover = fixed_total - ideal_needs_budget
                
                # Kurangi Wants budget terlebih dahulu
                if wants_budget >= deficit_to_cover:
                    wants_budget -= deficit_to_cover
                    deficit_to_cover = 0
                else:
                    deficit_to_cover -= wants_budget
                    wants_budget = 0
                    
                # Sisa defisit dikurangi dari Savings budget
                if savings_budget >= deficit_to_cover:
                    savings_budget -= deficit_to_cover
                    deficit_to_cover = 0
                else:
                    deficit_to_cover -= savings_budget
                    savings_budget = 0
                
                # Update kebutuhan pokok ke nilai biaya tetap manual (dikurangi sisa defisit yang tidak tercover)
                needs_budget = fixed_total - deficit_to_cover

                # Jika masih ada sisa defisit (berarti fixed_total > income), kita terpaksa men-scale down biaya tetap manual agar totalnya pas dengan needs_budget (income)
                if deficit_to_cover > 0 and fixed_total > 0:
                    scale_fixed = needs_budget / fixed_total
                    for k in fixed_keys:
                        if k in needs_detail:
                            needs_detail[k]["amount"] = int(needs_detail[k]["amount"] * scale_fixed)
                            needs_detail[k]["desc"] = f"{needs_detail[k]['desc']} (disesuaikan budget)"
            else:
                # 2. Biaya tetap manual tidak melebihi ideal needs_budget
                # Potong hanya kebutuhan variabel
                deficit = raw_needs_estimated - ideal_needs_budget
                if variable_total > 0:
                    scale_var = (variable_total - deficit) / variable_total
                    scaled_var_total = 0
                    last_var_key = None
                    for k in variable_keys:
                        last_var_key = k
                        needs_detail[k]["amount"] = int(needs_detail[k]["amount"] * scale_var)
                        needs_detail[k]["desc"] = f"{needs_detail[k]['desc']} (disesuaikan budget)"
                        scaled_var_total += needs_detail[k]["amount"]
                    
                    # Koreksi pembulatan kebutuhan variabel
                    target_var_total = variable_total - deficit
                    if last_var_key is not None:
                        needs_detail[last_var_key]["amount"] += int(target_var_total - scaled_var_total)

        needs_pct = round(needs_budget / income * 100) if income > 0 else 0
        wants_pct = round(wants_budget / income * 100) if income > 0 else 0
        savings_pct = max(0, 100 - needs_pct - wants_pct)

        total_needs_estimated = sum(item["amount"] for item in needs_detail.values())

        # -------------------------------------------------------
        # STEP 3: Breakdown Wants berdasarkan data historis + ML
        # -------------------------------------------------------
        wants_items = self._generate_wants_breakdown(wants_budget, profile, family_size)

        # -------------------------------------------------------
        # STEP 4: Saran tabungan
        # -------------------------------------------------------
        savings_tips = self._generate_savings_tips(savings_budget, profile)

        # -------------------------------------------------------
        # STEP 5: Warning jika pengeluaran melebihi pendapatan
        # -------------------------------------------------------
        warnings = []
        if is_budget_adjusted:
            selisih = raw_needs_estimated - ideal_needs_budget
            msg = (
                f"Estimasi kebutuhan pokok normal Anda (Rp {raw_needs_estimated:,.0f}) melebihi alokasi Needs "
                f"sebesar Rp {selisih:,.0f}. Pertimbangkan untuk mengurangi pengeluaran atau meningkatkan pendapatan."
            )
            if GEMINI_API_KEY:
                msg = refine_sentence_with_gemini(msg, "Peringatan kebutuhan pokok melebihi target alokasi ideal.")
            warnings.append(msg)
        if raw_needs_estimated > income * 0.80:
            msg = (
                "Kebutuhan pokok Anda melebihi 80% pendapatan. Kondisi keuangan Anda dalam status KRITIS. "
                "Prioritaskan kebutuhan paling mendasar dan cari sumber pendapatan tambahan."
            )
            if GEMINI_API_KEY:
                msg = refine_sentence_with_gemini(msg, "Peringatan krisis keuangan di mana pengeluaran pokok > 80% pendapatan.")
            warnings.append(msg)

        if raw_needs_estimated <= income * 0.50:
            health_status = "aman"
            health_message = "Kebutuhan pokok masih berada di batas sehat."
        elif raw_needs_estimated <= income * 0.80:
            health_status = "waspada"
            health_message = "Kebutuhan pokok mulai menekan ruang keinginan dan tabungan."
        else:
            health_status = "kritis"
            health_message = "Kebutuhan pokok normal lebih besar dari batas sehat pendapatan."

        if GEMINI_API_KEY:
            health_message = refine_sentence_with_gemini(
                health_message, 
                f"Status kesehatan keuangan adalah {health_status} dengan rasio pengeluaran {raw_needs_estimated/income if income > 0 else 0.5:.2f}."
            )

        # Update Makan Harian desc dynamically based on the final amount
        if "Makan Harian" in needs_detail:
            daily_food = needs_detail["Makan Harian"]["amount"] // 30
            suffix = " (disesuaikan budget)" if "disesuaikan budget" in needs_detail["Makan Harian"]["desc"] else ""
            needs_detail["Makan Harian"]["desc"] = f"Warung/kantin sekitar Rp {daily_food:,.0f}/hari{suffix}"

        # -------------------------------------------------------
        # STEP 6: Susun response JSON
        # -------------------------------------------------------
        return {
            "budget_rule": {
                "needs": needs_budget,
                "wants": wants_budget,
                "savings": savings_budget,
                "needs_pct": needs_pct,
                "wants_pct": wants_pct,
                "savings_pct": savings_pct,
            },
            "needs_detail": [
                {"name": k, "amount": v["amount"], "raw_amount": v["raw_amount"], "desc": v["desc"], "icon": v["icon"]}
                for k, v in needs_detail.items()
            ],
            "needs_total_estimated": total_needs_estimated,
            "normal_needs_total": raw_needs_estimated,
            "is_budget_adjusted": is_budget_adjusted,
            "budget_health": {
                "status": health_status,
                "message": health_message,
            },
            "wants_items": wants_items,
            "savings_tips": savings_tips,
            "warnings": warnings,
            "family_info": {
                "user_type": user_type,
                "city_tier": city_tier,
                "budget_mode": budget_mode,
                "family_size": family_size,
                "num_children": num_children,
                "vehicle": has_vehicle,
                "housing": housing_type,
            },
            "profile_used": profile,
        }

    # ============================================================
    # HELPER: Breakdown pengeluaran Wants
    # ============================================================
    def _generate_wants_breakdown(self, wants_budget, profile, family_size):
        """
        Menghasilkan list item pengeluaran keinginan (Wants) secara dinamis
        berdasarkan kategori riil yang ada di dataset.
        """
        items = []
        mult = {"Hemat": 0.7, "Standar": 1.0, "Konsumtif": 1.2}.get(profile, 1.0)
        
        wants_mapping = WANTS_MAPPING

        available_wants = [cat for cat in wants_mapping.keys() if cat in self.category_avg_monthly]
        if not available_wants:
            available_wants = ["Makan & Minum", "Hiburan"]
            
        # Menghitung bobot secara dinamis menggunakan K-Means jika model terlatih
        use_dynamic = False
        cluster_idx = None
        weights = {}

        if self.model_trained and self.cluster_breakdown is not None and profile in self.profile_mapping:
            cluster_idx = self.profile_mapping[profile]
            total_cluster_wants = 0
            for cat in available_wants:
                val = 0
                if cat in self.cluster_breakdown.columns:
                    val = self.cluster_breakdown.loc[cluster_idx, cat]
                weights[cat] = val
                total_cluster_wants += val
            
            if total_cluster_wants > 0:
                use_dynamic = True
                # Normalisasi bobot dinamis
                for cat in available_wants:
                    weights[cat] = weights[cat] / total_cluster_wants
            else:
                use_dynamic = False

        if not use_dynamic:
            total_weight = sum(wants_mapping[cat]["weight"] for cat in available_wants)
            for cat in available_wants:
                weights[cat] = wants_mapping[cat]["weight"] / total_weight
        
        for cat in available_wants:
            info = wants_mapping[cat]
            cat_budget = int(wants_budget * weights[cat])
            
            # Tentukan rata-rata transaksi per kategori per kluster jika pakai dinamis
            if use_dynamic:
                avg_hist = self.cluster_category_avg_transaction.get((cluster_idx, cat), 0)
                if avg_hist <= 0:
                    avg_hist = int(self.category_avg_transaction.get(cat, 100_000) * mult)
            else:
                avg_hist = int(self.category_avg_transaction.get(cat, 100_000) * mult)

            # Batasi nilai minimal rata-rata transaksi agar tidak terjadi division by zero atau nilai negatif
            avg_hist = max(1000, avg_hist)
            
            freq = cat_budget // avg_hist if avg_hist > 0 else 0
            
            if cat == "Makan & Minum":
                desc = self._format_limit_desc("Makan di luar / delivery", freq, avg_hist)
            elif cat == "Hiburan":
                desc = self._format_limit_desc("Aktivitas hiburan/streaming", freq, avg_hist)
            elif cat == "Pakaian & Fashion":
                desc = self._format_limit_desc("Belanja pakaian", freq, avg_hist)
            elif cat == "Perawatan Diri":
                desc = self._format_limit_desc("Skincare/salon/barbershop", freq, avg_hist)
            elif cat == "Donasi & Amal":
                desc = f"Sisihkan untuk sedekah/zakat agar rezeki makin berkah."
            else:
                desc = f"Alokasi untuk {cat} (rata-rata Rp {avg_hist:,.0f})."
                
            items.append({
                "category": cat,
                "budget": cat_budget,
                "avg_transaction": avg_hist,
                "icon": info["icon"],
                "color": info["color"],
                "details": desc,
            })
            
        return items

    def _format_limit_desc(self, label, freq, avg_amount):
        if freq <= 0:
            return (
                "Budget belum cukup untuk 1 transaksi rata-rata "
                f"(Est. Rp {avg_amount:,.0f}). Pilih opsi gratis atau lebih murah."
            )
        return f"{label} maks {freq}x/bulan (Est. Rp {avg_amount:,.0f}/transaksi)."

    # ============================================================
    # HELPER: Saran Tabungan
    # ============================================================
    def _generate_savings_tips(self, savings_budget, profile):
        """
        Memberikan saran alokasi tabungan & investasi.
        """
        tips = []

        # Dana darurat: 50% dari savings
        dana_darurat = int(savings_budget * 0.50)
        tips.append({
            "name": "Dana Darurat",
            "amount": dana_darurat,
            "icon": "shield-alt",
            "desc": "Sisihkan untuk tabungan darurat (target 3-6 bulan pengeluaran).",
        })

        # Investasi: 30% dari savings
        investasi = int(savings_budget * 0.30)
        if profile == "Hemat":
            invest_desc = "Reksadana pasar uang atau deposito untuk risiko rendah."
        elif profile == "Konsumtif":
            invest_desc = "Pertimbangkan reksadana saham atau saham blue chip untuk return lebih tinggi."
        else:
            invest_desc = "Reksadana campuran atau obligasi negara untuk keseimbangan risiko dan return."

        tips.append({
            "name": "Investasi",
            "amount": investasi,
            "icon": "chart-line",
            "desc": invest_desc,
        })

        # Asuransi/Proteksi: 20% dari savings
        proteksi = int(savings_budget * 0.20)
        tips.append({
            "name": "Proteksi & Asuransi",
            "amount": proteksi,
            "icon": "umbrella",
            "desc": "Premi asuransi kesehatan/jiwa untuk perlindungan keluarga.",
        })

        return tips

