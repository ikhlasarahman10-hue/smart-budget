// script.js - SmartBudget.ai Frontend Logic

const CONFIG = window.SMART_BUDGET_CONFIG || {};
const API_BASE_URL = CONFIG.apiBaseUrl || window.SMART_BUDGET_API_BASE_URL || 'http://127.0.0.1:8000';

let lastCalculationData = null;

const allowedIcons = new Set([
    'utensils', 'mug-hot', 'box-open', 'leaf', 'fire', 'home', 'bolt', 'tint',
    'wifi', 'car', 'graduation-cap', 'hamburger', 'film', 'tshirt', 'spa',
    'hand-holding-heart', 'shield-alt', 'chart-line', 'umbrella', 'magic',
    'exclamation-triangle', 'birthday-cake',
]);

const colorMap = {
    orange: { bg: 'bg-orange-50', text: 'text-orange-500', border: 'border-orange-200' },
    purple: { bg: 'bg-purple-50', text: 'text-purple-500', border: 'border-purple-200' },
    pink: { bg: 'bg-pink-50', text: 'text-pink-500', border: 'border-pink-200' },
    amber: { bg: 'bg-amber-50', text: 'text-amber-500', border: 'border-amber-200' },
    blue: { bg: 'bg-blue-50', text: 'text-blue-500', border: 'border-blue-200' },
};

// Memformat angka murni menjadi format Rupiah Indonesia (contoh: 1000000 menjadi Rp 1.000.000)
const formatRupiah = (n) =>
    new Intl.NumberFormat('id-ID', {
        style: 'currency',
        currency: 'IDR',
        minimumFractionDigits: 0,
        maximumFractionDigits: 0,
    }).format(Number(n) || 0);

// Memformat nilai Rupiah bulanan menjadi nominal harian (rata-rata dibagi 30 hari)
const formatDailyRupiah = (n) => formatRupiah(Math.round((Number(n) || 0) / 30));

// Membaca pesan error dari API backend dan menerjemahkannya agar mudah dipahami pengguna
const formatApiError = (payload) => {
    if (!payload || !payload.detail) return 'Server mengembalikan error.';
    if (typeof payload.detail === 'string') return payload.detail;
    if (Array.isArray(payload.detail)) {
        return payload.detail
            .map((item) => item.msg || item.message || 'Input tidak valid.')
            .join('\n');
    }
    return 'Input tidak valid.';
};

const form = document.getElementById('budgetForm');
const submitBtn = document.getElementById('submitBtn');
const loadingState = document.getElementById('loadingState');
const emptyState = document.getElementById('emptyState');
const resultsContainer = document.getElementById('resultsContainer');
const numChildrenInput = document.getElementById('numChildren');
const childrenAgesContainer = document.getElementById('childrenAgesContainer');
const childrenAgesInputs = document.getElementById('childrenAgesInputs');
const maritalStatusSelect = document.getElementById('maritalStatus');
const familySection = document.getElementById('familySection');
const userTypeSelect = document.getElementById('userType');
const errorPanel = document.getElementById('errorPanel');
const errorMessage = document.getElementById('errorMessage');
let chartInstance = null;

// Membaca nilai input formulir secara aman, menghapus karakter non-angka, dan mengembalikannya sebagai angka murni
const optionalNumber = (id) => {
    const value = document.getElementById(id).value.replace(/\D/g, '');
    return value === '' ? null : Math.max(0, parseInt(value, 10) || 0);
};

// Mengosongkan seluruh elemen anak (child nodes) dari suatu elemen HTML
const clearNode = (node) => {
    while (node.firstChild) node.removeChild(node.firstChild);
};

// Menambahkan teks baru secara aman ke dalam elemen HTML tanpa memicu kerentanan XSS
const appendText = (parent, text) => {
    parent.appendChild(document.createTextNode(text));
};

// Membuat elemen ikon FontAwesome secara dinamis menggunakan daftar ikon yang diizinkan
const createIcon = (icon, className = '') => {
    const safeIcon = allowedIcons.has(icon) ? icon : 'shield-alt';
    const el = document.createElement('i');
    el.className = `fas fa-${safeIcon} ${className}`.trim();
    return el;
};

// Mengubah tombol hitung rekomendasi menjadi loading/spinner (mencegah klik ganda saat memproses data)
const setButtonLoading = (isLoading) => {
    submitBtn.disabled = isLoading;
    clearNode(submitBtn);
    if (isLoading) {
        const loader = document.createElement('div');
        loader.className = 'loader w-5 h-5 border-2 border-white/30';
        loader.style.borderTopColor = 'white';
        const text = document.createElement('span');
        text.className = 'ml-2';
        text.textContent = 'Memproses...';
        submitBtn.append(loader, text);
        return;
    }
    submitBtn.append(createIcon('magic', 'mr-2'));
    appendText(submitBtn, 'Hitung Rekomendasi');
};

// Menampilkan banner pesan error di atas form jika terjadi kendala input atau jaringan
const showError = (message) => {
    errorMessage.textContent = message;
    errorPanel.classList.remove('hidden');
};

// Menyembunyikan kembali banner pesan error yang sedang tampil
const hideError = () => {
    errorMessage.textContent = '';
    errorPanel.classList.add('hidden');
};

// Membuat kotak kontainer untuk membungkus ikon agar tampil rapi dan estetik
const makeIconBox = (icon, className) => {
    const box = document.createElement('div');
    box.className = className;
    box.appendChild(createIcon(icon));
    return box;
};

// Membuat kartu rincian kebutuhan pokok (Needs) seperti Makan, Transportasi, Listrik, dll.
const createInfoCard = (item) => {
    const div = document.createElement('div');
    div.className = 'bg-white rounded-xl p-3 border border-slate-100 hover:border-blue-200 transition-colors';

    const header = document.createElement('div');
    header.className = 'flex items-center mb-1.5';
    const name = document.createElement('span');
    name.className = 'text-xs font-semibold text-slate-600';
    name.textContent = item.name || '-';
    header.append(makeIconBox(item.icon, 'w-7 h-7 rounded-lg bg-blue-50 text-blue-500 flex items-center justify-center mr-2 text-xs'), name);

    const amount = document.createElement('p');
    amount.className = 'text-base font-bold text-slate-800';
    amount.textContent = formatRupiah(item.amount);

    const desc = document.createElement('p');
    desc.className = 'text-[11px] text-slate-400 mt-0.5';
    desc.textContent = item.desc || '';

    div.append(header, amount, desc);
    return div;
};

