# SmartBudget.ai - Cara Menjalankan

SmartBudget.ai adalah aplikasi demo rekomendasi anggaran berbasis FastAPI, frontend statis, dan data transaksi dummy. File `Data_Finance_6_Bulan.csv` dipakai sebagai data demo untuk melatih ringkasan historis dan K-Means, bukan data produksi pengguna nyata.

## Kebutuhan

- Python 3.10 atau lebih baru
- Browser modern seperti Chrome atau Edge
- Koneksi internet saat membuka frontend, karena UI masih memakai CDN Tailwind, Font Awesome, Google Fonts, dan Chart.js

## 1. Install Dependency Backend

Buka PowerShell di folder proyek:

```powershell
cd "D:\projek ikhlas\SISTEM_KEUANGAN"
python -m pip install -r requirements.txt
```

Jika `python` tidak dikenali, coba:

```powershell
py -m pip install -r requirements.txt
```

Jika tetap tidak ada, install Python dari python.org lalu centang opsi "Add Python to PATH".

## 2. Jalankan Backend FastAPI

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Backend berjalan di:

```text
http://127.0.0.1:8000
```

Cek status API:

```text
http://127.0.0.1:8000/health
```

Endpoint ini menampilkan apakah model berhasil dilatih atau sedang memakai mode fallback.

## 3. Jalankan Frontend

Cara paling mudah:

1. Buka `index.html` langsung di browser.
2. Pastikan backend tetap berjalan.

Alternatif memakai server statis:

```powershell
python -m http.server 3000
```

Lalu buka:

```text
http://127.0.0.1:3000
```

URL backend frontend diatur di `smartbudget-config.js`:

```javascript
window.SMART_BUDGET_CONFIG = {
    apiBaseUrl: 'http://127.0.0.1:8000',
    mode: 'demo',
};
```

## 4. Cara Pakai

1. Isi pendapatan bulanan.
2. Pilih profil gaya hidup.
3. Pilih tipe pengguna, lokasi, dan mode budget.
4. Isi detail keluarga, kendaraan, tempat tinggal, dan sumber air jika perlu.
5. Jika punya angka asli, isi biaya tetap manual seperti sewa, listrik, internet, atau transport.
6. Klik `Hitung Rekomendasi`.

## 5. Menjalankan Test

```powershell
python -m py_compile app.py ml_engine.py generate_dummy_data.py
python -m pytest
```

Test mencakup health check, validasi request, rekomendasi anak kos/keluarga, fixed cost yang melebihi budget, dan mode fallback saat CSV tidak tersedia.

## Contoh Request API

```http
POST /predict_budget
Content-Type: application/json
```

```json
{
  "income": 3000000,
  "profile": "Standar",
  "user_type": "anak_kos",
  "city_tier": "sedang",
  "budget_mode": "normal",
  "family_size": 1,
  "num_children": 0,
  "children_ages": [],
  "has_vehicle": "none",
  "housing_type": "kos",
  "water_source": "pdam"
}
```

Contoh response ringkas:

```json
{
  "status": "success",
  "data": {
    "budget_rule": {
      "needs": 1500000,
      "wants": 900000,
      "savings": 600000,
      "needs_pct": 50,
      "wants_pct": 30,
      "savings_pct": 20
    },
    "budget_health": {
      "status": "aman",
      "message": "Kebutuhan pokok masih berada di batas sehat."
    }
  }
}
```

## Troubleshooting

- `python` atau `py` tidak dikenali: install Python dan aktifkan PATH, lalu buka terminal baru.
- `ModuleNotFoundError`: jalankan ulang `python -m pip install -r requirements.txt`.
- Backend gagal start karena port dipakai: ganti port, misalnya `--port 8001`, lalu ubah `smartbudget-config.js`.
- Frontend gagal memanggil API: pastikan `/health` bisa dibuka dan `apiBaseUrl` benar.
- Model masuk fallback: cek apakah `Data_Finance_6_Bulan.csv` ada dan memiliki kolom `Date`, `Title`, `Amount`, `Type`, dan `Category`.

## Catatan Demo

- Semua angka utama ditampilkan per bulan.
- Jika ada tulisan `disesuaikan budget`, estimasi normal lebih besar dari alokasi sehingga sistem menurunkan rincian agar tetap masuk budget.
- Rekomendasi ini adalah alat bantu edukasi/demo, bukan nasihat keuangan profesional.
