# 🧭 Pilgrim: Modular Scraping & Crawling Microservice

## 1. Proje Vizyonu ve Amacı
**Pilgrim**, modern web verisi toplama süreçlerini otomatize eden, merkezi bir yönetim panelinden kontrol edilebilen ve diğer projelerle API üzerinden entegre olan **"Scraping as a Service"** modelinde bir mikroservistir.

Geleneksel scraping yaklaşımlarında, her yeni site veya sayfa yapısı için kod üzerinde değişiklik yapılması gerekir. Pilgrim bu sorunu **"Config-Driven Scraping"** (Konfigürasyon Güdümlü Kazıma) yaklaşımıyla çözer. Kazıma mantığı (seçiciler, veri alanları, kurallar) koddan arındırılarak bir veritabanı nesnesine dönüştürülür.

### Temel Hedefler:
* **Bağımsızlık:** Kazıma mantığının (Config) hedef URL'den tamamen izole edilmesi.
* **Modülerlik:** `Scrapling` ve `Playwright` gibi farklı motorların aynı sistem içinde esnekçe kullanılabilmesi.
* **Yeniden Kullanılabilirlik:** Bir kez tanımlanan kural setinin (Config ID), binlerce farklı URL üzerinde çalıştırılabilmesi.
* **Merkezi Yönetim:** Tek bir arayüzden tüm kazıma kurallarının ve ileride eklenecek zamanlanmış görevlerin yönetilmesi.

---

## 2. Temel Mimari ve Çalışma Mantığı

Pilgrim, üç ana katman üzerinde yükselir: **Yönetim (UI/DB)**, **İletişim (API)** ve **Yürütme (Engine)**.

### 2.1. Config-Driven Scraping Akışı
Sistem, bir URL'ye istek atmadan önce o URL'nin nasıl işleneceğini bildiği bir "reçete" (Config) kullanır.
1. **Tanımlama:** Kullanıcı UI üzerinden bir Config oluşturur (Örn: "Galeri Sayfası Config'i"). Bu config; hangi CSS/XPath seçicilerinin kullanılacağını, verinin hangi formatta döneceğini ve hangi motorun (Scrapling/Playwright) kullanılacağını içerir.
2. **Saklama:** Bu kurallar **PostgreSQL** veritabanında JSON formatında veya ilişkisel tablolar halinde saklanır.
3. **Tetikleme:** Dış bir servis, Pilgrim API'sine bir istek atar: `Execute(config_id=42, target_url="...")`.
4. **Yürütme:** Pilgrim, ID'si 42 olan config'i veritabanından çeker, talep edilen URL'ye gider ve kuralları uygular.
5. **Sonuç:** İşlenmiş veri, tertemiz bir JSON objesi olarak asenkron şekilde geri döner.

---

## 3. Teknik Bileşenler

### 3.1. Veri Motorları (Scraping Engines)
Pilgrim, kazıma kalitesini ve hızını optimize etmek için hibrit bir yapı kullanır:
* **[Scrapling](https://github.com/D4Vinci/Scrapling):** Statik veya hızlı işlenmesi gereken sayfalar için birincil motordur. Bellek yönetimi ve hız konusunda optimize edilmiştir.
* **Playwright Desteği:** JavaScript render edilmesi gereken, karmaşık bot engelleri olan veya kullanıcı etkileşimi (tıklama, kaydırma) gerektiren sayfalar için devreye girer. Config bazında hangi motorun seçileceği belirlenebilir.

### 3.2. Veritabanı (PostgreSQL)
Sistemin beyni olan PostgreSQL şu verileri tutar:
* **Scraping Configs:** Seçiciler, bekleme süreleri, user-agent ayarları, veri şemaları.
* **Scheduler Settings:** (Gelecek hazırlığı için) Hangi görevin ne sıklıkla çalışacağı bilgisi.
* **Logs & Metrics:** Hangi kazıma işleminin ne kadar sürdüğü, hata oranları ve başarı durumları.

### 3.3. Mikroservis ve API Yapısı
Pilgrim, kendi başına yaşayan bir organizmadır. REST veya gRPC üzerinden diğer servislerle haberleşir. Bu yapı sayesinde:
* Python, Go, Node.js veya PHP ile yazılmış herhangi bir projeniz Pilgrim'i bir kütüphane gibi değil, bir servis gibi çağırabilir.
* Scraping yükü ana sunucunuzdan alınarak Pilgrim'in bulunduğu optimize edilmiş sunucuya aktarılır.

---

## 4. Kullanıcı Arayüzü ve Yönetim (Standalone Mode)
Pilgrim, sadece bir API değil, aynı zamanda bir yönetim panelidir. Bu panel üzerinden şunlar yapılabilir:
* **Config Builder:** Teknik bilgisi olmayan veya kod yazmak istemeyen kullanıcılar için görsel olarak kazıma kuralları oluşturma.
* **Test Environment:** Bir config oluşturulduğunda, canlıya almadan önce bir URL üzerinde test edip sonuçları anlık görme.
* **İzleme:** Hangi servislerin Pilgrim'i ne kadar yoğun kullandığını ve kazıma performanslarını takip etme.

---

## 5. Sistem Modülerliği ve Genişletilebilirlik
Pilgrim, gelecekteki ihtiyaçlara göre genişleyebilecek şekilde tasarlanmıştır:
* **Scheduler Entegrasyonu:** Mevcut mimari, bir scheduler (zamanlayıcı) eklendiğinde config'leri otomatik tetikleyecek yapıdadır.
* **Proxy Yönetimi:** Her config veya her istek bazında farklı proxy havuzları tanımlanabilir.
* **Output Formatları:** Veriler sadece JSON olarak doğrudan dönebileceği gibi, farklı veritabanlarına veya webhook'lara da gönderilebilecek şekilde yapılandırılabilir.