// Membuat kartu peringatan darurat/waspada jika rasio pengeluaran melebihi batas sehat
const createWarning = (message) => {
    const div = document.createElement('div');
    div.className = 'bg-red-50 border border-red-200 rounded-xl p-4 flex items-start text-sm text-red-700';
    div.appendChild(createIcon('exclamation-triangle', 'mt-0.5 mr-3 text-red-400'));
    const span = document.createElement('span');
    span.textContent = message;
    div.appendChild(span);
    return div;
};

// Membuat kartu rincian keinginan (Wants) lengkap dengan estimasi rata-rata transaksi dan saran frekuensi bulanan
const createWantsCard = (item) => {
    const color = colorMap[item.color] || colorMap.orange;
    const div = document.createElement('div');
    div.className = `bg-white rounded-xl p-5 border ${color.border} hover:shadow-md transition-all group`;

    const header = document.createElement('div');
    header.className = 'flex items-center justify-between mb-2 gap-3';

    const left = document.createElement('div');
    left.className = 'flex items-center min-w-0';
    const iconBox = makeIconBox(
        item.icon,
        `w-10 h-10 rounded-xl ${color.bg} ${color.text} flex items-center justify-center text-lg mr-3 group-hover:scale-110 transition-transform shrink-0`
    );
    const titleWrap = document.createElement('div');
    titleWrap.className = 'min-w-0';
    const title = document.createElement('h4');
    title.className = 'font-bold text-slate-800 text-sm';
    title.textContent = item.category || '-';
    titleWrap.appendChild(title);
    left.append(iconBox, titleWrap);

    const budget = document.createElement('span');
    budget.className = `text-sm font-bold ${color.text} shrink-0`;
    budget.textContent = formatRupiah(item.budget);

    const details = document.createElement('p');
    details.className = 'text-sm text-slate-500 leading-relaxed pl-0 sm:pl-[52px] mt-2 sm:mt-0';
    details.textContent = item.details || '';

    header.append(left, budget);
    div.append(header, details);
    return div;
};

// Membuat kartu tips alokasi tabungan (Dana Darurat, Investasi, Asuransi Proteksi)
const createSavingsCard = (tip) => {
    const div = document.createElement('div');
    div.className = 'bg-white rounded-xl p-4 border border-green-100 hover:border-green-300 transition-colors';

    const header = document.createElement('div');
    header.className = 'flex items-center mb-2';
    const name = document.createElement('span');
    name.className = 'text-sm font-bold text-slate-700';
    name.textContent = tip.name || '-';
    header.append(makeIconBox(tip.icon, 'w-8 h-8 rounded-lg bg-green-50 text-green-500 flex items-center justify-center mr-2'), name);

    const amount = document.createElement('p');
    amount.className = 'text-lg font-bold text-green-600 mb-1';
    amount.textContent = formatRupiah(tip.amount);

    const desc = document.createElement('p');
    desc.className = 'text-xs text-slate-400 leading-relaxed';
    desc.textContent = tip.desc || '';

    div.append(header, amount, desc);
    return div;
};

// Menambahkan kotak input usia anak secara dinamis di form parameter keluarga sesuai jumlah anak
const addChildAgeInput = (index) => {
    const div = document.createElement('div');
    div.className = 'relative';
    div.appendChild(createIcon('birthday-cake', 'input-icon-left text-slate-400'));

    const input = document.createElement('input');
    input.type = 'number';
    input.min = '0';
    input.max = '25';
    input.value = '5';
    input.className = 'inp pl-11 child-age-input';
    input.placeholder = `Usia anak ke-${index + 1}`;
    div.appendChild(input);

    childrenAgesInputs.appendChild(div);
};

maritalStatusSelect.addEventListener('change', () => {
    if (maritalStatusSelect.value === 'berkeluarga') {
        familySection.classList.remove('hidden');
        familySection.style.maxHeight = familySection.scrollHeight + 200 + 'px';
    } else {
        familySection.classList.add('hidden');
        document.getElementById('familySize').value = 1;
        numChildrenInput.value = 0;
        clearNode(childrenAgesInputs);
        childrenAgesContainer.classList.add('hidden');
    }
});

userTypeSelect.addEventListener('change', () => {
    if (userTypeSelect.value === 'anak_kos') {
        maritalStatusSelect.value = 'lajang';
        maritalStatusSelect.dispatchEvent(new Event('change'));
        document.getElementById('housing').value = 'kos';
    } else if (userTypeSelect.value.startsWith('keluarga')) {
        maritalStatusSelect.value = 'berkeluarga';
        maritalStatusSelect.dispatchEvent(new Event('change'));
        if (userTypeSelect.value === 'keluarga_anak_sekolah' && (parseInt(numChildrenInput.value, 10) || 0) === 0) {
            numChildrenInput.value = 1;
            numChildrenInput.dispatchEvent(new Event('input'));
        }
    }
});

numChildrenInput.addEventListener('input', () => {
    const n = parseInt(numChildrenInput.value, 10) || 0;
    clearNode(childrenAgesInputs);
    if (n > 0) {
        childrenAgesContainer.classList.remove('hidden');
        for (let i = 0; i < n; i++) addChildAgeInput(i);
    } else {
        childrenAgesContainer.classList.add('hidden');
    }
});

