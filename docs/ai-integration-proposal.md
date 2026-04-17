# Pilgrim AI Entegrasyon Önerisi

> Tarih: 2026-04-18
> Durum: Analiz / Fikir Aşaması
> Kapsam: Pilgrim'e inovatif AI desteği eklenmesi

---

## 1. Mevcut Durum

Pilgrim şu an **tamamen deterministic** bir scraping pipeline. Kullanıcı manuel olarak CSS/XPath selector'ları yazıyor (`extraction_spec` JSONB alanı), sistem bu selector'ları uyguluyor ve veriyi çıkarıyor. Hiçbir AI/ML bileşeni mevcut değil. Config oluşturma tamamen manuel — frontend'de raw JSON textarea ile dolduruluyor.

**Mevcut extraction_spec örneği:**

```json
{
  "fields": {
    "title": { "selector": "h1.product-title::text", "type": "css" },
    "price": { "selector": "//span[@class='price']/text()", "type": "xpath" },
    "images": { "selector": "img.gallery::attr(src)", "type": "css", "multiple": true }
  }
}
```

Bu yapı güçlü ama **kullanıcıdan CSS/XPath bilgisi gerektiriyor** — teknik olmayan kullanıcılar için büyük bir engel.

---

## 2. Scrapling'in AI Desteği Analizi

Scrapling'in "AI" desteği iki şey anlamına geliyor:

| Özellik | Ne Yapıyor | Bizim İşimize Yarar mı? |
|---------|-----------|----------------------|
| **MCP Server** (`pip install scrapling[ai]`) | Claude/Cursor gibi AI agent'ların Scrapling'i tool olarak kullanmasını sağlar. HTML'i önceden temizleyip LLM'e verir, token tasarrufu sağlar | Kısmen — ama bu AI'ın Scrapling'i kullanması, Scrapling'in AI kullanması değil |
| **Adaptive Element Tracking** | Selector kırıldığında benzerlik algoritmasıyla element'i yeniden bulur (`auto_save=True`, `adaptive=True`) | **Evet!** Mevcut extraction pipeline'ına entegre edilmeli |
| **`find_similar()`** | Bir anchor element'ten yola çıkarak benzer tüm element'leri bulur | Evet — listeleme sayfaları için faydalı |

**Önemli tespit:** Scrapling **LLM-tabanlı extraction yapmıyor**. Selector oluşturmayı AI'a yaptırmak için kendi AI katmanımızı eklememiz gerekiyor. Scrapling, "AI'ın yerine geçen ücretsiz bir alternatif" olarak konumlanıyor — adaptive algoritmalarla selector dayanıklılığı sağlıyor ama LLM ile entegrasyon MCP Server üzerinden ve AI'ın Scrapling'i kullanması yönünde.

---

## 3. AI Entegrasyon Fikirleri

### 3.1 AI-Powered Config Generator (En Yüksek Değer)

**Senaryo:** Kullanıcı URL + doğal dil açıklaması veriyor → sistem sayfayı fetch ediyor → Ollama ile extraction_spec üretiyor → kullanıcı review ediyor → kaydediyor.

```
Kullanıcı: "https://example.com/product/123 — bu sayfadan ürün adı, fiyat, stok durumu ve resimleri çekmek istiyorum"
        ↓
Backend: Scrapling ile sayfayı fetch et → HTML'i temizle → Ollama'ya gönder
        ↓
Ollama: extraction_spec JSON döndür
        ↓
Kullanıcı: Önizleme + düzenleme → Config olarak kaydet
```

**Teknik detaylar:**

- **Endpoint:** `POST /api/v1/ai/generate-extraction-spec` — `{url, description, scraper_profile?}`
- **Ollama structured output:** Pydantic schema ile `format=ExtractionSpecSchema.model_json_schema()` → garanti valid JSON
- **Model:** `qwen2.5:7b` veya `llama3.2` — CSS/XPath anlama yeteneği iyi, local çalışıyor
- **Pipeline:**
  1. Scrapling ile sayfa fetch (mevcut factory kullanarak)
  2. HTML sanitize (script/style etiketleri temizle, DOM yapısını koru)
  3. Ollama'ya prompt + temiz HTML → structured extraction_spec
  4. İsteğe bağlı: üretilen spec'i hemen test et (scrape endpoint ile doğrula)
  5. Frontend'de önizleme + düzenleme

