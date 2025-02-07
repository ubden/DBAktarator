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
![Job Edit](https://raw.githubusercontent.com/ubden/DBAktarator/refs/heads/main/screenshoots/job-edit.png)

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
   
2. **Gerekli Paketleri Yükleyin / Install Required Packages:**

Eğer requirements.txt varsa:

pip install -r requirements.txt