form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const income = parseInt(document.getElementById('income').value.replace(/\D/g, ''), 10);
    const profile = document.getElementById('profile').value;
    const userType = document.getElementById('userType').value;
    const cityTier = document.getElementById('cityTier').value;
    const budgetMode = document.getElementById('budgetMode').value;
    const isFamily = maritalStatusSelect.value === 'berkeluarga';
    const familySizeInput = document.getElementById('familySize');
    let familySize = isFamily ? (parseInt(familySizeInput.value, 10) || 2) : 1;
    const numChildren = isFamily ? (parseInt(numChildrenInput.value, 10) || 0) : 0;
    const vehicle = document.getElementById('vehicle').value;
    const housing = document.getElementById('housing').value;
    const waterSource = document.getElementById('waterSource').value;

    const childrenAges = [];
    document.querySelectorAll('.child-age-input').forEach((el) => {
        childrenAges.push(parseInt(el.value, 10) || 5);
    });

    if (isFamily && familySize <= numChildren) {
        familySize = numChildren + 1;
        familySizeInput.value = familySize;
    }

    hideError();
    emptyState.classList.add('hidden');
    resultsContainer.classList.add('hidden');
    loadingState.classList.remove('hidden');
    setButtonLoading(true);

    try {
        const res = await fetch(`${API_BASE_URL}/predict_budget`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                income,
                profile,
                user_type: userType,
                city_tier: cityTier,
                budget_mode: budgetMode,
                family_size: familySize,
                num_children: numChildren,
                children_ages: childrenAges,
                has_vehicle: vehicle,
                housing_type: housing,
                water_source: waterSource,
                fixed_housing_cost: optionalNumber('fixedHousing'),
                fixed_electricity_cost: optionalNumber('fixedElectricity'),
                fixed_water_cost: optionalNumber('fixedWater'),
                fixed_internet_cost: optionalNumber('fixedInternet'),
                fixed_transport_cost: optionalNumber('fixedTransport'),
            }),
        });

        if (!res.ok) {
            const payload = await res.json().catch(() => null);
            throw new Error(formatApiError(payload));
        }

        const json = await res.json();
        lastCalculationData = {
            name: '',
            timestamp: Date.now(),
            input: {
                income,
                profile,
                userType,
                cityTier,
                budgetMode,
                familySize,
                numChildren,
                childrenAges,
                vehicle,
                housing,
                waterSource,
                fixedHousing: optionalNumber('fixedHousing'),
                fixedElectricity: optionalNumber('fixedElectricity'),
                fixedWater: optionalNumber('fixedWater'),
                fixedInternet: optionalNumber('fixedInternet'),
                fixedTransport: optionalNumber('fixedTransport'),
            },
            result: json.data,
            originalResult: JSON.parse(JSON.stringify(json.data))
        };
        renderResult(json.data, profile);
        setTimeout(() => {
            loadingState.classList.add('hidden');
            resultsContainer.classList.remove('hidden');
            resultsContainer.scrollIntoView({ behavior: 'smooth' });
        }, 250);
    } catch (err) {
        console.error(err);
        const message = err.message === 'Failed to fetch'
            ? `Gagal memanggil API di ${API_BASE_URL}. Pastikan server FastAPI berjalan.`
            : err.message;
        showError(message);
        loadingState.classList.add('hidden');
        emptyState.classList.remove('hidden');
    } finally {
        setButtonLoading(false);
    }
});

// Memperbarui posisi slider anggaran (Kebutuhan, Keinginan, Tabungan) dan memperbarui label angka persentase
function updateSliderUI(needs_pct, wants_pct, savings_pct) {
    const needsSlider = document.getElementById('needsSlider');
    const wantsSlider = document.getElementById('wantsSlider');
    const savingsSlider = document.getElementById('savingsSlider');
    const needsSliderVal = document.getElementById('needsSliderVal');
    const wantsSliderVal = document.getElementById('wantsSliderVal');
    const savingsSliderVal = document.getElementById('savingsSliderVal');

    if (needsSlider) needsSlider.value = needs_pct;
    if (wantsSlider) wantsSlider.value = wants_pct;
    if (savingsSlider) savingsSlider.value = savings_pct;
    
    if (needsSliderVal) needsSliderVal.textContent = `${needs_pct}%`;
    if (wantsSliderVal) wantsSliderVal.textContent = `${wants_pct}%`;
    if (savingsSliderVal) savingsSliderVal.textContent = `${savings_pct}%`;
}

// Merender daftar detail kebutuhan pokok (Needs) di bawah hasil ringkasan anggaran
function renderNeedsDetailList(needs_detail, needs_total_estimated, is_budget_adjusted) {
    const ndGrid = document.getElementById('needsDetailGrid');
    clearNode(ndGrid);
    (needs_detail || []).forEach((item) => ndGrid.appendChild(createInfoCard(item)));

    document.getElementById('needsTotalEstimated').textContent = formatRupiah(needs_total_estimated);
    document.getElementById('needsTotalLabel').textContent = is_budget_adjusted
        ? `Total Kebutuhan Sesuai Budget / Bulan (${formatDailyRupiah(needs_total_estimated)}/hari)`
        : `Total Estimasi Kebutuhan / Bulan (${formatDailyRupiah(needs_total_estimated)}/hari)`;
}

// Merender daftar detail anggaran keinginan (Wants) beserta batas frekuensi jajannya
function renderWantsItemsList(wants_items) {
    const wList = document.getElementById('wantsItemsList');
    clearNode(wList);
    (wants_items || []).forEach((item) => wList.appendChild(createWantsCard(item)));
}

// Merender daftar tips alokasi tabungan dan investasi di dashboard
function renderSavingsTipsList(savings_tips) {
    const sList = document.getElementById('savingsTipsList');
    clearNode(sList);
    (savings_tips || []).forEach((tip) => sList.appendChild(createSavingsCard(tip)));
}

