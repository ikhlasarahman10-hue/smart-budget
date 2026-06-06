(function() {
    const devUrl = 'http://127.0.0.1:8000';
    // Ganti sub-domain di bawah ini dengan Username & Nama Space Hugging Face Anda jika berbeda
    const prodUrl = 'https://ikhlasarahman10-hue-smart-budget.hf.space'; 

    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

    window.SMART_BUDGET_CONFIG = {
        apiBaseUrl: isLocal ? devUrl : prodUrl,
        mode: isLocal ? 'demo' : 'production'
    };
})();
