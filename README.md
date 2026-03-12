# 🎓 Bitirme Proje Takip Uygulaması
**OSTİM Teknik Üniversitesi — Yazılım Mühendisliği**

Web tabanlı bitirme proje takip sistemi. Danışmanlar, grup liderleri ve öğrenciler için ayrı paneller sunar.

---

## 🚀 Kurulum ve Çalıştırma

### Gereksinimler
- Python 3.10 veya üstü

### 1. Sanal ortam oluştur ve bağımlılıkları yükle
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Konfigürasyon dosyasını oluştur
```bash
cp .env.example .env
```
`.env` dosyasını bir metin editörü ile açıp değerleri doldurun (varsayılan değerler çoğu durumda çalışır).

### 3. Uygulamayı başlat
```bash
streamlit run app.py
```

Tarayıcınızda otomatik açılır: **http://localhost:8501**

---

## 👤 Giriş Bilgileri (Varsayılan)

### Danışman Girişi
| Kullanıcı ID | Şifre   |
|---|---|
| `dr.mehmet`  | `12345` |

> Danışman adları `constants.py` → `DEFAULT_ADVISOR` ve `ADMIN_ADVISOR_KEYS` ayarlarından düzenlenir.
> Şifre `.env` → `DEFAULT_PASSWORD` ile değiştirilebilir.

### Öğrenci Girişi
Öğrenci numaraları veritabanında kayıtlı olmalıdır.
- CSV yükleyerek eklemek için önce danışman olarak giriş yapın.
- Varsayılan şifre: `12345` (ilk girişte değiştirme zorunludur).

---

## 📁 Proje Yapısı

```
bitirme-projesi-takip-main/
├── app.py                 ← Giriş noktası
├── constants.py           ← Sabitler ve konfigürasyon
├── utils.py               ← Yardımcı fonksiyonlar
├── db.py                  ← Veritabanı katmanı (SQLite)
├── models.py              ← İş mantığı
├── components.py          ← Paylaşılan UI bileşenleri
├── ui_helpers.py          ← HTML kart/rozet yardımcıları
├── styles.py              ← CSS tema
├── i18n.py                ← Çok dilli destek (TR/EN)
├── panels/
│   ├── advisor.py         ← Danışman paneli
│   ├── leader.py          ← Grup lideri paneli
│   └── student.py         ← Öğrenci paneli
├── .env.example           ← Konfigürasyon şablonu
├── requirements.txt       ← Python bağımlılıkları
├── translations_tr_en.json← Çeviri dosyası
├── PROJE_RAPORU.txt       ← Proje değişiklikleri raporu
└── ogr.csv                ← Örnek öğrenci listesi (CSV)
```

---

## ✨ Özellikler

| Rol | Özellikler |
|---|---|
| **Danışman** | Proje kartları ızgarası, öğrenci arama, lider atama, CSV yükleme, geri bildirim, görev takibi |
| **Grup Lideri** | Görev oluşturma, rol atama, milestone takibi, üye ilerleme özeti |
| **Öğrenci** | Görev güncelleme, haftalık rapor, danışman geri bildirimleri, grup karşılaştırma |

### Genel
- 🌐 Türkçe / İngilizce dil desteği (yan panelden değiştirilebilir)
- 🔐 Rol tabanlı erişim kontrolü
- 📊 Milestone bazlı ilerleme görselleştirmesi
- 💬 Görev bazlı yorum sistemi
- 📎 Kanıt dosyası yükleme

---

## 📦 Bağımlılıklar

```
streamlit
pandas
python-dotenv
```