// Fungsi utama untuk menampilkan seluruh hasil rekomendasi anggaran (kartu, chart, saran) dari API backend ke layar
function renderResult(d, fallbackProfile) {
    const warnC = document.getElementById('warningsContainer');
    clearNode(warnC);
    if (d.warnings && d.warnings.length) {
        warnC.classList.remove('hidden');
        d.warnings.forEach((warning) => warnC.appendChild(createWarning(warning)));
    } else {
        warnC.classList.add('hidden');
    }

    const healthBadgeContainer = document.getElementById('healthBadgeContainer');
    if (healthBadgeContainer && d.budget_health) {
        clearNode(healthBadgeContainer);
        const badge = document.createElement('span');
        const status = d.budget_health.status || 'aman';
        let bg = 'bg-green-50 text-green-700 border-green-200';
        if (status === 'waspada') bg = 'bg-amber-50 text-amber-700 border-amber-200';
        if (status === 'kritis') bg = 'bg-red-50 text-red-700 border-red-200';
        
        badge.className = `inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${bg}`;
        badge.textContent = `STATUS: ${status.toUpperCase()}`;
        
        const msgSpan = document.createElement('span');
        msgSpan.className = 'text-xs text-slate-500 font-medium';
        msgSpan.textContent = d.budget_health.message || '';
        
        healthBadgeContainer.append(badge, msgSpan);
    }

    document.getElementById('needsAmount').textContent = formatRupiah(d.budget_rule.needs);
    document.getElementById('wantsAmount').textContent = formatRupiah(d.budget_rule.wants);
    document.getElementById('savingsAmount').textContent = formatRupiah(d.budget_rule.savings);
    document.getElementById('needsPct2').textContent = d.budget_rule.needs_pct;
    document.getElementById('wantsPct2').textContent = d.budget_rule.wants_pct;
    document.getElementById('savingsPct2').textContent = d.budget_rule.savings_pct;
    document.getElementById('needsPctLabel').textContent = `${d.budget_rule.needs_pct}%`;
    document.getElementById('wantsPctLabel').textContent = `${d.budget_rule.wants_pct}%`;
    document.getElementById('savingsPctLabel').textContent = `${d.budget_rule.savings_pct}%`;
    document.getElementById('displayProfile').textContent = d.profile_used || fallbackProfile;

    renderChart(d.budget_rule.needs, d.budget_rule.wants, d.budget_rule.savings);

    renderNeedsDetailList(d.needs_detail, d.needs_total_estimated, d.is_budget_adjusted);
    renderWantsItemsList(d.wants_items);
    renderSavingsTipsList(d.savings_tips);
    calculateGoal();

    updateSliderUI(d.budget_rule.needs_pct, d.budget_rule.wants_pct, d.budget_rule.savings_pct);
}

// Memformat deskripsi limit transaksi (contoh: "Makan di luar maks 6x/bulan (Est. Rp 100.000/transaksi)")
function formatLimitDesc(category, freq, avgAmount) {
    if (category === "Donasi & Amal") {
        return "Sisihkan untuk sedekah/zakat agar rezeki makin berkah.";
    }
    let label = "";
    if (category === "Makan & Minum") label = "Makan di luar / delivery";
    else if (category === "Hiburan") label = "Aktivitas hiburan/streaming";
    else if (category === "Pakaian & Fashion") label = "Belanja pakaian";
    else if (category === "Perawatan Diri") label = "Skincare/salon/barbershop";
    else return `Alokasi untuk ${category} (rata-rata ${formatRupiah(avgAmount)}).`;

    if (freq <= 0) {
        return `Budget belum cukup untuk 1 transaksi rata-rata (Est. ${formatRupiah(avgAmount)}). Pilih opsi gratis atau lebih murah.`;
    }
    return `${label} maks ${freq}x/bulan (Est. ${formatRupiah(avgAmount)}/transaksi).`;
}

// Menghitung status pencapaian target impian finansial secara real-time berdasarkan alokasi tabungan
function calculateGoal() {
    const goalNameInput = document.getElementById('goalName');
    const goalAmountInput = document.getElementById('goalAmount');
    const goalMonthsInput = document.getElementById('goalMonths');
    const analysisContainer = document.getElementById('goalAnalysisContainer');
    
    if (!goalNameInput || !goalAmountInput || !goalMonthsInput || !analysisContainer) return;
    
    const goalName = goalNameInput.value.trim();
    const goalAmountVal = goalAmountInput.value.replace(/\D/g, '');
    const goalMonthsVal = parseInt(goalMonthsInput.value, 10);
    
    if (!goalName || !goalAmountVal || !goalMonthsVal || goalMonthsVal <= 0) {
        analysisContainer.classList.add('hidden');
        clearNode(analysisContainer);
        return;
    }
    
    const goalAmount = parseInt(goalAmountVal, 10);
    if (!lastCalculationData || !lastCalculationData.result) return;
    
    const savingsBudget = lastCalculationData.result.budget_rule.savings;
    const requiredSavings = Math.round(goalAmount / goalMonthsVal);
    const actualMonths = savingsBudget > 0 ? Math.ceil(goalAmount / savingsBudget) : Infinity;
    
    const isFeasible = savingsBudget >= requiredSavings;
    
    // Merender hasil analisis kelayakan target impian finansial ke layar beserta progress bar pencapaian
function renderGoalUI(status, message) {
        clearNode(analysisContainer);
        analysisContainer.classList.remove('hidden');
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'flex items-start space-x-3 text-xs leading-relaxed';
        
        let iconName = 'triangle-exclamation';
        let bgClass = 'bg-amber-50 border-amber-200 text-amber-800';
        let iconClass = 'text-amber-500';
        
        if (status === 'success') {
            iconName = 'circle-check';
            bgClass = 'bg-green-50 border-green-200 text-green-800';
            iconClass = 'text-green-500';
        }
        
        analysisContainer.className = `p-4 rounded-xl border transition-all duration-300 ${bgClass}`;
        
        const icon = createIcon(iconName, `text-base mt-0.5 ${iconClass}`);
        const textWrapper = document.createElement('div');
        textWrapper.className = 'flex-1';
        
        const statusTitle = document.createElement('p');
        statusTitle.className = 'font-bold uppercase tracking-wider mb-1';
        statusTitle.textContent = status === 'success' ? 'Target Tercapai!' : 'Alokasi Tabungan Kurang';
        
        const descText = document.createElement('p');
        descText.className = 'font-medium';
        descText.textContent = message;
        
        textWrapper.append(statusTitle, descText);
        contentDiv.append(icon, textWrapper);
        analysisContainer.appendChild(contentDiv);
    }
    
    const context = `Target impian: ${goalName}, harga: Rp ${goalAmount}, durasi target: ${goalMonthsVal} bulan. Status kelayakan tabungan saat ini: ${isFeasible ? 'cukup' : 'kurang'}.`;
    
    const fallbackMsg = isFeasible
        ? `Hebat! Tabungan bulanan Anda saat ini (${formatRupiah(savingsBudget)}) sangat cukup untuk membeli ${goalName} seharga ${formatRupiah(goalAmount)} dalam waktu ${goalMonthsVal} bulan. Bahkan, target Anda akan tercapai dalam ${actualMonths} bulan!`
        : `Waduh, alokasi tabungan bulanan Anda saat ini (${formatRupiah(savingsBudget)}) masih kurang ${formatRupiah(requiredSavings - savingsBudget)} per bulan untuk membeli ${goalName} seharga ${formatRupiah(goalAmount)} dalam ${goalMonthsVal} bulan. Butuh sekitar ${actualMonths} bulan untuk mencapainya dengan alokasi saat ini.`;
        
    renderGoalUI(isFeasible ? 'success' : 'warning', fallbackMsg);
    
    fetch(`${API_BASE_URL}/refine_text`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: fallbackMsg, context: context })
    })
    .then(res => res.json())
    .then(json => {
        if (json.status === 'success' && json.refined_text) {
            renderGoalUI(isFeasible ? 'success' : 'warning', json.refined_text);
        }
    })
    .catch(err => console.error("Error refining text with Gemini:", err));
}

