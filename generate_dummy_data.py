"""
generate_dummy_data.py
======================
Membuat dataset dummy yang realistis untuk kehidupan:
  1. Mahasiswa (anak kos / tinggal sendiri)
  2. Mahasiswa yang tinggal bersama keluarga
  3. Lajang muda / fresh graduate
Disesuaikan dengan kondisi lapangan di Indonesia.
"""

import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta


def generate_dummy_data(filename="Data_Finance_6_Bulan.csv"):
    random.seed(42)
    np.random.seed(42)

    # ----------------------------------------------------------------
    # KATEGORI & ITEM — disesuaikan kehidupan mahasiswa & keluarga
    # ----------------------------------------------------------------
    categories = [
        'Makan & Minum',
        'Hiburan',
        'Tagihan',
        'Belanja Rumah Tangga',
        'Transportasi',
        'Kesehatan',
        'Pakaian & Fashion',
        'Perawatan Diri',
        'Edukasi',
        'Donasi & Amal',
    ]

    titles_map = {
        'Makan & Minum': [
            'Warteg / Warung Nasi',
            'Mie Ayam / Bakso',
            'Kantin Kampus',
            'Beli Mie Instan',
            'Kopi Kapal Api / Nescafe',
            'Jajan Minuman Kekinian',
            'GoFood / GrabFood',
            'Beli Roti / Sarapan',
            'Makan Siang Bersama Teman',
            'Makan Malam di Luar',
        ],
        'Hiburan': [
            'Nonton Bioskop XXI',
            'Netflix / Disney+ Bareng',
            'Spotify Premium',
            'Main Game Mobile',
            'Jalan ke Mall',
            'Futsal / Badminton',
            'Karaoke Dengan Teman',
            'Nongkrong Kafe',
        ],
        'Tagihan': [
            'Bayar Kos Bulanan',
            'Tagihan Listrik',
            'Internet / Wi-Fi Kos',
            'Paket Data Seluler',
            'Air PDAM',
            'Iuran Lingkungan RT',
            'Bayar Kontrakan',
        ],
        'Belanja Rumah Tangga': [
            'Shopee / Tokopedia',
            'Indomaret',
            'Alfamart',
            'Beli Sabun / Sampo / Deterjen',
            'Beli Sembako (Beras, Telur)',
            'Beli Minyak Goreng',
            'Peralatan Dapur',
        ],
        'Transportasi': [
            'Gojek / Grab',
            'Beli Bensin Motor',
            'Parkir Kampus',
            'Angkot / Trans',
            'Ojek Konvensional',
            'Tol',
            'Servis / Ganti Oli Motor',
        ],
        'Kesehatan': [
            'Beli Obat di Apotek',
            'Periksa ke Klinik',
            'Beli Vitamin / Suplemen',
            'Halodoc / Konsultasi Online',
            'Iuran BPJS',
        ],
        'Pakaian & Fashion': [
            'Beli Baju di Toko',
            'Shopee Fashion',
            'Beli Sepatu / Sandal',
            'Beli Seragam / Jas Almamater',
            'Distro / Thrift Shop',
        ],
        'Perawatan Diri': [
            'Cukur / Pangkas Rambut',
            'Beli Skincare Murah',
            'Beli Sabun Mandi / Deodoran',
            'Facial Wash',
            'Minyak Rambut / Pomade',
        ],
        'Edukasi': [
            'Beli Buku / Modul Kuliah',
            'Print & Fotocopy',
            'Kursus Online (Dicoding/Udemy)',
            'Bayar SKS / UKT Cicilan',
            'Alat Tulis',
            'Biaya Seminar / Workshop',
        ],
        'Donasi & Amal': [
            'Infaq Masjid Kampus',
            'Iuran Organisasi',
            'Sumbangan Teman Sakit',
            'Sedekah Jumat',
        ],
    }

    # ----------------------------------------------------------------
    # RANGE NOMINAL — disesuaikan kantong mahasiswa (dalam Rupiah)
    # ----------------------------------------------------------------
    amount_range = {
        'Makan & Minum': (8_000, 50_000),          # sekali makan 8k–50k
        'Hiburan': (15_000, 100_000),               # hiburan murah–sedang
        'Tagihan': (50_000, 800_000),               # kos/internet/listrik
        'Belanja Rumah Tangga': (15_000, 200_000),  # kebutuhan sehari-hari
        'Transportasi': (5_000, 80_000),            # bensin/ojol murah
        'Kesehatan': (10_000, 150_000),             # obat/klinik
        'Pakaian & Fashion': (50_000, 250_000),     # baju/sepatu
        'Perawatan Diri': (10_000, 80_000),         # toiletries murah
        'Edukasi': (5_000, 200_000),                # print/buku/kursus
        'Donasi & Amal': (5_000, 50_000),           # sedekah mahasiswa
    }

    # ----------------------------------------------------------------
    # BOBOT FREKUENSI KATEGORI — sesuai kebiasaan mahasiswa
    # ----------------------------------------------------------------
    weights = [
        0.30,   # Makan & Minum   → paling sering
        0.08,   # Hiburan
        0.08,   # Tagihan
        0.10,   # Belanja RT
        0.15,   # Transportasi    → cukup sering naik ojol/bensin
        0.05,   # Kesehatan
        0.05,   # Pakaian
        0.07,   # Perawatan Diri
        0.07,   # Edukasi
        0.05,   # Donasi
    ]

    start_date = datetime.now() - timedelta(days=180)
    data = []

    # ----------------------------------------------------------------
    # 700 transaksi EXPENSE — simulasi 6 bulan pengeluaran
    # ----------------------------------------------------------------
    for _ in range(700):
        cat = random.choices(categories, weights=weights)[0]
        title = random.choice(titles_map[cat])
        lo, hi = amount_range[cat]
        amount = random.randint(lo, hi)

        # Pembulatan ke ribuan agar lebih natural
        amount = round(amount / 1000) * 1000

        date = start_date + timedelta(days=random.randint(0, 180))

        data.append({
            'Date': date.strftime('%Y-%m-%d'),
            'Title': title,
            'Amount': amount,
            'Type': 'EXPENSE',
            'Category': cat,
            'Account': random.choice(['Dana', 'OVO', 'GoPay', 'Tunai', 'BRI', 'BNI']),
        })

    # ----------------------------------------------------------------
    # INCOME — simulasi uang saku/beasiswa 6 bulan
    # ----------------------------------------------------------------
    income_sources = [
        ('Uang Saku dari Orang Tua', 800_000, 2_000_000),
        ('Beasiswa PPA / BBP', 300_000, 700_000),
        ('Freelance / Part-time', 200_000, 1_500_000),
        ('Uang Saku Tambahan', 100_000, 500_000),
        ('Proyek / Lomba', 500_000, 3_000_000),
    ]

    for month_offset in range(6):
        base_date = start_date + timedelta(days=month_offset * 30 + random.randint(1, 5))

        # Uang saku tiap bulan (paling umum)
        title, lo, hi = income_sources[0]
        data.append({
            'Date': base_date.strftime('%Y-%m-%d'),
            'Title': title,
            'Amount': random.randint(lo // 1000, hi // 1000) * 1000,
            'Type': 'INCOME',
            'Category': 'Uang Saku',
            'Account': random.choice(['Dana', 'BRI', 'BNI', 'Tunai']),
        })

        # Beasiswa: tidak tiap bulan (50% peluang)
        if random.random() < 0.5:
            title, lo, hi = income_sources[1]
            data.append({
                'Date': (base_date + timedelta(days=random.randint(3, 10))).strftime('%Y-%m-%d'),
                'Title': title,
                'Amount': random.randint(lo // 1000, hi // 1000) * 1000,
                'Type': 'INCOME',
                'Category': 'Beasiswa',
                'Account': 'BRI',
            })

        # Freelance: kadang-kadang (30% peluang)
        if random.random() < 0.30:
            title, lo, hi = income_sources[2]
            data.append({
                'Date': (base_date + timedelta(days=random.randint(5, 20))).strftime('%Y-%m-%d'),
                'Title': title,
                'Amount': random.randint(lo // 1000, hi // 1000) * 1000,
                'Type': 'INCOME',
                'Category': 'Pendapatan Lain',
                'Account': random.choice(['Dana', 'GoPay', 'BRI']),
            })

    df = pd.DataFrame(data)
    df = df.sort_values(by='Date').reset_index(drop=True)
    df.to_csv(filename, index=False)

    total_expense = df[df['Type'] == 'EXPENSE']['Amount'].sum()
    total_income = df[df['Type'] == 'INCOME']['Amount'].sum()
    print(f"[OK] Dataset dummy berhasil dibuat: {filename}")
    print(f"     Total baris  : {len(df)}")
    print(f"     EXPENSE      : {len(df[df['Type'] == 'EXPENSE'])} transaksi -> Rp {total_expense:,.0f}")
    print(f"     INCOME       : {len(df[df['Type'] == 'INCOME'])} transaksi -> Rp {total_income:,.0f}")
    print(f"     Rentang waktu: {df['Date'].min()} s/d {df['Date'].max()}")


if __name__ == '__main__':
    generate_dummy_data()
