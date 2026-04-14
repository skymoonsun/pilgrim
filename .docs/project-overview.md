# Pilgrim: Modüler Scraping ve Crawling Mikroservisi

## 1. Proje vizyonu ve amacı

**Pilgrim**, web verisi toplamayı otomatikleştiren, merkezi yönetimden kontrol edilebilen ve diğer sistemlerle **HTTP API** üzerinden entegre olan **“Scraping as a Service”** yaklaşımındaki bir mikroservistir.

Geleneksel scraping’de sıkça her yeni site veya sayfa yapısı için kod değişikliği gerekir. Pilgrim bunu **config-driven scraping** (konfigürasyon güdümlü kazıma) ile azaltır: seçiciler, çıkarım kuralları ve fetch profili mümkün olduğunca **veritabanındaki yapılandırma** üzerinden yönetilir; hedef URL yalnızca çalıştırma parametresidir.

### Temel hedefler

- **Bağımsızlık:** Kazıma “reçetesi” (config) ile hedef URL’nin mümkün olduğunca gevşek bağlanması; aynı config’in çok sayıda URL’de kullanılması.
- **Modülerlik:** **[Scrapling](https://github.com/D4Vinci/Scrapling)** ile statik/hızlı yollar; gerekirse dinamik sayfalar için tarayıcı tabanlı yürütme (worker tarafında).
- **Yeniden kullanılabilirlik:** Bir kez tanımlanan kural setinin (ör. `CrawlConfiguration` / config kimliği) benzer sayfa türlerinde tekrar kullanılması.
- **Merkezi yönetim:** Kurallar, zamanlamalar ve iş durumlarının API ve yönetim arayüzü üzerinden izlenmesi.

---

## 2. Temel mimari ve çalışma mantığı

Pilgrim üç ana katmanda düşünülebilir: **kontrol düzlemi (API + veri modeli)**, **yürütme (worker’lar)** ve **altyapı (PostgreSQL, Redis, container’lar)**.

### 2.1. Config-driven akış (özet)

1. **Tanımlama:** Bir **crawl config** oluşturulur: motor/profil (ör. Scrapling fetcher profili, gerekirse dinamik oturum), `fetch_options` / çıkarım spesifikasyonu (`extraction_spec`), proxy ve hız limiti gibi ayarlar.
2. **Saklama:** Kurallar **PostgreSQL**’te tutulur (ilişkisel alanlar + gerektiğinde JSON/JSONB yapılandırma).
3. **Tetikleme:** İstemci, Pilgrim API’si üzerinden bir **crawl job** başlatır (ör. `config_id` + hedef URL veya hedef kimliği).
4. **Kuyruk:** API ağır işi doğrudan bloklamaz; iş **Celery** görevi olarak **Redis** broker üzerinden worker’a iletilir.
5. **Yürütme:** Worker, config’i yükler, Scrapling (ve gerekiyorsa dinamik fetcher) ile sayfayı alır, kuralları uygular, sonucu modele yazar.
6. **Sonuç ve durum:** **Asıl iş durumu** (pending/running/success/failure, hata özeti, üretilen kayıtlar) **PostgreSQL**’teki job/result yapıları üzerinden izlenir; Redis broker ve kısa ömürlü önbellekler yardımcı roldedir.

Bu nedenle entegrasyon modeli çoğu senaryoda “tek çağrıda anında JSON” değil, **asenkron job + durum sorgulama** veya webhook/geri çağrı gibi tamamlayıcı desenlerle düşünülmelidir.

### 2.2. Zamanlama

Periyodik veya cron benzeri tekrarlayan işler **Celery Beat** ile planlanır; yine asıl plan ve job geçmişi **PostgreSQL** tarafında takip edilir (Redis yalnızca kuyruk/broker rolünde kalır).

---

## 3. Teknik bileşenler

### 3.1. Kazıma motorları

- **Scrapling (birincil):** Statik veya hızlı sayfalar için varsayılan fetch/parse hattı. Proje kurallarında **Scrapling-first** yaklaşım benimsenir; ham HTML için varsayılan olarak `httpx` + ad hoc BeautifulSoup zinciri hedeflenmez.
- **Dinamik / tarayıcı:** Karmaşık JS, bot koruması veya etkileşim gerektiren sayfalar için Scrapling’in dinamik oturumları veya Playwright benzeri yollar devreye alınabilir; bu yük **API sürecinden ayrı, worker imajı/sürecinde** çalışacak şekilde tasarlanır.

Motor seçimi ve oturum ayarları **config** üzerinden yönlendirilir.

### 3.2. PostgreSQL

Örnek sorumluluk alanları (tasarım ayrıntıları için repo içi `database-design` kuralına bakın):

- **Crawl yapılandırmaları** ve mağaza/hedef ilişkileri.
- **Crawl job** ve **sonuç** kayıtları (izlenebilirlik, tekrar çalıştırma, hata ayıklama).
- **Zamanlama / beat** ile uyumlu schedule tanımları.
- İleride fiyat veya içerik için **zaman serisi** ve indeks stratejileri.

### 3.3. Redis

Broker, sonuç önbelleği, hız sınırlama ve kilit gibi **ephemeral** kullanım için. Kalıcı “tek doğru kaynak” iş durumu değildir; o rol **PostgreSQL**’tedir.

### 3.4. API ve servis sınırı

- **Kontrol düzlemi:** **FastAPI** (async), **SQLAlchemy 2.0 async**, **Pydantic v2**.
- **Dağıtım:** **Docker Compose** ile API, worker, beat, Postgres, Redis (ve izleme için Flower gibi yardımcılar) ayrı servisler olarak çalıştırılabilir.
- Dış sistemler Pilgrim’i bir kütüphane değil **HTTP üzerinden servis** gibi çağırır; scraping yükü worker katmanına kaydırılır.

---

## 4. Yönetim arayüzü

Pilgrim yalnızca bir API değil; operasyonel kullanım için **yönetim yüzeyi** hedeflenir (ör. FastAPI tabanlı admin, ayrı bir panel veya ileride ayrıştırılmış UI). Bu yüzey üzerinden:

- Config ve zamanlamaların yönetimi,
- Job durumlarının izlenmesi,
- Gerekirse “tek URL ile dene” test akışları

öngörülür. Ürünleşme aşamasına göre bu bölüm repo içi `app/admin` veya ayrı bir istemci ile somutlaşır.

---

## 5. Modülerlik ve genişleme

- **Zamanlayıcı:** Mimari Celery Beat ve schedule tabloları ile uyumludur; “ileride eklenecek” yerine planlanan bileşen olarak ele alınır.
- **Proxy:** Config veya ortam düzeyinde proxy rotasyonu ve havuz yönetimi için genişleme noktaları tanımlanır.
- **Çıktı:** JSON API yanıtlarına ek olarak webhook, iç veri modeli veya downstream tüketicilere aktarım senaryoları desteklenebilir şekilde tasarlanır.

---

## 6. Geliştiriciler için referanslar

Uygulama standartları, dizin yapısı, test ve Docker akışı repo kökündeki yapılandırılmış kurallarda tutulur:

- **Cursor:** `.cursor/rules/*.mdc`
- **Claude Code:** `.claude/rules/*.md`
- **Antigravity:** `.agents/rules/*.md` (dosya başına karakter sınırına dikkat)
- **Ortak özet:** `AGENTS.md`, `CLAUDE.md`

Bu belge ürün ve mimariyi Türkçe özetler; teknik ayrıntı ve isimlendirme için yukarıdaki kurallar güncel kaynaktır.