// Menghitung ulang rupiah per pos secara lokal (sisi klien) saat pengguna menggeser slider anggaran kustom
function recalculateCustomBudget(needsPct, wantsPct, savingsPct) {
    if (!lastCalculationData) return;

    const income = lastCalculationData.input.income;
    const originalResult = lastCalculationData.originalResult;

    // 1. Calculate new top level rule amounts
    const needsBudget = Math.round(income * needsPct / 100);
    const wantsBudget = Math.round(income * wantsPct / 100);
    const savingsBudget = income - needsBudget - wantsBudget;

    // Update budget rule values in the result copy we will render
    const resultCopy = lastCalculationData.result;
    resultCopy.budget_rule.needs = needsBudget;
    resultCopy.budget_rule.wants = wantsBudget;
    resultCopy.budget_rule.savings = savingsBudget;
    resultCopy.budget_rule.needs_pct = needsPct;
    resultCopy.budget_rule.wants_pct = wantsPct;
    resultCopy.budget_rule.savings_pct = savingsPct;

    // 2. Recalculate Needs details (Option 2 protection logic)
    const fixedKeysMap = {
        "Tempat Tinggal": lastCalculationData.input.fixedHousing,
        "Listrik": lastCalculationData.input.fixedElectricity,
        "Air/Air Minum": lastCalculationData.input.fixedWater,
        "Internet": lastCalculationData.input.fixedInternet,
        "Transportasi": lastCalculationData.input.fixedTransport
    };

    const originalNeedsDetail = originalResult.needs_detail || [];
    const newNeedsDetail = originalNeedsDetail.map(item => {
        const raw = (item.raw_amount !== undefined && item.raw_amount !== null) ? item.raw_amount : item.amount;
        return {
            name: item.name,
            raw_amount: raw,
            amount: raw,
            desc: item.desc,
            icon: item.icon
        };
    });

    // Separate fixed vs variable
    const fixedItems = [];
    const variableItems = [];

    newNeedsDetail.forEach(item => {
        if (fixedKeysMap.hasOwnProperty(item.name) && fixedKeysMap[item.name] !== null && fixedKeysMap[item.name] !== undefined) {
            fixedItems.push(item);
        } else {
            variableItems.push(item);
        }
    });

    const fixedTotal = fixedItems.reduce((sum, item) => sum + item.raw_amount, 0);
    const variableTotal = variableItems.reduce((sum, item) => sum + item.raw_amount, 0);

    if (fixedTotal > needsBudget) {
        // Force all variables to 0
        variableItems.forEach(item => {
            item.amount = 0;
        });

        // Scale fixed items down to fit needsBudget
        if (fixedTotal > 0) {
            const scaleFixed = needsBudget / fixedTotal;
            let scaledFixedTotal = 0;
            fixedItems.forEach((item, idx) => {
                if (idx === fixedItems.length - 1) {
                    item.amount = needsBudget - scaledFixedTotal;
                } else {
                    item.amount = Math.round(item.raw_amount * scaleFixed);
                    scaledFixedTotal += item.amount;
                }
            });
        }
    } else {
        // Keep all fixed items at 100%
        fixedItems.forEach(item => {
            item.amount = item.raw_amount;
        });

        // Scale variable items to fit the remaining needsBudget
        const remainingNeedsBudget = needsBudget - fixedTotal;
        if (variableTotal > 0) {
            const scaleVar = remainingNeedsBudget / variableTotal;
            let scaledVarTotal = 0;
            variableItems.forEach((item, idx) => {
                if (idx === variableItems.length - 1) {
                    item.amount = remainingNeedsBudget - scaledVarTotal;
                } else {
                    item.amount = Math.round(item.raw_amount * scaleVar);
                    scaledVarTotal += item.amount;
                }
            });
        } else {
            variableItems.forEach(item => {
                item.amount = 0;
            });
        }
    }

    // Update needs_detail and needs_total_estimated in resultCopy
    resultCopy.needs_detail = newNeedsDetail;
    resultCopy.needs_total_estimated = newNeedsDetail.reduce((sum, item) => sum + item.amount, 0);
    resultCopy.is_budget_adjusted = resultCopy.needs_total_estimated < originalResult.normal_needs_total;

    // 3. Recalculate Wants breakdown
    const originalWantsItems = originalResult.wants_items || [];
    const newWantsItems = originalWantsItems.map(item => {
        const initialWantsBudget = originalResult.budget_rule.wants;
        const weight = initialWantsBudget > 0 ? (item.budget / initialWantsBudget) : 0;
        const catBudget = Math.round(wantsBudget * weight);
        const avgTx = item.avg_transaction || 100000;
        const freq = Math.floor(catBudget / avgTx);
        const desc = formatLimitDesc(item.category, freq, avgTx);

        return {
            category: item.category,
            budget: catBudget,
            avg_transaction: avgTx,
            icon: item.icon,
            color: item.color,
            details: desc
        };
    });
    resultCopy.wants_items = newWantsItems;

    // 4. Recalculate Savings tips
    const originalSavingsTips = originalResult.savings_tips || [];
    const newSavingsTips = originalSavingsTips.map(item => {
        let amount = 0;
        if (item.name === "Dana Darurat") {
            amount = Math.round(savingsBudget * 0.50);
        } else if (item.name === "Investasi") {
            amount = Math.round(savingsBudget * 0.30);
        } else {
            const ddAmount = Math.round(savingsBudget * 0.50);
            const invAmount = Math.round(savingsBudget * 0.30);
            amount = Math.max(0, savingsBudget - ddAmount - invAmount);
        }
        return {
            name: item.name,
            amount: amount,
            icon: item.icon,
            desc: item.desc
        };
    });
    resultCopy.savings_tips = newSavingsTips;

    // Render components
    renderNeedsDetailList(resultCopy.needs_detail, resultCopy.needs_total_estimated, resultCopy.is_budget_adjusted);
    renderWantsItemsList(resultCopy.wants_items);
    renderSavingsTipsList(resultCopy.savings_tips);

    // Update main cards, charts and labels
    document.getElementById('needsAmount').textContent = formatRupiah(resultCopy.budget_rule.needs);
    document.getElementById('wantsAmount').textContent = formatRupiah(resultCopy.budget_rule.wants);
    document.getElementById('savingsAmount').textContent = formatRupiah(resultCopy.budget_rule.savings);
    document.getElementById('needsPct2').textContent = resultCopy.budget_rule.needs_pct;
    document.getElementById('wantsPct2').textContent = resultCopy.budget_rule.wants_pct;
    document.getElementById('savingsPct2').textContent = resultCopy.budget_rule.savings_pct;
    document.getElementById('needsPctLabel').textContent = `${resultCopy.budget_rule.needs_pct}%`;
    document.getElementById('wantsPctLabel').textContent = `${resultCopy.budget_rule.wants_pct}%`;
    document.getElementById('savingsPctLabel').textContent = `${resultCopy.budget_rule.savings_pct}%`;

    renderChart(resultCopy.budget_rule.needs, resultCopy.budget_rule.wants, resultCopy.budget_rule.savings);
    calculateGoal();
}

