# DBAktarator

**DBAktarator**, veritabanı entegrasyonu ve veri aktarımını kolaylaştıran güçlü bir Python uygulamasıdır.  
**DBAktarator** is a powerful Python application that simplifies database integration and data transfer.

---

## İçindekiler / Table of Contents

- [Özellikler / Features](#özellikler--features)
- [Ekran Görüntüleri / Screenshots](#ekran-görüntüleri--screenshots)
- [Kurulum / Installation](#kurulum--installation)
- [Kullanım / Usage](#kullanım--usage)
- [Konfigürasyon / Configuration](#konfigürasyon--configuration)
- [Katkıda Bulunanlar / Contributing](#katkıda-bulunanlar--contributing)
- [Lisans / License](#lisans--license)

---

## Özellikler / Features

- **Kolay Konfigürasyon / Easy Configuration:**  
  `config.json` dosyası ile veritabanı bağlantısı ve SMTP ayarlarını hızlıca yapılandırın.
  
- **Grafiksel Kullanıcı Arayüzü (GUI) / Graphical User Interface:**  
  PyQt5 kullanılarak oluşturulmuş modern ve kullanıcı dostu arayüz.

- **İş Yönetimi / Job Management:**  
  - Yeni aktarım işleri oluşturun.
  - Mevcut işleri düzenleyin, çoğaltın veya silin.
  - Kayıtlı veritabanı bağlantıları yönetimi.

- **Mapping & Tetikleyiciler / Mapping & Triggers:**  
  - Kaynak ve hedef veritabanları arasında detaylı kolon eşleştirmeleri.
  - Yeni kayıt geldiğinde otomatik olarak integration mapping kayıtları oluşturacak trigger desteği (GUID ve integration_code alanları).

- **Otomatik Aktarım / Automatic Transfers:**  
  Belirlenen aralıklarla otomatik veri aktarım işlemleri.

- **Sistem Tepsisi Entegrasyonu / System Tray Integration:**  
  Uygulamayı arka planda çalıştırıp sistem tepsisine entegre edebilirsiniz.

---

## Ekran Görüntüleri / Screenshots

### Transfer Wizard / Aktarım Sihirbazı
![Job Wizard](https://raw.githubusercontent.com/ubden/DBAktarator/refs/heads/main/screenshoots/job-wizard.png)

### Aktarım İşleri Listesi / Transfer Jobs List
![Jobs List](https://raw.githubusercontent.com/ubden/DBAktarator/refs/heads/main/screenshoots/jobs.png)

### İş Düzenleme / Job Edit Dialog
![Job Edit](https://raw.githubusercontent.com/ubden/DBAktarator/refs/heads/main/screenshoots/jop-edit.png)

---

## Kurulum / Installation

### Gereksinimler / Prerequisites

- **Python 3.x**
- **PyQt5:** `pip install PyQt5`
- **pymssql:** `pip install pymssql`
- Çalışan bir **Microsoft SQL Server** kurulumu

### Adımlar / Steps

1. **Depoyu Klonlayın / Clone the Repository:**

   ```bash
   git clone https://github.com/ubden/DBAktarator.git
   cd DBAktarator
   ```
2. **Gerekli Paketleri Yükleyin / Install Required Packages:**

Eğer requirements.txt varsa:
```bash
pip install -r requirements.txt
```
Aksi Halde

```
pip install PyQt5 pymssql
```

3) **Uygulamayı Çalıştırın / Run the Application:**
```
python3 DBAktarator.py
```

## Kullanım / Usage
- Veritabanı Bağlantılarını Yapılandırın / Configure Database Connections:
- "Veritabanı Ayarları" ve "Kayıtlı Veritabanları Yönetimi" diyaloglarını kullanarak kaynak ve hedef veritabanı bağlantılarınızı ayarlayın.

- Yeni Aktarım İşleri Oluşturun / Create New Transfer Jobs:
- Ana araç çubuğundaki "Yeni Aktarım" seçeneğiyle aktarım sihirbazını başlatın; adım adım iş detaylarını girin, tabloları yükleyin ve kolon eşleştirmelerini yapın.

- İşleri Düzenleyin ve Çoğaltın / Edit and Duplicate Jobs:
- Ana pencere üzerinden iş listesine sağ tıklayarak düzenleme, silme, çoğaltma veya aktarıma başlama işlemlerini gerçekleştirin.

- Tetikleyici ve Otomatik Aktarım / Setup Triggers and Automatic Transfers:
- Genel Ayarlar diyalogunda tetikleyici ayarlarını ve otomatik aktarım aralıklarını belirleyin. Yeni fatura eklendiğinde, trigger ilgili integration mapping tablosuna otomatik kayıt ekleyecektir.

- Sistem Tepsisi / System Tray:
- Uygulama, sistem tepsisine entegre edilmiş olup, arka planda çalışabilir. Tepsi ikonundan uygulamayı gösterip gizleyebilirsiniz.

## Konfigürasyon / Configuration
Uygulama, ayarları saklamak için config.json dosyasını kullanır. Örnek yapılandırma:
```
{
    "db_server": "127.0.0.1",
    "db_user": "sa",
    "db_password": "password123",
    "db_name": "VeriAktarma",
    "db_port": 1433,
    "smtp_server": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_pass": "",
    "smtp_to": "",
    "auto_start_transfers": "0",
    "auto_start_jobs": "",
    "error_retry_seconds": "60",
    "auto_transfer_interval": "0"
}
```

## Katkıda Bulunanlar / Contributing
Katkılarınızı memnuniyetle bekliyoruz! Lütfen projeyi fork'layın, geliştirmelerinizi yapın ve pull request gönderin. Büyük değişiklikler öncesinde bir issue açarak tartışmanız önerilir.





