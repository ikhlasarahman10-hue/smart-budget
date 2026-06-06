"""
app.py — Backend FastAPI untuk Sistem Rekomendasi Anggaran
==========================================================
Endpoint:
  POST /predict_budget  → menerima data lengkap pengguna + keluarga
                          → mengembalikan rekomendasi dari ML engine
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from typing import Literal, List, Optional
from ml_engine import BudgetRecommender, refine_sentence_with_gemini
import uvicorn

app = FastAPI(
    title="Sistem Rekomendasi Anggaran & Pengeluaran",
    description="API backend untuk rekomendasi anggaran cerdas berbasis Machine Learning",
    version="2.0.0",
)

# Konfigurasi CORS agar frontend dapat melakukan fetch API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inisialisasi model Machine Learning saat server start
recommender = BudgetRecommender("Data_Finance_6_Bulan.csv")


# ============================================================
# Request / Response Models (Struktur Data Input & Output)
# ============================================================

# Model data input yang dikirim oleh frontend saat meminta rekomendasi anggaran
class BudgetRequest(BaseModel):
    income: int = Field(..., ge=500_000, le=1_000_000_000, description="Pendapatan bulanan dalam Rupiah")
    profile: Literal["Hemat", "Standar", "Konsumtif"] = Field(..., description="Profil gaya hidup")
    user_type: Literal["anak_kos", "lajang", "keluarga_kecil", "keluarga_anak_sekolah"] = Field(default="anak_kos", description="Tipe pengguna")
    city_tier: Literal["murah", "sedang", "mahal"] = Field(default="sedang", description="Kategori biaya hidup lokasi")
    budget_mode: Literal["normal", "hemat", "darurat", "agresif_menabung"] = Field(default="normal", description="Strategi alokasi budget")
    family_size: int = Field(default=1, ge=1, le=20, description="Jumlah anggota keluarga (termasuk diri sendiri)")
    num_children: int = Field(default=0, ge=0, le=15, description="Jumlah anak")
    children_ages: Optional[List[int]] = Field(default=None, description="Usia masing-masing anak")
    has_vehicle: Literal["none", "motor", "mobil", "both"] = Field(default="none", description="Kendaraan")
    housing_type: Literal["kos", "kontrakan", "rumah_sendiri", "cicilan"] = Field(default="kos", description="Tipe tempat tinggal")
    water_source: Literal["pdam", "sumur"] = Field(default="pdam", description="Sumber air")
    fixed_housing_cost: Optional[int] = Field(default=None, ge=0, le=100_000_000, description="Biaya tempat tinggal manual")
    fixed_electricity_cost: Optional[int] = Field(default=None, ge=0, le=50_000_000, description="Biaya listrik manual")
    fixed_water_cost: Optional[int] = Field(default=None, ge=0, le=50_000_000, description="Biaya air manual")
    fixed_internet_cost: Optional[int] = Field(default=None, ge=0, le=50_000_000, description="Biaya internet manual")
    fixed_transport_cost: Optional[int] = Field(default=None, ge=0, le=50_000_000, description="Biaya transport manual")

    # Validasi keselarasan data keluarga (misal: jumlah anak dan list usianya harus cocok)
    @model_validator(mode="after")
    def validate_family(self):
        if self.children_ages is None:
            self.children_ages = []

        if len(self.children_ages) != self.num_children:
            raise ValueError("Jumlah usia anak harus sama dengan jumlah anak.")

        if any(age < 0 or age > 25 for age in self.children_ages):
            raise ValueError("Usia anak harus berada di rentang 0 sampai 25 tahun.")

        if self.num_children >= self.family_size:
            raise ValueError("Jumlah anggota keluarga harus lebih besar dari jumlah anak.")

        return self


# Model data untuk respons status kesehatan server & training model ML
class HealthResponse(BaseModel):
    status: Literal["ok"]
    model_trained: bool
    data_path: str
    training_status: str
    training_message: str


# Model data untuk pembagian 3 pos utama (Kebutuhan, Keinginan, Tabungan) beserta persentasenya
class BudgetRule(BaseModel):
    needs: int
    wants: int
    savings: int
    needs_pct: int
    wants_pct: int
    savings_pct: int


# Model data untuk pengeluaran pokok (Needs) yang memiliki nama, jumlah, ikon, dan deskripsi
class NamedAmountItem(BaseModel):
    name: str
    amount: int
    raw_amount: Optional[int] = None
    icon: str
    desc: str


# Model data untuk pengeluaran keinginan (Wants) beserta batas frekuensi transaksi bulanan
class WantsItem(BaseModel):
    category: str
    budget: int
    avg_transaction: int
    icon: str
    color: str
    details: str


# Model data status kesehatan keuangan berdasarkan rasio pengeluaran pokok
class BudgetHealth(BaseModel):
    status: Literal["aman", "waspada", "kritis"]
    message: str


# Model data detail parameter keluarga untuk dikembalikan ke frontend
class FamilyInfo(BaseModel):
    user_type: str
    city_tier: str
    budget_mode: str
    family_size: int
    num_children: int
    vehicle: str
    housing: str


# Model data kompilasi seluruh hasil kalkulator rekomendasi anggaran
class BudgetRecommendation(BaseModel):
    budget_rule: BudgetRule
    needs_detail: List[NamedAmountItem]
    needs_total_estimated: int
    normal_needs_total: int
    is_budget_adjusted: bool
    budget_health: BudgetHealth
    wants_items: List[WantsItem]
    savings_tips: List[NamedAmountItem]
    warnings: List[str]
    family_info: FamilyInfo
    profile_used: Literal["Hemat", "Standar", "Konsumtif"]


# Model data permintaan poles teks oleh Gemini AI
class RefineTextRequest(BaseModel):
    text: str
    context: str


# Model data respons hasil pemolesan teks oleh Gemini AI
class RefineTextResponse(BaseModel):
    status: Literal["success"]
    original_text: str
    refined_text: str


# Model data respons pembungkus hasil rekomendasi anggaran
class PredictBudgetResponse(BaseModel):
    status: Literal["success"]
    data: BudgetRecommendation


# ============================================================
# Endpoints (Rute Layanan API)
# ============================================================

# Endpoint Beranda: Memastikan API Server menyala
@app.get("/")
def read_root():
    return {
        "message": "Selamat datang di API Sistem Rekomendasi Anggaran v2.0",
        "endpoints": {
            "POST /predict_budget": "Kirim data pendapatan & profil keluarga untuk mendapatkan rekomendasi.",
        },
    }


# Endpoint Health: Mengecek status kesehatan model ML (apakah K-Means sudah siap atau memakai fallback)
@app.get("/health", response_model=HealthResponse)
def health_check():
    return {
        "status": "ok",
        "model_trained": recommender.model_trained,
        "data_path": recommender.data_path,
        "training_status": recommender.training_status,
        "training_message": recommender.training_message,
    }


# Endpoint Utama Predict Budget: Menerima info profil, menghitung budget dinamis, dan merespons hasil rekomendasi
@app.post("/predict_budget", response_model=PredictBudgetResponse)
def predict_budget(req: BudgetRequest):
    """
    Endpoint utama: menerima data pengguna lengkap, mengembalikan
    rekomendasi anggaran dari ML engine.
    """
    result = recommender.recommend(
        income=req.income,
        profile=req.profile,
        user_type=req.user_type,
        city_tier=req.city_tier,
        budget_mode=req.budget_mode,
        family_size=req.family_size,
        num_children=req.num_children,
        children_ages=req.children_ages,
        has_vehicle=req.has_vehicle,
        housing_type=req.housing_type,
        water_source=req.water_source,
        fixed_costs={
            "housing": req.fixed_housing_cost,
            "electricity": req.fixed_electricity_cost,
            "water": req.fixed_water_cost,
            "internet": req.fixed_internet_cost,
            "transport": req.fixed_transport_cost,
        },
    )
    return {"status": "success", "data": result}


# Endpoint Refine Text: Mengirim kalimat peringatan atau analisis ke Gemini AI untuk dipoles agar luwes
@app.post("/refine_text", response_model=RefineTextResponse)
def refine_text(req: RefineTextRequest):
    refined = refine_sentence_with_gemini(req.text, req.context)
    return {
        "status": "success",
        "original_text": req.text,
        "refined_text": refined
    }


if __name__ == "__main__":
    print("Server FastAPI berjalan di http://127.0.0.1:8000")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