// Mengatur sinkronisasi ketiga slider (Kebutuhan, Keinginan, Tabungan) agar total persentase selalu pas 100%
function handleSliderInput(changedId) {
    const needsSlider = document.getElementById('needsSlider');
    const wantsSlider = document.getElementById('wantsSlider');
    const savingsSlider = document.getElementById('savingsSlider');

    let needsVal = parseInt(needsSlider.value, 10) || 0;
    let wantsVal = parseInt(wantsSlider.value, 10) || 0;
    let savingsVal = parseInt(savingsSlider.value, 10) || 0;

    let total = needsVal + wantsVal + savingsVal;
    let diff = 100 - total;

    if (diff !== 0) {
        let adjustables = [];
        if (changedId !== 'needsSlider') adjustables.push({ id: 'needsSlider', val: needsVal, min: 10, max: 85, setVal: (v) => { needsVal = v; } });
        if (changedId !== 'wantsSlider') adjustables.push({ id: 'wantsSlider', val: wantsVal, min: 0, max: 70, setVal: (v) => { wantsVal = v; } });
        if (changedId !== 'savingsSlider') adjustables.push({ id: 'savingsSlider', val: savingsVal, min: 5, max: 50, setVal: (v) => { savingsVal = v; } });

        let sumOthers = adjustables.reduce((acc, curr) => acc + curr.val, 0);
        
        if (sumOthers > 0) {
            let remainingDiff = diff;
            adjustables.forEach((adj, idx) => {
                let change = 0;
                if (idx === adjustables.length - 1) {
                    change = remainingDiff;
                } else {
                    change = Math.round(diff * (adj.val / sumOthers));
                    remainingDiff -= change;
                }
                let newVal = adj.val + change;
                newVal = Math.max(adj.min, Math.min(adj.max, newVal));
                adj.setVal(newVal);
            });
        } else {
            let remainingDiff = diff;
            adjustables.forEach((adj, idx) => {
                let change = 0;
                if (idx === adjustables.length - 1) {
                    change = remainingDiff;
                } else {
                    change = Math.round(diff / adjustables.length);
                    remainingDiff -= change;
                }
                let newVal = adj.val + change;
                newVal = Math.max(adj.min, Math.min(adj.max, newVal));
                adj.setVal(newVal);
            });
        }

        let currentTotal = needsVal + wantsVal + savingsVal;
        let finalDiff = 100 - currentTotal;
        if (finalDiff !== 0) {
            let targetAdj = adjustables.find(adj => {
                let testVal = adj.val + finalDiff;
                return testVal >= adj.min && testVal <= adj.max;
            });
            if (targetAdj) {
                targetAdj.setVal(targetAdj.val + finalDiff);
            } else {
                let firstAdj = adjustables[0];
                firstAdj.setVal(Math.max(firstAdj.min, Math.min(firstAdj.max, firstAdj.val + finalDiff)));
            }
        }
    }

    updateSliderUI(needsVal, wantsVal, savingsVal);
    recalculateCustomBudget(needsVal, wantsVal, savingsVal);
}