**Frontend UX:**

ConfigCreate sayfasında "AI ile Oluştur" butonu → URL ve açıklama gir → AI çalışır (spinner) → extraction_spec alanı otomatik doldurulur → kullanıcı düzenleyebilir.

**Örnek Ollama prompt yapısı:**

```
Aşağıdaki HTML'den {description} bilgisini çıkarmak için CSS/XPath selector'ları oluştur.
Her alan için selector, type (css/xpath) ve multiple (true/false) belirt.

HTML:
{sanitized_html}

Yanıtını şu JSON şemasına uygun ver:
{extraction_spec_schema}
```

**Örnek Pydantic schema (structured output):**

```python
class FieldSpec(BaseModel):
    selector: str = Field(description="CSS or XPath selector")
    type: Literal["css", "xpath"] = Field(default="css")
    multiple: bool = Field(default=False)

class ExtractionSpecAI(BaseModel):
    fields: dict[str, FieldSpec] = Field(description="Field name to selector mapping")
```

---

### 3.2 AI Config Verification & Iterative Refinement

Config oluştuktan sonra AI, selector'ların gerçekten çalıştığını doğrular:

```
AI config üretti → hedef URL'de test etti → 3/4 field başarılı, "price" selector boş döndü
  → Ollama'ya: "price selector çalışmadı, HTML bu, alternatif selector öner"
  → Yeni selector döndü → tekrar test → 4/4 başarılı
```

**Endpoint:** `POST /api/v1/ai/verify-extraction-spec` — `{url, extraction_spec}`

- Mevcut scrape pipeline'ını kullan, sonuçları analiz et
- Boş/null dönen field'lar için AI'a alternatif selector sor
- Max 2-3 iterasyon (sonsuz döngüyü önle)
- Sonuç: `{"valid": true/false, "failed_fields": [...], "suggestions": {...}}`

**Değer:** Config Generator ile birlikte kullanıldığında, kullanıcıya sadece üretilen config'i değil, onun doğrulanmış halini sunar. Güveni artırır.

---

### 3.3 Scrapling Adaptive Mode Entegrasyonu

Mevcut `app/crawlers/extraction.py` hiçbir adaptive özellik kullanmıyor. Bunu eklemek **sıfır AI maliyetiyle** selector dayanıklılığını artırır.

**Mevcut davranış:**

```python
# Selector kırılınca None döner
result[field_name] = selected.get() if selected else None
```

**Yeni davranış:**

```python
if selected:
    result[field_name] = selected.get()
else:
    # Adaptive: benzerlik algoritmasıyla element'i bul
    result[field_name] = response.css(selector, adaptive=True).get()
```

**Değişiklikler:**

- `CrawlConfiguration` modeline `use_adaptive: bool = False` alanı ekle
- `extraction.py`'de `adaptive=True` ve `auto_save=True` desteği ekle
- Extraction spec'e opsiyonel `adaptive: bool` alanı ekle (field bazında toggle)
- Frontend'de config formuna "Adaptive Mode" checkbox ekle

**Değer:** Site redesign sonrası selector'lar otomatik olarak yeniden bulunur. Production'da en büyük ağrı noktalarından biri.

---

### 3.4 AI-Powered Site Profiler

Hedef siteyi analiz edip otomatik öneri üret:

```
Kullanıcı URL veriyor → AI analiz ediyor:
  - "Bu site Cloudflare koruması var → Stealth profile önerilir"
  - "Sayfa JS-rendered SPA → Dynamic profile gerekli"
  - "Pagination pattern: ?page=2 → spider ile çoklu sayfa crawl edilebilir"
  - "Rate-limit header'ı var → custom_delay: 2.0 önerilir"
```

**Endpoint:** `POST /api/v1/ai/profile-site` — `{url}`

**Dönen response:**

