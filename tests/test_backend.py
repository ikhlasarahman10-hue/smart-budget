from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app
from ml_engine import BudgetRecommender


client = TestClient(app)


def base_payload(**overrides):
    payload = {
        "income": 3_000_000,
        "profile": "Standar",
        "user_type": "anak_kos",
        "city_tier": "sedang",
        "budget_mode": "normal",
        "family_size": 1,
        "num_children": 0,
        "children_ages": [],
        "has_vehicle": "none",
        "housing_type": "kos",
        "water_source": "pdam",
    }
    payload.update(overrides)
    return payload


def assert_budget_balanced(data, income):
    rule = data["budget_rule"]
    assert rule["needs"] + rule["wants"] + rule["savings"] == income
    assert rule["needs"] >= 0
    assert rule["wants"] >= 0
    assert rule["savings"] >= 0


def test_health_endpoint_reports_training_status():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["model_trained"], bool)
    assert body["data_path"] == "Data_Finance_6_Bulan.csv"
    assert body["training_status"] in {"trained", "fallback", "not_started"}
    assert body["training_message"]


def test_predict_budget_anak_kos_normal_income():
    response = client.post("/predict_budget", json=base_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    data = body["data"]
    assert_budget_balanced(data, 3_000_000)
    assert data["family_info"]["user_type"] == "anak_kos"
    assert data["family_info"]["family_size"] == 1
    assert data["family_info"]["num_children"] == 0
    assert data["needs_detail"]
    assert data["wants_items"]
    assert data["savings_tips"]


def test_predict_budget_family_with_children():
    payload = base_payload(
        income=8_000_000,
        profile="Hemat",
        user_type="keluarga_anak_sekolah",
        family_size=4,
        num_children=2,
        children_ages=[3, 8],
        housing_type="kontrakan",
        has_vehicle="motor",
    )

    response = client.post("/predict_budget", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    assert_budget_balanced(data, 8_000_000)
    assert data["family_info"]["family_size"] == 4
    assert data["family_info"]["num_children"] == 2
    assert any(item["name"] == "Pendidikan Anak" for item in data["needs_detail"])


def test_predict_budget_fixed_cost_over_budget_warns_and_balances():
    payload = base_payload(
        income=1_000_000,
        fixed_housing_cost=2_000_000,
        fixed_electricity_cost=500_000,
        fixed_transport_cost=500_000,
    )

    response = client.post("/predict_budget", json=payload)

    assert response.status_code == 200
    data = response.json()["data"]
    assert_budget_balanced(data, 1_000_000)
    assert data["is_budget_adjusted"] is True
    assert data["warnings"]
    assert data["budget_health"]["status"] == "kritis"


def test_children_ages_must_match_num_children():
    payload = base_payload(
        user_type="keluarga_kecil",
        family_size=3,
        num_children=2,
        children_ages=[5],
    )

    response = client.post("/predict_budget", json=payload)

    assert response.status_code == 422
    assert "Jumlah usia anak" in response.text


def test_recommender_fallback_when_csv_missing(tmp_path):
    recommender = BudgetRecommender(str(tmp_path / "missing.csv"))

    assert recommender.model_trained is False
    assert recommender.training_status == "fallback"
    result = recommender.recommend(2_000_000, "Standar")
    assert_budget_balanced(result, 2_000_000)
    assert result["wants_items"]


def test_predict_budget_dynamic_kmeans_integration():
    # Menggunakan recommender utama yang dilatih dari Data_Finance_6_Bulan.csv
    recommender = BudgetRecommender("Data_Finance_6_Bulan.csv")
    assert recommender.model_trained is True
    
    # Ambil rekomendasi untuk dua profil yang berbeda
    result_hemat = recommender.recommend(5_000_000, "Hemat")
    result_konsumtif = recommender.recommend(5_000_000, "Konsumtif")
    
    # Periksa bahwa kluster di-mapping dengan benar
    assert recommender.profile_mapping["Hemat"] != recommender.profile_mapping["Konsumtif"]
    
    # Pastikan alokasi budget wants terpengaruh secara dinamis
    wants_hemat = {item["category"]: item["budget"] for item in result_hemat["wants_items"]}
    wants_konsumtif = {item["category"]: item["budget"] for item in result_konsumtif["wants_items"]}
    
    # Periksa ketersediaan kategori wants yang umum
    assert "Makan & Minum" in wants_hemat
    assert "Makan & Minum" in wants_konsumtif
    
    # Proporsi anggaran wants per kategori harus berbeda di antara profil yang berbeda
    ratio_hemat = wants_hemat["Makan & Minum"] / max(1, wants_hemat.get("Hiburan", 1))
    ratio_konsumtif = wants_konsumtif["Makan & Minum"] / max(1, wants_konsumtif.get("Hiburan", 1))
    
    assert ratio_hemat != ratio_konsumtif


def test_fixed_costs_protected_from_scaling():
    recommender = BudgetRecommender("Data_Finance_6_Bulan.csv")
    
    # Masukkan fixed cost sewa (housing) Rp 2.700.000 dengan pendapatan Rp 3.000.000
    # Batas ideal Needs (50% dari 3M) adalah Rp 1.500.000, tapi dengan max_needs (85%) adalah Rp 2.550.000.
    result = recommender.recommend(
        income=3_000_000,
        profile="Standar",
        fixed_costs={"housing": 2_700_000}
    )
    
    # 1. Pastikan tempat tinggal (biaya tetap) dipertahankan 100% (Rp 2.700.000)
    housing_item = next(item for item in result["needs_detail"] if item["name"] == "Tempat Tinggal")
    assert housing_item["amount"] == 2_700_000
    
    # 2. Pastikan kebutuhan variabel (seperti bensin/ojol di Transportasi) terpotong/disesuaikan ke 0
    transport_item = next(item for item in result["needs_detail"] if item["name"] == "Transportasi")
    assert transport_item["amount"] == 0
    
    # 3. Pastikan Wants budget dikurangi untuk mendanai defisit Rp 150.000 tersebut
    assert result["budget_rule"]["wants"] == 0
    assert result["budget_rule"]["needs"] == 2_700_000
    assert result["budget_rule"]["savings"] == 300_000