// Menggambar bagan donat (donut chart) pembagian anggaran menggunakan Chart.js
function renderChart(needs, wants, savings) {
    const ctx = document.getElementById('budgetChart').getContext('2d');
    if (chartInstance) chartInstance.destroy();
    chartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Kebutuhan', 'Keinginan', 'Tabungan'],
            datasets: [{
                data: [needs, wants, savings],
                backgroundColor: ['#3b82f6', '#a855f7', '#22c55e'],
                borderWidth: 0,
                hoverOffset: 8,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '72%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: { label: (c) => ` ${formatRupiah(c.raw)}` },
                    backgroundColor: 'rgba(15,23,42,0.9)',
                    padding: 10,
                    cornerRadius: 8,
                    bodyFont: { family: 'Inter', size: 13, weight: 'bold' },
                },
            },
            animation: { animateScale: true, animateRotate: true },
        },
    });
}

// Mengaktifkan pemformat rupiah otomatis (tanda titik ribuan) secara real-time saat pengguna mengetik di kolom input
const attachRupiahFormatter = (id) => {
    const input = document.getElementById(id);
    if (!input) return;
    input.addEventListener('input', (e) => {
        let value = e.target.value.replace(/\D/g, '');
        if (value) {
            e.target.value = new Intl.NumberFormat('id-ID').format(value);
        } else {
            e.target.value = '';
        }
    });
};

['income', 'fixedHousing', 'fixedElectricity', 'fixedWater', 'fixedInternet', 'fixedTransport'].forEach(attachRupiahFormatter);

const saveScenarioBtn = document.getElementById('saveScenarioBtn');
const savedScenariosCard = document.getElementById('savedScenariosCard');
const savedScenariosList = document.getElementById('savedScenariosList');
const compareBtn = document.getElementById('compareBtn');
const compareCount = document.getElementById('compareCount');
const comparisonModal = document.getElementById('comparisonModal');
const closeComparisonBtn = document.getElementById('closeComparisonBtn');
const comparisonTableHeader = document.getElementById('comparisonTableHeader');
const comparisonTableBody = document.getElementById('comparisonTableBody');

// Merender daftar skenario anggaran yang tersimpan dari LocalStorage ke panel sisi kiri bawah
const renderSavedScenariosList = () => {
    const saved = JSON.parse(localStorage.getItem('smartbudget_scenarios') || '[]');
    if (saved.length === 0) {
        savedScenariosCard.classList.add('hidden');
        return;
    }
    
    savedScenariosCard.classList.remove('hidden');
    clearNode(savedScenariosList);
    
    saved.forEach((scenario, index) => {
        const item = document.createElement('div');
        item.className = 'flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-100 hover:border-blue-100 transition-all text-xs';
        
        const left = document.createElement('div');
        left.className = 'flex items-center space-x-2.5 min-w-0';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'scenario-compare-checkbox w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500 cursor-pointer';
        checkbox.dataset.index = index;
        checkbox.addEventListener('change', updateCompareButtonState);
        
        const details = document.createElement('div');
        details.className = 'min-w-0';
        const name = document.createElement('p');
        name.className = 'font-bold text-slate-800 truncate';
        name.textContent = scenario.name;
        
        const meta = document.createElement('p');
        meta.className = 'text-[10px] text-slate-400 mt-0.5';
        meta.textContent = `${formatRupiah(scenario.input.income)} | Needs: ${scenario.result.budget_rule.needs_pct}%`;
        
        details.append(name, meta);
        left.append(checkbox, details);
        
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'text-slate-400 hover:text-red-500 transition-colors p-1.5 hover:bg-slate-100 rounded-lg shrink-0';
        deleteBtn.innerHTML = '<i class="fas fa-trash-can"></i>';
        deleteBtn.addEventListener('click', () => {
            if (confirm(`Apakah Anda yakin ingin menghapus skenario "${scenario.name}"?`)) {
                saved.splice(index, 1);
                localStorage.setItem('smartbudget_scenarios', JSON.stringify(saved));
                renderSavedScenariosList();
                updateCompareButtonState();
            }
        });
        
        item.append(left, deleteBtn);
        savedScenariosList.appendChild(item);
    });
};

// Memperbarui status tombol bandingkan (aktif jika minimal ada 2 skenario yang dicentang)
const updateCompareButtonState = () => {
    const checkboxes = document.querySelectorAll('.scenario-compare-checkbox:checked');
    const count = checkboxes.length;
    compareCount.textContent = count;
    
    if (count >= 2) {
        compareBtn.classList.remove('hidden');
    } else {
        compareBtn.classList.add('hidden');
    }
};

saveScenarioBtn.addEventListener('click', () => {
    if (!lastCalculationData) return;
    
    const scenarioName = prompt('Masukkan nama skenario (contoh: Kos Jakarta Timur):');
    if (!scenarioName) return;
    const cleanName = scenarioName.trim();
    if (!cleanName) return;
    
    const saved = JSON.parse(localStorage.getItem('smartbudget_scenarios') || '[]');
    if (saved.some(s => s.name.toLowerCase() === cleanName.toLowerCase())) {
        alert('Skenario dengan nama tersebut sudah ada. Harap gunakan nama lain.');
        return;
    }
    
    lastCalculationData.name = cleanName;
    lastCalculationData.timestamp = Date.now();
    saved.push(lastCalculationData);
    localStorage.setItem('smartbudget_scenarios', JSON.stringify(saved));
    
    alert(`Skenario "${cleanName}" berhasil disimpan!`);
    renderSavedScenariosList();
});

closeComparisonBtn.addEventListener('click', () => {
    comparisonModal.classList.add('hidden');
});