```python
class SiteProfile(BaseModel):
    recommended_profile: ScraperProfile
    recommended_fetch_options: dict | None
    recommended_use_proxy: bool
    recommended_custom_delay: Decimal | None
    detected_features: list[str]  # ["cloudflare", "spa", "pagination", ...]
    confidence: float  # 0-1
    reasoning: str  # AI'ın açıklaması
```

**Pipeline:**

1. Fetcher ile sayfayı fetch et (en basit profile başla)
2. HTTP header'ları analiz et (Cloudflare, rate-limit, server tipi)
3. HTML içeriğini analiz et (JS framework tespiti, SSR vs CSR)
4. Ollama'ya analiz sonuçlarını gönder → öneri al

**Değer:** Kullanıcı hangi profile seçeceğini bilmediğinde rehberlik sağlar. Özellikle yeni kullanıcılar için onboarding deneyimini iyileştirir.

---

### 3.5 Natural Language Extraction (AI Fallback)

Selector tabanlı extraction başarısız olduğunda veya kullanıcı hızlı bir şey istediğinde, LLM doğrudan HTML'den veriyi çıkarır:

```
"Bu sayfadan ürün fiyatını çıkar" → AI doğrudan HTML'den fiyatı okur → structured data döner
```

**CrawlConfiguration modeline yeni alan:**

```python
extraction_mode: str = "selector"  # "selector" | "ai" | "hybrid"
```

| Mod | Davranış |
|-----|---------|
| `selector` | Mevcut davranış — CSS/XPath ile deterministic extraction |
| `ai` | LLM tabanlı extraction — her call Ollama'ya gider, daha yavaş ama esnek |
| `hybrid` | Önce selector dene, başarısız olursa AI fallback |

**AI extraction pipeline:**

1. Sayfayı fetch et
2. HTML'i sanitize et
3. Ollama'ya: "Bu HTML'den şu alanları çıkar: {fields}" → structured JSON
4. Sonuçları CrawlJobResult'a kaydet

**Dikkat noktaları:**

- Her extraction bir Ollama call → maliyet ve latency artar
- `ai_tokens_used` metriği takip edilmeli
- Production'da dikkatli kullanılmalı — rate limit ve timeout ekle
- `hybrid` mod en dengeli seçenek

---

### 3.6 Smart Selector Healing (Production)

Production'da selector kırıldığında (site redesign vb.) otomatik iyileştirme:

```
Job çalıştı → 3 field başarılı, 2 field None (selector kırıldı)
  → AI'a: "Eski selector bu, yeni HTML bu, yeni selector öner"
  → Öneriyi CrawlConfiguration'a draft olarak kaydet
  → Kullanıcı onaylarsa config güncellenir
```

**CrawlJob modeline yeni alan:** `healing_suggestions: JSONB`

```json
{
  "broken_fields": {
    "price": {
      "old_selector": "span.price::text",
      "suggested_selector": "div.product-price span::text",
      "confidence": 0.85
    }
  }
}
```

**Pipeline:**

1. Job tamamlandığında, null dönen field'ları tespit et
2. Null field oranı > threshold ise (örn. %50+), healing task oluştur
3. Healing task: Ollama'ya eski selector + mevcut HTML gönder
4. Önerilen selector'ları job'a `healing_suggestions` olarak kaydet
5. Frontend'de "Selector Önerileri" badge ile kullanıcıyı bilgilendir
6. Kullanıcı tek tıkla onayla → config güncellenir

**Değer:** Site redesign sonrası manuel müdahale ihtiyacını azaltır. Proaktif bakım sağlar.

---

### 3.7 Pilgrim MCP Server

Scrapling'in MCP server'ından ilham alarak Pilgrim'i de bir MCP tool haline getirebiliriz. Bu AI agent'ların (Claude, Cursor) Pilgrim'i doğrudan yönetmesini sağlar:

```
Claude: "Bu site için yeni bir crawl config oluştur, her saat çalışsın"
  → Pilgrim MCP Tool: create_config, create_schedule, trigger_job
```

**MCP Tools (taslak):**

| Tool | Açıklama |
|------|---------|
| `pilgrim_create_config` | Yeni crawl config oluştur |
| `pilgrim_list_configs` | Mevcut config'leri listele |
| `pilgrim_trigger_job` | Belirli bir config + URL ile job başlat |
| `pilgrim_get_job_status` | Job durumunu sorgula |
| `pilgrim_create_schedule` | Zamanlama oluştur |
| `pilgrim_ai_generate_config` | AI ile config oluştur |

**Değer:** AI-native workflow'lar. Claude Code veya Cursor'dan doğrudan "bu siteyi crawl et" diyebilmek. Geliştirici deneyimini önemli ölçüde iyileştirir.

---

## 4. Ollama Entegrasyon Mimarisi

### 4.1 Docker Compose Eklentisi

```yaml
# docker-compose.dev.yml'e eklenecek
ollama:
  image: ollama/ollama:latest
  ports:
    - "11434:11434"
  volumes:
    - ollama_data:/root/.ollama

ollama-pull:
  image: ollama/ollama:latest
  entrypoint: ["sh", "-c"]
  command:
    - |
      sleep 5
      ollama pull qwen2.5:7b
      ollama pull llama3.2:3b
  depends_on:
    - ollama
  restart: "no"
```

### 4.2 Backend Yapısı

```
app/
├── integrations/
│   ├── redis.py          # mevcut
│   └── ollama.py         # YENI — Ollama client wrapper
├── services/
│   ├── crawl_config_service.py   # mevcut
│   ├── scrape_service.py          # mevcut
│   └── ai_service.py              # YENI — AI-powered servisler
├── api/v1/endpoints/
│   ├── crawl_configs.py   # mevcut
│   └── ai.py              # YENI — AI endpoint'leri
└── schemas/
    └── ai.py              # YENI — AI request/response schemas
```

### 4.3 Ollama Client Wrapper

```python
# app/integrations/ollama.py (taslak)
from ollama import Client
from pydantic import BaseModel
from app.core.config import settings

class OllamaIntegration:
    """Ollama client wrapper with structured output support."""

    def __init__(self):
        self.client = Client(host=settings.ollama_base_url)

    def generate_structured(
        self,
        model: str,
        prompt: str,
        schema: type[BaseModel],
        system: str | None = None,
    ) -> BaseModel:
        """Generate structured output validated against Pydantic schema."""
        response = self.client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system or ""},
                {"role": "user", "content": prompt},
            ],
            format=schema.model_json_schema(),
            options={"temperature": 0},
        )
        return schema.model_validate_json(response.message.content)
```

### 4.4 Config Ayarları

```python
# app/core/config.py'ye eklenecek
# ── AI / Ollama ──────────────────────────────────────────────────
ollama_base_url: str = Field(
    default="http://ollama:11434",
    validation_alias="PILGRIM_OLLAMA_BASE_URL",
)
ollama_default_model: str = Field(
    default="qwen2.5:7b",
    validation_alias="PILGRIM_OLLAMA_DEFAULT_MODEL",
)
ai_enabled: bool = Field(
    default=False,
    validation_alias="PILGRIM_AI_ENABLED",
)
ai_max_iterations: int = Field(
    default=3,
    ge=1,
    le=5,
    validation_alias="PILGRIM_AI_MAX_ITERATIONS",
)
```

### 4.5 Neden Ollama?

| Kriter | Ollama | OpenAI API | Anthropic API |
|--------|--------|-----------|---------------|
| **Veri gizliliği** | Tamamen local | Veri dışarı çıkar | Veri dışarı çıkar |
| **Maliyet** | Sıfır (donanım hariç) | Token başına | Token başına |
| **Structured output** | Pydantic schema desteği | JSON mode | JSON mode |
| **Latency** | Local network | Internet round-trip | Internet round-trip |
| **Docker deploy** | Tek container | API key gerekli | API key gerekli |
| **Apple Silicon** | Metal acceleration | N/A | N/A |

**Scraping verisi hassas olabilir** — hedef sitelerin HTML'i, fiyat verileri, rakip analizleri vb. Local model kullanmak veri güvenliği açısından önemli bir avantaj.