compareBtn.addEventListener('click', () => {
    const saved = JSON.parse(localStorage.getItem('smartbudget_scenarios') || '[]');
    const checkedIndexes = Array.from(document.querySelectorAll('.scenario-compare-checkbox:checked'))
        .map(el => parseInt(el.dataset.index, 10));
        
    const selectedScenarios = checkedIndexes.map(idx => saved[idx]);
    if (selectedScenarios.length < 2) return;
    
    clearNode(comparisonTableHeader);
    clearNode(comparisonTableBody);
    
    const firstTh = document.createElement('th');
    firstTh.className = 'py-4 px-5 w-[200px]';
    firstTh.textContent = 'Kriteria / Pos';
    comparisonTableHeader.appendChild(firstTh);
    
    selectedScenarios.forEach(s => {
        const th = document.createElement('th');
        th.className = 'py-4 px-5 font-bold text-slate-800';
        th.textContent = s.name;
        comparisonTableHeader.appendChild(th);
    });
    
    // Helper untuk menambahkan baris baru pada tabel perbandingan skenario side-by-side
const addRow = (label, valueExtractor, isHeader = false) => {
        const tr = document.createElement('tr');
        tr.className = isHeader ? 'bg-slate-50/50 font-bold border-t border-slate-200' : 'hover:bg-slate-50/30';
        
        const tdLabel = document.createElement('td');
        tdLabel.className = 'py-3.5 px-5 text-slate-500 font-semibold';
        tdLabel.textContent = label;
        tr.appendChild(tdLabel);
        
        selectedScenarios.forEach(s => {
            const tdVal = document.createElement('td');
            tdVal.className = 'py-3.5 px-5 text-slate-800';
            
            const extracted = valueExtractor(s);
            if (extracted instanceof HTMLElement) {
                tdVal.appendChild(extracted);
            } else {
                tdVal.textContent = extracted;
            }
            tr.appendChild(tdVal);
        });
        
        comparisonTableBody.appendChild(tr);
    };
    
    addRow('Pendapatan Bulanan', s => formatRupiah(s.input.income));
    
    addRow('ALOKASI ANGGARAN (50/30/20)', s => '', true);
    addRow('Kebutuhan (Needs)', s => `${formatRupiah(s.result.budget_rule.needs)} (${s.result.budget_rule.needs_pct}%)`);
    addRow('Keinginan (Wants)', s => `${formatRupiah(s.result.budget_rule.wants)} (${s.result.budget_rule.wants_pct}%)`);
    addRow('Tabungan (Savings)', s => `${formatRupiah(s.result.budget_rule.savings)} (${s.result.budget_rule.savings_pct}%)`);
    
    addRow('BIAYA TETAP MANUAL', s => '', true);
    addRow('Sewa / Cicilan', s => s.input.fixedHousing !== null ? formatRupiah(s.input.fixedHousing) : 'Otomatis');
    addRow('Listrik', s => s.input.fixedElectricity !== null ? formatRupiah(s.input.fixedElectricity) : 'Otomatis');
    addRow('Air', s => s.input.fixedWater !== null ? formatRupiah(s.input.fixedWater) : 'Otomatis');
    addRow('Internet', s => s.input.fixedInternet !== null ? formatRupiah(s.input.fixedInternet) : 'Otomatis');
    addRow('Transport', s => s.input.fixedTransport !== null ? formatRupiah(s.input.fixedTransport) : 'Otomatis');
    
    addRow('LAIN-LAIN', s => '', true);
    addRow('Kategori Biaya Hidup', s => s.input.cityTier.toUpperCase());
    addRow('Profil Gaya Hidup', s => s.result.profile_used || s.input.profile);
    
    addRow('Kesehatan Keuangan', s => {
        const badge = document.createElement('span');
        const status = s.result.budget_health.status;
        let bg = 'bg-green-50 text-green-700 border-green-200';
        if (status === 'waspada') bg = 'bg-amber-50 text-amber-700 border-amber-200';
        if (status === 'kritis') bg = 'bg-red-50 text-red-700 border-red-200';
        
        badge.className = `inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${bg}`;
        badge.textContent = status.toUpperCase();
        return badge;
    });

    comparisonModal.classList.remove('hidden');
});

// Add event listeners for budget adjustment sliders
const needsSliderElement = document.getElementById('needsSlider');
const wantsSliderElement = document.getElementById('wantsSlider');
const savingsSliderElement = document.getElementById('savingsSlider');
const resetSlidersBtnElement = document.getElementById('resetSlidersBtn');

if (needsSliderElement) needsSliderElement.addEventListener('input', () => handleSliderInput('needsSlider'));
if (wantsSliderElement) wantsSliderElement.addEventListener('input', () => handleSliderInput('wantsSlider'));
if (savingsSliderElement) savingsSliderElement.addEventListener('input', () => handleSliderInput('savingsSlider'));

if (resetSlidersBtnElement) {
    resetSlidersBtnElement.addEventListener('click', () => {
        if (!lastCalculationData || !lastCalculationData.originalResult) return;
        
        // Restore copy
        lastCalculationData.result = JSON.parse(JSON.stringify(lastCalculationData.originalResult));
        
        const r = lastCalculationData.result;
        updateSliderUI(r.budget_rule.needs_pct, r.budget_rule.wants_pct, r.budget_rule.savings_pct);
        renderResult(r, lastCalculationData.input.profile);
    });
}

// Add event listeners for Goal Tracker inputs
const goalNameInput = document.getElementById('goalName');
const goalAmountInput = document.getElementById('goalAmount');
const goalMonthsInput = document.getElementById('goalMonths');

if (goalNameInput) goalNameInput.addEventListener('input', calculateGoal);
if (goalAmountInput) {
    goalAmountInput.addEventListener('input', (e) => {
        let value = e.target.value.replace(/\D/g, '');
        if (value) {
            e.target.value = new Intl.NumberFormat('id-ID').format(value);
        } else {
            e.target.value = '';
        }
        calculateGoal();
    });
}
if (goalMonthsInput) goalMonthsInput.addEventListener('input', calculateGoal);

// Add event listener for Scroll to Form button (mobile friendly)
const scrollToFormBtn = document.getElementById('scrollToFormBtn');
const formColumn = document.getElementById('formColumn');
if (scrollToFormBtn && formColumn) {
    scrollToFormBtn.addEventListener('click', () => {
        formColumn.scrollIntoView({ behavior: 'smooth' });
    });
}

renderSavedScenariosList();