### 4.6 Model Önerileri

| Model | Boyut | RAM | Kullanım |
|-------|-------|-----|---------|
| `qwen2.5:7b` | ~5GB | ~8GB | Config generation, site profiling — en iyi JSON/HTML anlama |
| `llama3.2:3b` | ~2GB | ~4GB | Hızlı doğrulama, basit extraction |
| `gemma3:12b` | ~8GB | ~10GB | Karmaşık selector üretimi (vision desteği ile screenshot analizi) |
| `qwen2.5:14b` | ~10GB | ~12GB | Yüksek doğruluk gerektiren görevler |

---

## 5. Frontend Değişiklikleri

### 5.1 ConfigCreate Sayfası — AI Mode

Mevcut ConfigCreate sayfasına AI desteği eklenmesi:

```
┌─────────────────────────────────────────────────┐
│  New Configuration                               │
│                                                  │
│  ┌─ AI ile Oluştur ──────────────────────────┐  │
│  │  Target URL: [________________________]    │  │
│  │  Açıklama:   [________________________]    │  │
│  │              [Bu sayfadan ürün adı, fiyat  │  │
│  │               ve resimleri çek]             │  │
│  │                                            │  │
│  │  [✨ AI ile Oluştur]    [Manuel Mod]       │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  ┌─ Extraction Spec ─────────────────────────┐  │
│  │  {                                         │  │
│  │    "fields": {                             │  │
│  │      "title": { "selector": "h1::text" },  │  │ ← AI doldurdu
│  │      "price": { "selector": ".price" }      │  │ ← kullanıcı düzenleyebilir
│  │    }                                       │  │
│  │  }                                         │  │
│  └────────────────────────────────────────────┘  │
│                                                  │
│  [Doğrula & Test Et]  [Kaydet]                  │
└─────────────────────────────────────────────────┘
```

### 5.2 Yeni Sayfa: AI Playground

ScrapePlayground benzeri ama AI odaklı:

```
/ai-playground → URL + doğal dil girdisi → AI config üretir → anlık test → sonucu göster
```

### 5.3 API Client Genişletmesi

```typescript
// frontend/src/api/client.ts'e eklenecek
export const aiApi = {
  generateExtractionSpec: (data: { url: string; description: string; scraper_profile?: string }) =>
    api.post<AIGenerateResponse>('/ai/generate-extraction-spec', data),

  verifyExtractionSpec: (data: { url: string; extraction_spec: object }) =>
    api.post<AIVerifyResponse>('/ai/verify-extraction-spec', data),

  profileSite: (data: { url: string }) =>
    api.post<AISiteProfileResponse>('/ai/profile-site', data),
};
```

---

## 6. Önceliklendirme Matrisi

| # | Fikir | Değer | Efor | Risk | Öneri |
|---|-------|-------|------|------|-------|
| 3.1 | **AI Config Generator** | Cok Yuksek | Orta | Dusuk | **Ilk yapilacak** — en buyuk UX kazanimi |
| 3.2 | **Config Verification** | Yuksek | Dusuk | Dusuk | 3.1 ile birlikte |
| 3.3 | **Adaptive Mode** | Yuksek | Dusuk | Cok Dusuk | **Paralel yapilabilir** — sifir AI maliyeti |
| 3.4 | **Site Profiler** | Orta | Orta | Dusuk | 3.1'den sonra |
| 3.5 | **NL Extraction** | Yuksek | Yuksek | Orta | Urun olarak ayri phase |
| 3.6 | **Selector Healing** | Yuksek | Yuksek | Orta | Production ihtiyaci dogunca |
| 3.7 | **MCP Server** | Orta | Orta | Dusuk | Uzun vadeli |

---

## 7. Önerilen Uygulama Fazları

### Faz 1: AI Temel Altyapı + Config Generator (Önerilen İlk Adım)

**Amaç:** Kullanıcı deneyimini dönüştürmek — manuel JSON yazımından kurtulmak.

**Kapsam:**

1. Ollama Docker servisi ekleme
2. `app/integrations/ollama.py` — Ollama client wrapper
3. `app/core/config.py` — AI ayarları (PILGRIM_OLLAMA_* env vars)
4. `app/services/ai_service.py` — Config generation servisi
5. `app/schemas/ai.py` — AI request/response schema'ları
6. `app/api/v1/endpoints/ai.py` — AI endpoint'leri
7. Frontend ConfigCreate sayfasına AI mode ekleme
8. HTML sanitizer utility (Ollama'ya gönderilecek HTML'i temizle)

**Tahmini dosya değişiklikleri:** ~8-10 yeni dosya, ~3-4 mevcut dosya güncellemesi

### Faz 2: Adaptive Mode + Config Verification (Paralel Yapılabilir)

**Amaç:** Extraction dayanıklılığını artırmak ve AI üretimi config'leri doğrulamak.

**Kapsam:**

1. `app/crawlers/extraction.py` — adaptive mode desteği
2. `CrawlConfiguration` model — `use_adaptive` alanı
3. AI verification endpoint
4. Frontend'de adaptive mode toggle + verification UI

### Faz 3: Site Profiler + AI Playground

**Amaç:** Kullanıcıya rehberlik ve interaktif AI deneyimi.

**Kapsam:**

1. Site profiling endpoint ve servisi
2. AI Playground sayfası (frontend)
3. Scrapling MCP server entegrasyonu (opsiyonel)

### Faz 4: AI Extraction Mode (Uzun Vadeli)

**Amaç:** Selector yazmadan doğrudan AI ile extraction.

**Kapsam:**

1. `extraction_mode` alanı (model, schema, API)
2. AI extraction pipeline (Ollama ile doğrudan extraction)
3. Hybrid mod (selector fallback → AI)
4. Token kullanım takibi ve rate limiting

### Faz 5: Selector Healing + MCP Server

**Amaç:** Production bakımını otomatikleştirmek ve AI-native workflow'lar.

**Kapsam:**

1. Healing task (Celery worker)
2. `healing_suggestions` JSONB alanı (CrawlJob model)
3. Frontend'de healing öneri UI
4. Pilgrim MCP Server implementasyonu

---

## 8. Riskler ve Dikkat Edilmesi Gerekenler

| Risk | Açıklama | Azaltma Stratejisi |
|------|---------|-------------------|
| **Ollama model doğruluğu** | Küçük modeller yanlış selector üretebilir | Verification endpoint ile doğrulama, iterative refinement |
| **Latency** | Ollama call'ları 5-30 saniye sürebilir | Async processing, loading state UI, cache |
| **HTML boyutu** | Bazı sayfalar çok büyük → Ollama context limiti | HTML sanitizer ile aggressive temizleme, sadece anlamlı DOM bölümlerini gönder |
| **Docker kaynakları** | Ollama RAM ve GPU gerektirir | `ai_enabled` flag ile op-in, model boyutuna göre RAM ayarı |
| **Selector kırılganlığı** | AI ürettiği selector'lar site değişince kırılabilir | Adaptive mode ile yedek mekanizma, healing sistemi |
| **Veri sızıntısı** | Ollama'ya gönderilen HTML'de hassas veri olabilir | Local model kullanımı (zaten Ollama ile sağlanıyor) |

---

## 9. Kaynaklar

- [Scrapling Docs — Replacing AI](https://scrapling.readthedocs.io/en/latest/tutorials/replacing_ai.html)
- [Scrapling Overview](https://scrapling.readthedocs.io/en/latest/overview.html)
- [Scrapling Adaptive Scraping — Scrapingbee](https://scrapingbee.com/blog/scrapling-adaptive-python-web-scraping/)
- [Ollama Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs)
- [Ollama Python SDK](https://github.com/ollama/ollama-python)
- [ScrapeGraphAI + Ollama Configuration](https://mintlify.com/ScrapeGraphAI/Scrapegraph-ai/configuration/ollama)
- [ScrapeGraphAI CodeGeneratorGraph](https://docs-oss.scrapegraphai.com/docs/Examples/local_models/code_generator_graph_ollama)