#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, os, json, uuid, datetime, smtplib
from email.mime.text import MIMEText

# PyQt5
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import (
    QSystemTrayIcon, QMenu, QAction, QTableWidgetItem, QTableWidget, QMessageBox,
    QComboBox, QAbstractItemView, QRadioButton, QButtonGroup, QLineEdit, QPushButton,
    QHBoxLayout, QVBoxLayout, QFormLayout
)
from PyQt5.QtCore import Qt

# pymssql
import pymssql

###############################################################################
# SABİT DEĞERLER
###############################################################################
CONFIG_FILE = "config.json"
ICON_FILE = "icon.jpg"  # Gerçek bir ikon dosyanız varsa buraya yolunu yazın.

###############################################################################
# CONFIG MANAGER
###############################################################################
class ConfigManager:
    """
    config.json dosyasını okumak-yazmak ve eğer yoksa oluşturmak.
    """
    def __init__(self):
        self.config_data = {
            "db_server": "127.0.0.1",
            "db_user": "sa",
            "db_password": "password123",
            "db_name": "VeriAktarma",
            "db_port": 1433,
            # SMTP ve otomatik transfer ayarları da burada saklanabilir:
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
        self.read_or_create_config()

    def read_or_create_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    self.config_data.update(data)
                except Exception as e:
                    print("Config okunurken hata:", e)
        else:
            self.write_config()

    def write_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f, indent=4, ensure_ascii=False)

###############################################################################
# DATABASE MANAGER
###############################################################################
class DatabaseManager:
    """
    Projenin kendi veritabanına bağlanan ve tabloları yöneten sınıf.
    """
    def __init__(self, config: ConfigManager):
        self.config = config
        self.conn = None
        self.connect()

    def connect(self):
        c = self.config.config_data
        try:
            self.conn = pymssql.connect(
                server=c["db_server"],
                user=c["db_user"],
                password=c["db_password"],
                database=c["db_name"],
                port=c.get("db_port", 1433),
                timeout=10
            )
        except Exception as e:
            print("Veritabanına bağlanırken hata oluştu:", str(e))
            self.conn = None

    def close(self):
        if self.conn:
            self.conn.close()

    def create_tables_if_not_exists(self):
        if not self.conn:
            return
        cursor = self.conn.cursor()
        # Tabloları sırasıyla oluşturuyoruz...
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Settings' AND xtype='U')
        CREATE TABLE Settings (
            setting_key VARCHAR(100) NOT NULL PRIMARY KEY,
            setting_value VARCHAR(1000)
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TransferJobs' AND xtype='U')
        CREATE TABLE TransferJobs (
            job_id INT IDENTITY(1,1) PRIMARY KEY,
            job_name VARCHAR(255) NOT NULL,
            source_server VARCHAR(255),
            source_user VARCHAR(255),
            source_password VARCHAR(255),
            source_db VARCHAR(255),
            target_server VARCHAR(255),
            target_user VARCHAR(255),
            target_password VARCHAR(255),
            target_db VARCHAR(255),
            create_date DATETIME DEFAULT GETDATE(),
            last_run_date DATETIME
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TransferJobDetails' AND xtype='U')
        CREATE TABLE TransferJobDetails (
            detail_id INT IDENTITY(1,1) PRIMARY KEY,
            job_id INT NOT NULL,
            source_table VARCHAR(255),
            target_table VARCHAR(255),
            source_column VARCHAR(255),
            target_column VARCHAR(255),
            fixed_value VARCHAR(255),
            convert_type VARCHAR(50),
            is_key BIT DEFAULT 0,
            FOREIGN KEY (job_id) REFERENCES TransferJobs(job_id)
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TransferTriggers' AND xtype='U')
        CREATE TABLE TransferTriggers (
            trigger_id INT IDENTITY(1,1) PRIMARY KEY,
            job_id INT NOT NULL,
            dependent_job_id INT NOT NULL,
            check_table VARCHAR(255),
            check_column VARCHAR(255),
            check_value VARCHAR(255),
            FOREIGN KEY (job_id) REFERENCES TransferJobs(job_id),
            FOREIGN KEY (dependent_job_id) REFERENCES TransferJobs(job_id)
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TransferLogs' AND xtype='U')
        CREATE TABLE TransferLogs (
            log_id INT IDENTITY(1,1) PRIMARY KEY,
            job_id INT NOT NULL,
            log_date DATETIME DEFAULT GETDATE(),
            log_message VARCHAR(MAX),
            FOREIGN KEY (job_id) REFERENCES TransferJobs(job_id)
        )
        """)
        cursor.execute("""
        IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='SavedConnections' AND xtype='U')
        CREATE TABLE SavedConnections (
            conn_id INT IDENTITY(1,1) PRIMARY KEY,
            conn_name VARCHAR(255) NOT NULL,
            server VARCHAR(255),
            username VARCHAR(255),
            passw VARCHAR(255),
            dbname VARCHAR(255),
            port INT
        )
        """)
        self.conn.commit()

    def get_setting(self, key):
        if not self.conn:
            return None
        cursor = self.conn.cursor()
        cursor.execute("SELECT setting_value FROM Settings WHERE setting_key=%s", (key,))
        row = cursor.fetchone()
        return row[0] if row else None

    def set_setting(self, key, value):
        if not self.conn:
            return
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Settings WHERE setting_key=%s", (key,))
        count = cursor.fetchone()[0]
        if count == 0:
            cursor.execute("INSERT INTO Settings (setting_key, setting_value) VALUES (%s, %s)", (key, str(value)))
        else:
            cursor.execute("UPDATE Settings SET setting_value=%s WHERE setting_key=%s", (str(value), key))
        self.conn.commit()

    def insert_transfer_job(self, job_data):
        sql = """INSERT INTO TransferJobs (
            job_name, source_server, source_user, source_password, source_db,
            target_server, target_user, target_password, target_db
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        vals = (
            job_data["job_name"],
            job_data["source_server"], job_data["source_user"], job_data["source_password"], job_data["source_db"],
            job_data["target_server"], job_data["target_user"], job_data["target_password"], job_data["target_db"]
        )
        cursor = self.conn.cursor()
        cursor.execute(sql, vals)
        self.conn.commit()
        cursor.execute("SELECT @@IDENTITY")
        return int(cursor.fetchone()[0])

    def update_transfer_job(self, job_id, job_data):
        sql = """UPDATE TransferJobs SET
            job_name=%s,
            source_server=%s,
            source_user=%s,
            source_password=%s,
            source_db=%s,
            target_server=%s,
            target_user=%s,
            target_password=%s,
            target_db=%s
            WHERE job_id=%s
        """
        vals = (
            job_data["job_name"],
            job_data["source_server"], job_data["source_user"], job_data["source_password"], job_data["source_db"],
            job_data["target_server"], job_data["target_user"], job_data["target_password"], job_data["target_db"],
            job_id
        )
        cursor = self.conn.cursor()
        cursor.execute(sql, vals)
        self.conn.commit()

    def delete_transfer_job(self, job_id):
        cursor = self.conn.cursor()
        # Silinecek job'a bağlı tetikleyiciler
        cursor.execute("DELETE FROM TransferJobDetails WHERE job_id=%s", (job_id,))
        cursor.execute("DELETE FROM TransferTriggers WHERE job_id=%s OR dependent_job_id=%s", (job_id, job_id))
        cursor.execute("DELETE FROM TransferLogs WHERE job_id=%s", (job_id,))
        cursor.execute("DELETE FROM TransferJobs WHERE job_id=%s", (job_id,))
        self.conn.commit()

    def insert_transfer_job_details(self, details):
        sql = """INSERT INTO TransferJobDetails (
            job_id, source_table, target_table, source_column, target_column,
            fixed_value, convert_type, is_key
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor = self.conn.cursor()
        for d in details:
            vals = (
                d["job_id"],
                d["source_table"], d["target_table"],
                d["source_column"], d["target_column"],
                d.get("fixed_value", None),
                d.get("convert_type", None),
                1 if d.get("is_key", False) else 0
            )
            cursor.execute(sql, vals)
        self.conn.commit()

    def update_transfer_job_details(self, job_id, details):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM TransferJobDetails WHERE job_id=%s", (job_id,))
        self.conn.commit()
        self.insert_transfer_job_details(details)

    def insert_trigger(self, job_id, dep_job_id, check_table, check_column, check_value):
        sql = """INSERT INTO TransferTriggers (
            job_id, dependent_job_id, check_table, check_column, check_value
        ) VALUES (%s, %s, %s, %s, %s)
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (job_id, dep_job_id, check_table, check_column, check_value))
        self.conn.commit()

    def log_message(self, job_id, message):
        sql = "INSERT INTO TransferLogs (job_id, log_message) VALUES (%s, %s)"
        cursor = self.conn.cursor()
        cursor.execute(sql, (job_id, message))
        self.conn.commit()

    def get_saved_connections(self):
        cursor = self.conn.cursor(as_dict=True)
        cursor.execute("SELECT * FROM SavedConnections ORDER BY conn_id")
        return cursor.fetchall()

    def insert_saved_connection(self, data):
        sql = """INSERT INTO SavedConnections (
            conn_name, server, username, passw, dbname, port
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (
            data["conn_name"], data["server"], data["username"],
            data["passw"], data["dbname"], data["port"]
        ))
        self.conn.commit()

    def update_saved_connection(self, conn_id, data):
        sql = """UPDATE SavedConnections SET
            conn_name=%s, server=%s, username=%s, passw=%s, dbname=%s, port=%s
            WHERE conn_id=%s
        """
        cursor = self.conn.cursor()
        cursor.execute(sql, (
            data["conn_name"], data["server"], data["username"],
            data["passw"], data["dbname"], data["port"], conn_id
        ))
        self.conn.commit()

    def delete_saved_connection(self, conn_id):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM SavedConnections WHERE conn_id=%s", (conn_id,))
        self.conn.commit()

    def duplicate_job(self, old_job_id):
        """
        Seçili aktarım işini aynen kopyalayarak (yeni job_id oluşturarak) çoğaltır.
        TransferJobDetails ve job_id=old_job_id olan tetikleyicileri de kopyalar.
        """
        cursor = self.conn.cursor(as_dict=True)
        # 1) Eski job bilgisini al
        cursor.execute("SELECT * FROM TransferJobs WHERE job_id=%d" % old_job_id)
        job = cursor.fetchone()
        if not job:
            return None

        # 2) Yeni job satırı ekle (create_date ve last_run_date'i sıfırlayabiliriz veya None bırakabiliriz)
        new_data = {
            "job_name": job["job_name"] + " (Kopya)",
            "source_server": job["source_server"],
            "source_user": job["source_user"],
            "source_password": job["source_password"],
            "source_db": job["source_db"],
            "target_server": job["target_server"],
            "target_user": job["target_user"],
            "target_password": job["target_password"],
            "target_db": job["target_db"]
        }
        new_job_id = self.insert_transfer_job(new_data)

        # 3) Eski job'un details kayıtlarını kopyala
        cursor.execute("SELECT * FROM TransferJobDetails WHERE job_id=%d" % old_job_id)
        details = cursor.fetchall()
        new_details = []
        for d in details:
            new_details.append({
                "job_id": new_job_id,
                "source_table": d["source_table"],
                "target_table": d["target_table"],
                "source_column": d["source_column"],
                "target_column": d["target_column"],
                "fixed_value": d["fixed_value"],
                "convert_type": d["convert_type"],
                "is_key": True if d["is_key"] else False
            })
        self.insert_transfer_job_details(new_details)

        # 4) Eski job'un tetikleyicilerini (job_id=old_job_id) kopyala
        cursor.execute("SELECT * FROM TransferTriggers WHERE job_id=%d" % old_job_id)
        triggers = cursor.fetchall()
        for t in triggers:
            self.insert_trigger(
                new_job_id,
                t["dependent_job_id"],
                t["check_table"],
                t["check_column"],
                t["check_value"]
            )
        return new_job_id


###############################################################################
# AKTARIM İŞİ (RUNNER)
###############################################################################
class TransferJobRunner:
    """
    Tek bir aktarım işini çalıştırır.
    """
    def __init__(self, db_manager: DatabaseManager, job_id):
        self.db_manager = db_manager
        self.job_id = job_id

    def run(self):
        job_info = self.get_job_info()
        if not job_info:
            return
        if not self.check_triggers(self.job_id):
            self.db_manager.log_message(self.job_id, "Tetikleyici koşulu sağlanmadığı için aktarım başlatılmadı.")
            return

        try:
            source_conn = pymssql.connect(
                server=job_info["source_server"],
                user=job_info["source_user"],
                password=job_info["source_password"],
                database=job_info["source_db"]
            )
        except Exception as e:
            self.db_manager.log_message(self.job_id, f"Kaynak DB bağlantı hatası: {str(e)}")
            self.send_error_mail(f"Kaynak DB bağlantı hatası: {str(e)}")
            return

        try:
            target_conn = pymssql.connect(
                server=job_info["target_server"],
                user=job_info["target_user"],
                password=job_info["target_password"],
                database=job_info["target_db"]
            )
        except Exception as e:
            self.db_manager.log_message(self.job_id, f"Hedef DB bağlantı hatası: {str(e)}")
            self.send_error_mail(f"Hedef DB bağlantı hatası: {str(e)}")
            return

        details = self.get_job_details(self.job_id)
        grouped = {}
        for d in details:
            key = (d["source_table"], d["target_table"])
            grouped.setdefault(key, []).append(d)

        for (src_table, tgt_table), col_maps in grouped.items():
            key_cols = [c for c in col_maps if c["is_key"]]
            columns_to_select = [c["source_column"] for c in col_maps if c["source_column"]]

            try:
                cur_s = source_conn.cursor(as_dict=True)
                sql_s = f"SELECT {','.join(columns_to_select)} FROM {src_table}"
                cur_s.execute(sql_s)
                rows = cur_s.fetchall()
            except Exception as e:
                self.db_manager.log_message(self.job_id, f"Kaynak okuma hatası {src_table}: {str(e)}")
                self.send_error_mail(f"Kaynak okuma hatası {src_table}: {str(e)}")
                continue

            inserted_count = 0
            for row in rows:
                if key_cols and self.target_row_exists(target_conn, tgt_table, key_cols, row):
                    continue

                col_names = []
                col_values = []
                for cm in col_maps:
                    val = None
                    if cm["fixed_value"]:
                        if cm["fixed_value"].lower() == "guid":
                            val = str(uuid.uuid4())
                        elif cm["fixed_value"].lower() == "null":
                            val = None
                        else:
                            val = cm["fixed_value"]
                    else:
                        val = row.get(cm["source_column"], None)

                    if not cm.get("convert_type") and val is not None:
                        # Basit örnek: tip kestirimi
                        pass

                    if cm["convert_type"] == "datetime" and isinstance(val, str):
                        try:
                            val = datetime.datetime.fromisoformat(val)
                        except:
                            try:
                                val = datetime.datetime.strptime(val, "%Y-%m-%d")
                            except:
                                val = None
                    elif cm["convert_type"] == "int" and val is not None:
                        try:
                            val = int(val)
                        except:
                            val = None
                    elif cm["convert_type"] == "float" and val is not None:
                        try:
                            val = float(val)
                        except:
                            val = None

                    col_names.append(cm["target_column"])
                    col_values.append(val)

                try:
                    cur_t = target_conn.cursor()
                    placeholders = ",".join(["%s"] * len(col_values))
                    sql_t = f"INSERT INTO {tgt_table} ({','.join(col_names)}) VALUES ({placeholders})"
                    cur_t.execute(sql_t, tuple(col_values))
                    target_conn.commit()
                    inserted_count += 1
                except Exception as e:
                    self.db_manager.log_message(self.job_id, f"Hedef insert hatası {tgt_table}: {str(e)}")
                    self.send_error_mail(f"Hedef insert hatası {tgt_table}: {str(e)}")
                    continue

            self.db_manager.log_message(self.job_id, f"{src_table} >> {tgt_table}: {inserted_count} kayıt.")
        source_conn.close()
        target_conn.close()
        self.update_job_last_run_date(self.job_id)
        self.db_manager.log_message(self.job_id, "Aktarım tamamlandı.")

    def target_row_exists(self, conn, table, key_cols, src_row):
        conds, vals = [], []
        for c in key_cols:
            if c["fixed_value"]:
                fv = c["fixed_value"]
                val = None if fv.lower() in ["guid", "null"] else fv
            else:
                val = src_row.get(c["source_column"])
            conds.append(f"{c['target_column']}=%s")
            vals.append(val)
        sql = f"SELECT COUNT(*) FROM {table} WHERE {' AND '.join(conds)}"
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(vals))
            count = cur.fetchone()[0]
            return count > 0
        except:
            return False

    def get_job_info(self):
        cr = self.db_manager.conn.cursor(as_dict=True)
        cr.execute("SELECT * FROM TransferJobs WHERE job_id=%s", (self.job_id,))
        return cr.fetchone()

    def get_job_details(self, job_id):
        cr = self.db_manager.conn.cursor(as_dict=True)
        cr.execute("SELECT * FROM TransferJobDetails WHERE job_id=%s", (job_id,))
        return cr.fetchall()

    def check_triggers(self, job_id):
        cr = self.db_manager.conn.cursor(as_dict=True)
        cr.execute("SELECT * FROM TransferTriggers WHERE job_id=%s", (job_id,))
        triggers = cr.fetchall()
        if not triggers:
            return True
        for tr in triggers:
            if not self.is_value_exists(tr["check_table"], tr["check_column"], tr["check_value"], tr["dependent_job_id"]):
                # Eksik veri varsa dependent job'ı çalıştır
                runner = TransferJobRunner(self.db_manager, tr["dependent_job_id"])
                runner.run()
                if not self.is_value_exists(tr["check_table"], tr["check_column"], tr["check_value"], tr["dependent_job_id"]):
                    return False
        return True

    def is_value_exists(self, table, column, val, dep_job_id):
        cr = self.db_manager.conn.cursor(as_dict=True)
        cr.execute("SELECT * FROM TransferJobs WHERE job_id=%s", (dep_job_id,))
        job_row = cr.fetchone()
        if not job_row:
            return False
        try:
            conn = pymssql.connect(
                server=job_row["target_server"],
                user=job_row["target_user"],
                password=job_row["target_password"],
                database=job_row["target_db"]
            )
        except:
            return False
        try:
            c2 = conn.cursor()
            sql = f"SELECT COUNT(*) FROM {table} WHERE {column}=%s"
            c2.execute(sql, (val,))
            cnt = c2.fetchone()[0]
            conn.close()
            return cnt > 0
        except:
            conn.close()
            return False

    def update_job_last_run_date(self, job_id):
        cr = self.db_manager.conn.cursor()
        cr.execute("UPDATE TransferJobs SET last_run_date=GETDATE() WHERE job_id=%s", (job_id,))
        self.db_manager.conn.commit()

    def send_error_mail(self, message):
        smtp_server = self.db_manager.get_setting("smtp_server")
        smtp_port = self.db_manager.get_setting("smtp_port")
        smtp_user = self.db_manager.get_setting("smtp_user")
        smtp_pass = self.db_manager.get_setting("smtp_pass")
        smtp_to = self.db_manager.get_setting("smtp_to")
        if not (smtp_server and smtp_port and smtp_user and smtp_pass and smtp_to):
            return
        try:
            msg = MIMEText(message, "plain", "utf-8")
            msg["Subject"] = "Aktarım Sistemi Hatası"
            msg["From"] = smtp_user
            msg["To"] = smtp_to
            s = smtplib.SMTP(smtp_server, int(smtp_port))
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, [smtp_to], msg.as_string())
            s.quit()
        except Exception as e:
            print("Mail gönderirken hata:", e)

###############################################################################
# KAYITLI VERİTABANLARI YÖNETİM DİYALOĞU
###############################################################################
class SavedDBDialog(QtWidgets.QDialog):
    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setWindowTitle("Kayıtlı Veritabanları Yönetimi")
        self.resize(700, 400)
        layout = QtWidgets.QVBoxLayout(self)

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(7)
        self.tbl.setHorizontalHeaderLabels(["conn_id", "Bağlantı Adı", "Server", "User", "Pass", "DB Name", "Port"])
        self.tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.tbl)

        btn_layout = QtWidgets.QHBoxLayout()
        btn_add = QPushButton("Ekle")
        btn_edit = QPushButton("Düzenle")
        btn_delete = QPushButton("Sil")
        btn_test = QPushButton("Bağlantı Test")

        btn_add.clicked.connect(self.on_add)
        btn_edit.clicked.connect(self.on_edit)
        btn_delete.clicked.connect(self.on_delete)
        btn_test.clicked.connect(self.on_test_connection)

        btn_layout.addWidget(btn_add)
        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_delete)
        btn_layout.addWidget(btn_test)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.load_data()

    def load_data(self):
        rows = self.db_manager.get_saved_connections()
        self.tbl.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.tbl.setItem(i, 0, QTableWidgetItem(str(r["conn_id"])))
            self.tbl.setItem(i, 1, QTableWidgetItem(r["conn_name"]))
            self.tbl.setItem(i, 2, QTableWidgetItem(r["server"]))
            self.tbl.setItem(i, 3, QTableWidgetItem(r["username"]))
            self.tbl.setItem(i, 4, QTableWidgetItem(r["passw"]))
            self.tbl.setItem(i, 5, QTableWidgetItem(r["dbname"]))
            self.tbl.setItem(i, 6, QTableWidgetItem(str(r["port"]) if r["port"] else ""))

    def on_add(self):
        dlg = SavedDBEditDialog(self.db_manager, None, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.load_data()

    def on_edit(self):
        row = self.tbl.currentRow()
        if row < 0:
            return
        conn_id_item = self.tbl.item(row, 0)
        if not conn_id_item:
            return
        conn_id = int(conn_id_item.text())
        dlg = SavedDBEditDialog(self.db_manager, conn_id, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.load_data()

    def on_delete(self):
        row = self.tbl.currentRow()
        if row < 0:
            return
        conn_id_item = self.tbl.item(row, 0)
        if not conn_id_item:
            return
        conn_id = int(conn_id_item.text())
        msg = QMessageBox.question(self, "Sil", "Seçili bağlantı silinsin mi?")
        if msg == QMessageBox.Yes:
            self.db_manager.delete_saved_connection(conn_id)
            self.load_data()

    def on_test_connection(self):
        """
        Seçili satırın bilgilerinden bağlanmayı deneyerek test eder.
        """
        row = self.tbl.currentRow()
        if row < 0:
            return
        server = self.tbl.item(row, 2).text()
        user = self.tbl.item(row, 3).text()
        psw = self.tbl.item(row, 4).text()
        dbname = self.tbl.item(row, 5).text()
        port_txt = self.tbl.item(row, 6).text()
        try:
            port = int(port_txt)
        except:
            port = 1433

        try:
            conn = pymssql.connect(server=server, user=user, password=psw, database=dbname, port=port, timeout=5)
            conn.close()
            QMessageBox.information(self, "Bağlantı Test", "Bağlantı başarılı!")
        except Exception as e:
            QMessageBox.warning(self, "Bağlantı Test", f"Bağlanılamadı: {str(e)}")


class SavedDBEditDialog(QtWidgets.QDialog):
    def __init__(self, db_manager: DatabaseManager, conn_id=None, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.conn_id = conn_id
        self.setWindowTitle("Veritabanı Bağlantı Kaydı")
        self.resize(400, 300)
        layout = QFormLayout(self)

        self.le_name = QLineEdit()
        self.le_server = QLineEdit()
        self.le_user = QLineEdit()
        self.le_pass = QLineEdit()
        self.le_pass.setEchoMode(QLineEdit.Password)
        self.le_db = QLineEdit()
        self.le_port = QLineEdit()
        layout.addRow("Bağlantı Adı:", self.le_name)
        layout.addRow("Sunucu:", self.le_server)
        layout.addRow("Kullanıcı:", self.le_user)
        layout.addRow("Şifre:", self.le_pass)
        layout.addRow("Veritabanı Adı:", self.le_db)
        layout.addRow("Port:", self.le_port)

        btn_ok = QPushButton("Kaydet")
        btn_ok.clicked.connect(self.on_save)
        layout.addRow(btn_ok)

        if conn_id:
            self.load_data(conn_id)

    def load_data(self, conn_id):
        cr = self.db_manager.conn.cursor(as_dict=True)
        cr.execute("SELECT * FROM SavedConnections WHERE conn_id=%s", (conn_id,))
        row = cr.fetchone()
        if row:
            self.le_name.setText(row["conn_name"] or "")
            self.le_server.setText(row["server"] or "")
            self.le_user.setText(row["username"] or "")
            self.le_pass.setText(row["passw"] or "")
            self.le_db.setText(row["dbname"] or "")
            self.le_port.setText(str(row["port"]) if row["port"] else "")

    def on_save(self):
        data = {
            "conn_name": self.le_name.text().strip(),
            "server": self.le_server.text().strip(),
            "username": self.le_user.text().strip(),
            "passw": self.le_pass.text().strip(),
            "dbname": self.le_db.text().strip(),
            "port": int(self.le_port.text()) if self.le_port.text().isdigit() else 1433
        }
        if not data["conn_name"]:
            QMessageBox.warning(self, "Uyarı", "Bağlantı Adı boş olamaz.")
            return
        if self.conn_id:
            self.db_manager.update_saved_connection(self.conn_id, data)
        else:
            self.db_manager.insert_saved_connection(data)
        self.accept()

###############################################################################
# TETİKLEYİCİ EKLEME VE DÜZENLEME PNL.
###############################################################################
class TriggerPanel(QtWidgets.QWidget):
    """
    Hem tetikleyici ekleme hem düzenleme için, seçimli tetikleyici paneli.
    Kullanıcı, mevcut aktarım işlerinden (daha önce oluşturulmuş) seçim yapar,
    ve kontrol için tablo, kolon, değer gibi alanlar da QComboBox üzerinden seçilir.
    """
    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager

        layout = QFormLayout(self)

        self.cbo_dependent_job = QComboBox()
        cr = self.db_manager.conn.cursor(as_dict=True)
        cr.execute("SELECT job_id, job_name FROM TransferJobs ORDER BY job_id")
        jobs = cr.fetchall()
        for j in jobs:
            self.cbo_dependent_job.addItem(f"{j['job_name']} (ID={j['job_id']})", j["job_id"])
        layout.addRow("Bağlı İş Seçimi:", self.cbo_dependent_job)

        self.cbo_check_table = QComboBox()
        self.cbo_check_column = QComboBox()

        # arama için editable + QCompleter
        self.cbo_check_table.setEditable(True)
        self.cbo_check_column.setEditable(True)

        self.cbo_check_table.currentIndexChanged.connect(self.update_check_columns)

        layout.addRow("Kontrol Tablo:", self.cbo_check_table)
        layout.addRow("Kontrol Kolon:", self.cbo_check_column)

        self.le_check_value = QLineEdit()
        layout.addRow("Kontrol Değer:", self.le_check_value)

        # Yeni seçilen dependent job'a göre tablo listesini güncelle
        self.cbo_dependent_job.currentIndexChanged.connect(self.refresh_tables)
        self.refresh_tables()

    def refresh_tables(self):
        self.cbo_check_table.clear()
        dep_job_id = self.cbo_dependent_job.currentData()
        if not dep_job_id:
            return

        cr = self.db_manager.conn.cursor(as_dict=True)
        cr.execute("SELECT * FROM TransferJobs WHERE job_id=%s", (dep_job_id,))
        job = cr.fetchone()
        if job:
            try:
                conn = pymssql.connect(
                    server=job["target_server"],
                    user=job["target_user"],
                    password=job["target_password"],
                    database=job["target_db"]
                )
                c = conn.cursor()
                c.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
                tables = [r[0] for r in c.fetchall()]
                conn.close()
                self.cbo_check_table.addItem("")
                for t in tables:
                    self.cbo_check_table.addItem(t)
                # completer
                completer = QtWidgets.QCompleter(tables, self)
                completer.setCaseSensitivity(Qt.CaseInsensitive)
                self.cbo_check_table.setCompleter(completer)
            except:
                pass

    def update_check_columns(self):
        table = self.cbo_check_table.currentText()
        self.cbo_check_column.clear()
        self.cbo_check_column.addItem("")
        if table:
            dep_job_id = self.cbo_dependent_job.currentData()
            cr = self.db_manager.conn.cursor(as_dict=True)
            cr.execute("SELECT * FROM TransferJobs WHERE job_id=%s", (dep_job_id,))
            job = cr.fetchone()
            if job:
                try:
                    conn = pymssql.connect(
                        server=job["target_server"],
                        user=job["target_user"],
                        password=job["target_password"],
                        database=job["target_db"]
                    )
                    c = conn.cursor()
                    c.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{table}' ORDER BY COLUMN_NAME")
                    cols = [r[0] for r in c.fetchall()]
                    conn.close()
                    for col in cols:
                        self.cbo_check_column.addItem(col)
                    completer = QtWidgets.QCompleter(cols, self)
                    completer.setCaseSensitivity(Qt.CaseInsensitive)
                    self.cbo_check_column.setCompleter(completer)
                except:
                    pass

    def get_trigger_data(self):
        return {
            "dep_job_id": self.cbo_dependent_job.currentData(),
            "check_table": self.cbo_check_table.currentText(),
            "check_column": self.cbo_check_column.currentText(),
            "check_value": self.le_check_value.text().strip()
        }

###############################################################################
# AKTARIM İŞİNİ DÜZENLEME PNL. (EditJobDialog)
###############################################################################
class EditJobDialog(QtWidgets.QDialog):
    """
    Var olan aktarım işini düzenlemek için pencere.
    """
    def __init__(self, db_manager: DatabaseManager, job_id, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.job_id = job_id
        self.setWindowTitle("Aktarım İşini Düzenle")
        self.resize(1000, 700)

        self.source_tables = []
        self.source_columns = {}
        self.target_tables = []
        self.target_columns = {}

        main_layout = QVBoxLayout(self)

        # Üst form
        form_top = QFormLayout()
        self.le_job_name = QLineEdit()
        self.le_source_server = QLineEdit()
        self.le_source_user = QLineEdit()
        self.le_source_pass = QLineEdit()
        self.le_source_pass.setEchoMode(QLineEdit.Password)
        self.le_source_db = QLineEdit()
        self.le_target_server = QLineEdit()
        self.le_target_user = QLineEdit()
        self.le_target_pass = QLineEdit()
        self.le_target_pass.setEchoMode(QLineEdit.Password)
        self.le_target_db = QLineEdit()

        form_top.addRow("İş Adı:", self.le_job_name)
        form_top.addRow("Kaynak Server:", self.le_source_server)
        form_top.addRow("Kaynak Kullanıcı:", self.le_source_user)
        form_top.addRow("Kaynak Şifre:", self.le_source_pass)
        form_top.addRow("Kaynak DB:", self.le_source_db)

        form_top.addRow("Hedef Server:", self.le_target_server)
        form_top.addRow("Hedef Kullanıcı:", self.le_target_user)
        form_top.addRow("Hedef Şifre:", self.le_target_pass)
        form_top.addRow("Hedef DB:", self.le_target_db)

        main_layout.addLayout(form_top)

        # Load tables button
        hl_bt = QHBoxLayout()
        self.btn_load_tables = QPushButton("Tabloları Yükle")
        self.btn_load_tables.clicked.connect(self.on_load_tables)
        hl_bt.addWidget(self.btn_load_tables)
        hl_bt.addStretch()
        main_layout.addLayout(hl_bt)

        # Mapping
        self.tbl_details = QTableWidget()
        self.tbl_details.setColumnCount(8)
        self.tbl_details.setHorizontalHeaderLabels([
            "Kaynak Tablo", "Kaynak Sütun", "Hedef Tablo", "Hedef Sütun",
            "Sabit Tip", "Sabit Değer", "Convert Type", "is_key"
        ])
        self.tbl_details.horizontalHeader().setStretchLastSection(True)
        self.tbl_details.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tbl_details.customContextMenuRequested.connect(self.mapping_context_menu)

        main_layout.addWidget(QtWidgets.QLabel("Eşleştirme Detayları:"))
        main_layout.addWidget(self.tbl_details)

        btn_det_hlayout = QHBoxLayout()
        btn_add_row = QPushButton("Satır Ekle")
        btn_remove_row = QPushButton("Satır Sil")
        btn_add_row.clicked.connect(self.on_add_row)
        btn_remove_row.clicked.connect(self.on_remove_row)
        btn_det_hlayout.addWidget(btn_add_row)
        btn_det_hlayout.addWidget(btn_remove_row)
        btn_det_hlayout.addStretch()
        main_layout.addLayout(btn_det_hlayout)

        # Trigger panel
        main_layout.addWidget(QtWidgets.QLabel("Tetikleyici Ayarları:"))
        self.trigger_panel = TriggerPanel(self.db_manager)
        main_layout.addWidget(self.trigger_panel)

        # Kaydet
        btn_save = QPushButton("Kaydet")
        btn_save.clicked.connect(self.on_save)
        main_layout.addWidget(btn_save)

        self.setLayout(main_layout)
        self.load_job_data()

    def load_job_data(self):
        cr = self.db_manager.conn.cursor(as_dict=True)
        cr.execute("SELECT * FROM TransferJobs WHERE job_id=%s", (self.job_id,))
        row = cr.fetchone()
        if row:
            self.le_job_name.setText(row["job_name"] or "")
            self.le_source_server.setText(row["source_server"] or "")
            self.le_source_user.setText(row["source_user"] or "")
            self.le_source_pass.setText(row["source_password"] or "")
            self.le_source_db.setText(row["source_db"] or "")
            self.le_target_server.setText(row["target_server"] or "")
            self.le_target_user.setText(row["target_user"] or "")
            self.le_target_pass.setText(row["target_password"] or "")
            self.le_target_db.setText(row["target_db"] or "")

        cr.execute("SELECT * FROM TransferJobDetails WHERE job_id=%s", (self.job_id,))
        details = cr.fetchall()
        self.tbl_details.setRowCount(len(details))
        for i, d in enumerate(details):
            self.set_mapping_row(i, d)

    def on_load_tables(self):
        # Kaynak tablolar
        self.source_tables = []
        self.source_columns = {}
        try:
            server = self.le_source_server.text().strip()
            user = self.le_source_user.text().strip()
            psw = self.le_source_pass.text().strip()
            db = self.le_source_db.text().strip()
            conn = pymssql.connect(server=server, user=user, password=psw, database=db, timeout=5)
            c = conn.cursor()
            c.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
            tables = [r[0] for r in c.fetchall()]
            self.source_tables = tables
            # Sütunlar:
            for t in tables:
                c.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY COLUMN_NAME")
                cols = [r[0] for r in c.fetchall()]
                self.source_columns[t] = cols
            conn.close()
        except Exception as e:
            QMessageBox.warning(self, "Kaynak Bağlantı Hatası", str(e))

        # Hedef tablolar
        self.target_tables = []
        self.target_columns = {}
        try:
            server = self.le_target_server.text().strip()
            user = self.le_target_user.text().strip()
            psw = self.le_target_pass.text().strip()
            db = self.le_target_db.text().strip()
            conn = pymssql.connect(server=server, user=user, password=psw, database=db, timeout=5)
            c = conn.cursor()
            c.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
            tables = [r[0] for r in c.fetchall()]
            self.target_tables = tables
            # Sütunlar:
            for t in tables:
                c.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY COLUMN_NAME")
                cols = [r[0] for r in c.fetchall()]
                self.target_columns[t] = cols
            conn.close()
        except Exception as e:
            QMessageBox.warning(self, "Hedef Bağlantı Hatası", str(e))

        QMessageBox.information(self, "Bilgi", "Tablolar ve sütunlar yüklendi. Eşleştirme alanlarını yenileyebilirsiniz.")

    def set_mapping_row(self, row, d):
        # Kaynak Tablo
        cb_src_table = QComboBox()
        cb_src_table.setEditable(True)
        cb_src_table.addItem("")
        for t in self.source_tables:
            cb_src_table.addItem(t)
        cb_src_table.setCurrentText(d.get("source_table", ""))
        # completer
        sc = QtWidgets.QCompleter(self.source_tables, self)
        sc.setCaseSensitivity(Qt.CaseInsensitive)
        cb_src_table.setCompleter(sc)

        cb_src_table.currentIndexChanged.connect(lambda idx, r=row: self.update_source_columns(r))

        self.tbl_details.setCellWidget(row, 0, cb_src_table)

        # Kaynak Sütun
        cb_src_col = QComboBox()
        cb_src_col.setEditable(True)
        cb_src_col.addItem("")
        cb_src_col.setCurrentText(d.get("source_column", ""))
        self.tbl_details.setCellWidget(row, 1, cb_src_col)

        # Hedef Tablo
        cb_tgt_table = QComboBox()
        cb_tgt_table.setEditable(True)
        cb_tgt_table.addItem("")
        for t in self.target_tables:
            cb_tgt_table.addItem(t)
        cb_tgt_table.setCurrentText(d.get("target_table", ""))
        tc = QtWidgets.QCompleter(self.target_tables, self)
        tc.setCaseSensitivity(Qt.CaseInsensitive)
        cb_tgt_table.setCompleter(tc)

        cb_tgt_table.currentIndexChanged.connect(lambda idx, r=row: self.update_target_columns(r))

        self.tbl_details.setCellWidget(row, 2, cb_tgt_table)

        # Hedef Sütun
        cb_tgt_col = QComboBox()
        cb_tgt_col.setEditable(True)
        cb_tgt_col.addItem("")
        cb_tgt_col.setCurrentText(d.get("target_column", ""))
        self.tbl_details.setCellWidget(row, 3, cb_tgt_col)

        # Sabit tip
        widget_fixed = QtWidgets.QWidget()
        h_fixed = QHBoxLayout(widget_fixed)
        h_fixed.setContentsMargins(0, 0, 0, 0)
        rb_guid = QRadioButton("GUID")
        rb_manual = QRadioButton("Sabit")
        group_fixed = QButtonGroup(widget_fixed)
        group_fixed.addButton(rb_guid)
        group_fixed.addButton(rb_manual)
        if (d.get("fixed_value") or "").lower() == "guid":
            rb_guid.setChecked(True)
        else:
            rb_manual.setChecked(True)
        h_fixed.addWidget(rb_guid)
        h_fixed.addWidget(rb_manual)
        self.tbl_details.setCellWidget(row, 4, widget_fixed)

        # Sabit değer
        le_fixed = QLineEdit()
        if (d.get("fixed_value") or "").lower() == "guid":
            le_fixed.setText("")
            le_fixed.setEnabled(False)
        else:
            le_fixed.setText(d.get("fixed_value") or "")
            le_fixed.setEnabled(rb_manual.isChecked())
        self.tbl_details.setCellWidget(row, 5, le_fixed)

        # radyo değişiminde le_fixed'i enable/disable yap
        def on_radio_change():
            le_fixed.setEnabled(rb_manual.isChecked())

        group_fixed.buttonClicked.connect(on_radio_change)

        # Convert type
        cb_conv = QComboBox()
        cb_conv.addItem("")
        cb_conv.addItem("datetime")
        cb_conv.addItem("int")
        cb_conv.addItem("float")
        if d.get("convert_type"):
            cb_conv.setCurrentText(d["convert_type"])
        self.tbl_details.setCellWidget(row, 6, cb_conv)

        # is_key
        cb_key = QComboBox()
        cb_key.addItems(["False", "True"])
        cb_key.setCurrentText("True" if d.get("is_key") else "False")
        self.tbl_details.setCellWidget(row, 7, cb_key)

        # Sütunları güncelle
        self.update_source_columns(row)
        self.update_target_columns(row)

    def update_source_columns(self, row):
        cb_table = self.tbl_details.cellWidget(row, 0)
        cb_col = self.tbl_details.cellWidget(row, 1)
        if not cb_table or not cb_col:
            return
        table_name = cb_table.currentText()
        cb_col.clear()
        cb_col.setEditable(True)
        cb_col.addItem("")
        if table_name and table_name in self.source_columns:
            for col in self.source_columns[table_name]:
                cb_col.addItem(col)
            # completer
            cc = QtWidgets.QCompleter(self.source_columns[table_name], self)
            cc.setCaseSensitivity(Qt.CaseInsensitive)
            cb_col.setCompleter(cc)

    def update_target_columns(self, row):
        cb_table = self.tbl_details.cellWidget(row, 2)
        cb_col = self.tbl_details.cellWidget(row, 3)
        if not cb_table or not cb_col:
            return
        table_name = cb_table.currentText()
        cb_col.clear()
        cb_col.setEditable(True)
        cb_col.addItem("")
        if table_name and table_name in self.target_columns:
            for col in self.target_columns[table_name]:
                cb_col.addItem(col)
            tc = QtWidgets.QCompleter(self.target_columns[table_name], self)
            tc.setCaseSensitivity(Qt.CaseInsensitive)
            cb_col.setCompleter(tc)

    def mapping_context_menu(self, pos):
        menu = QMenu()
        action_copy = QAction("Satırı Kopyala", self)
        action_copy.triggered.connect(self.copy_current_row)
        menu.addAction(action_copy)
        menu.exec_(self.tbl_details.viewport().mapToGlobal(pos))

    def copy_current_row(self):
        row = self.tbl_details.currentRow()
        if row < 0:
            return
        # Mevcut row'un widget değerlerini al
        data = {}
        # Kaynak tablo
        cb_src_table = self.tbl_details.cellWidget(row, 0)
        data["source_table"] = cb_src_table.currentText() if cb_src_table else ""

        # Kaynak sütun
        cb_src_col = self.tbl_details.cellWidget(row, 1)
        data["source_column"] = cb_src_col.currentText() if cb_src_col else ""

        # Hedef tablo
        cb_tgt_table = self.tbl_details.cellWidget(row, 2)
        data["target_table"] = cb_tgt_table.currentText() if cb_tgt_table else ""

        # Hedef sütun
        cb_tgt_col = self.tbl_details.cellWidget(row, 3)
        data["target_column"] = cb_tgt_col.currentText() if cb_tgt_col else ""

        # Sabit tip
        widget_fixed = self.tbl_details.cellWidget(row, 4)
        rb_guid = None
        rb_manual = None
        for ch in widget_fixed.findChildren(QRadioButton):
            if ch.text() == "GUID":
                rb_guid = ch
            elif ch.text() == "Sabit":
                rb_manual = ch
        fixed_type = ""
        if rb_guid and rb_guid.isChecked():
            fixed_type = "guid"
        else:
            fixed_type = "sabit"

        # Sabit değer
        le_fixed = self.tbl_details.cellWidget(row, 5)
        fixed_val = le_fixed.text() if le_fixed else ""

        if fixed_type == "guid":
            data["fixed_value"] = "GUID"
        else:
            data["fixed_value"] = fixed_val

        # Convert type
        cb_conv = self.tbl_details.cellWidget(row, 6)
        data["convert_type"] = cb_conv.currentText() if cb_conv else ""

        # is_key
        cb_key = self.tbl_details.cellWidget(row, 7)
        data["is_key"] = True if cb_key and cb_key.currentText() == "True" else False

        # Yeni satır ekle
        new_row = self.tbl_details.rowCount()
        self.tbl_details.insertRow(new_row)
        # set_mapping_row benzeri bir yöntemle
        self.set_mapping_row(new_row, {
            "source_table": data["source_table"],
            "source_column": data["source_column"],
            "target_table": data["target_table"],
            "target_column": data["target_column"],
            "fixed_value": data["fixed_value"],
            "convert_type": data["convert_type"],
            "is_key": data["is_key"]
        })

    def on_add_row(self):
        row = self.tbl_details.rowCount()
        self.tbl_details.insertRow(row)
        # Boş veri seti
        d = {
            "source_table": "",
            "source_column": "",
            "target_table": "",
            "target_column": "",
            "fixed_value": "GUID",  # default
            "convert_type": "",
            "is_key": False
        }
        self.set_mapping_row(row, d)

    def on_remove_row(self):
        selected = self.tbl_details.selectionModel().selectedRows()
        for s in reversed(selected):
            self.tbl_details.removeRow(s.row())

    def on_save(self):
        job_data = {
            "job_name": self.le_job_name.text().strip(),
            "source_server": self.le_source_server.text().strip(),
            "source_user": self.le_source_user.text().strip(),
            "source_password": self.le_source_pass.text().strip(),
            "source_db": self.le_source_db.text().strip(),
            "target_server": self.le_target_server.text().strip(),
            "target_user": self.le_target_user.text().strip(),
            "target_password": self.le_target_pass.text().strip(),
            "target_db": self.le_target_db.text().strip(),
        }
        self.db_manager.update_transfer_job(self.job_id, job_data)

        details_list = []
        for i in range(self.tbl_details.rowCount()):
            cb_stab = self.tbl_details.cellWidget(i, 0)
            cb_scol = self.tbl_details.cellWidget(i, 1)
            cb_ttab = self.tbl_details.cellWidget(i, 2)
            cb_tcol = self.tbl_details.cellWidget(i, 3)
            widget_fixed = self.tbl_details.cellWidget(i, 4)
            le_fixed = self.tbl_details.cellWidget(i, 5)
            cb_conv = self.tbl_details.cellWidget(i, 6)
            cb_key = self.tbl_details.cellWidget(i, 7)

            src_table = cb_stab.currentText() if cb_stab else ""
            src_col = cb_scol.currentText() if cb_scol else ""
            tgt_table = cb_ttab.currentText() if cb_ttab else ""
            tgt_col = cb_tcol.currentText() if cb_tcol else ""

            # Sabit tip
            rb_guid = None
            rb_manual = None
            for ch in widget_fixed.findChildren(QRadioButton):
                if ch.text() == "GUID":
                    rb_guid = ch
                elif ch.text() == "Sabit":
                    rb_manual = ch
            fixed_type = "guid" if (rb_guid and rb_guid.isChecked()) else "sabit"
            fixed_val = "GUID" if fixed_type == "guid" else le_fixed.text().strip()

            conv_type = cb_conv.currentText() if cb_conv else ""
            key_str = cb_key.currentText() if cb_key else "False"

            d = {
                "job_id": self.job_id,
                "source_table": src_table,
                "source_column": src_col,
                "target_table": tgt_table,
                "target_column": tgt_col,
                "fixed_value": fixed_val if fixed_val else None,
                "convert_type": conv_type if conv_type else None,
                "is_key": (key_str == "True")
            }
            details_list.append(d)

        self.db_manager.update_transfer_job_details(self.job_id, details_list)

        # Tetikleyici verilerini de ekleyelim:
        trig_data = self.trigger_panel.get_trigger_data()
        if all(trig_data.values()):
            self.db_manager.insert_trigger(
                job_id=self.job_id,
                dep_job_id=trig_data["dep_job_id"],
                check_table=trig_data["check_table"],
                check_column=trig_data["check_column"],
                check_value=trig_data["check_value"]
            )
        QMessageBox.information(self, "Bilgi", "Aktarım işi güncellendi.")
        self.accept()

###############################################################################
# SIHIRBAZ (Yeni Aktarım)
###############################################################################
class TransferWizard(QtWidgets.QDialog):
    """
    Yeni aktarım işi oluşturmak için sihirbaz.
    """
    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setWindowTitle("Yeni Aktarım İşi Sihirbazı")
        self.resize(1000, 700)

        self.source_tables = []
        self.source_columns = {}
        self.target_tables = []
        self.target_columns = {}

        self.stacked = QtWidgets.QStackedWidget()
        self.btn_next = QPushButton("İleri")
        self.btn_prev = QPushButton("Geri")
        self.btn_prev.setEnabled(False)

        # Sayfa1
        self.page1 = QtWidgets.QWidget()
        layout1 = QFormLayout(self.page1)
        self.le_job_name = QLineEdit()
        layout1.addRow("Aktarım İş Adı:", self.le_job_name)

        self.cbo_source_saved = QComboBox()
        self.cbo_source_saved.addItem("Manuel Giriş", -1)
        for c in self.db_manager.get_saved_connections():
            self.cbo_source_saved.addItem(f"{c['conn_name']} (ID={c['conn_id']})", c["conn_id"])
        self.le_source_server = QLineEdit()
        self.le_source_user = QLineEdit()
        self.le_source_pass = QLineEdit()
        self.le_source_pass.setEchoMode(QLineEdit.Password)
        self.le_source_db = QLineEdit()
        self.le_source_port = QLineEdit("1433")

        self.cbo_source_saved.currentIndexChanged.connect(self.on_source_saved_changed)

        layout1.addRow("Kayıtlı Kaynak DB:", self.cbo_source_saved)
        layout1.addRow("Kaynak Server:", self.le_source_server)
        layout1.addRow("Kaynak Kullanıcı:", self.le_source_user)
        layout1.addRow("Kaynak Şifre:", self.le_source_pass)
        layout1.addRow("Kaynak DB Adı:", self.le_source_db)
        layout1.addRow("Kaynak Port:", self.le_source_port)

        self.stacked.addWidget(self.page1)

        # Sayfa2
        self.page2 = QtWidgets.QWidget()
        layout2 = QFormLayout(self.page2)
        self.cbo_target_saved = QComboBox()
        self.cbo_target_saved.addItem("Manuel Giriş", -1)
        for c in self.db_manager.get_saved_connections():
            self.cbo_target_saved.addItem(f"{c['conn_name']} (ID={c['conn_id']})", c["conn_id"])
        self.le_target_server = QLineEdit()
        self.le_target_user = QLineEdit()
        self.le_target_pass = QLineEdit()
        self.le_target_pass.setEchoMode(QLineEdit.Password)
        self.le_target_db = QLineEdit()
        self.le_target_port = QLineEdit("1433")

        self.cbo_target_saved.currentIndexChanged.connect(self.on_target_saved_changed)

        layout2.addRow("Kayıtlı Hedef DB:", self.cbo_target_saved)
        layout2.addRow("Hedef Server:", self.le_target_server)
        layout2.addRow("Hedef Kullanıcı:", self.le_target_user)
        layout2.addRow("Hedef Şifre:", self.le_target_pass)
        layout2.addRow("Hedef DB Adı:", self.le_target_db)
        layout2.addRow("Hedef Port:", self.le_target_port)

        self.stacked.addWidget(self.page2)

        # Sayfa3: Eşleştirme
        self.page3 = QtWidgets.QWidget()
        vlay3 = QVBoxLayout(self.page3)
        hbox_btns = QHBoxLayout()
        self.btn_load_tables = QPushButton("Kaynak/Hedef Tabloları Yükle")
        self.btn_load_tables.clicked.connect(self.on_load_tables)
        hbox_btns.addWidget(self.btn_load_tables)
        hbox_btns.addStretch()
        vlay3.addLayout(hbox_btns)

        self.tbl_map = QTableWidget()
        self.tbl_map.setColumnCount(8)
        self.tbl_map.setHorizontalHeaderLabels([
            "Kaynak Tablo", "Kaynak Sütun", "Hedef Tablo", "Hedef Sütun",
            "Sabit Tip", "Sabit Değer", "Convert Type", "is_key"
        ])
        self.tbl_map.horizontalHeader().setStretchLastSection(True)
        self.tbl_map.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tbl_map.customContextMenuRequested.connect(self.mapping_context_menu)
        vlay3.addWidget(self.tbl_map)

        h2 = QHBoxLayout()
        self.btn_add_row = QPushButton("Satır Ekle")
        self.btn_remove_row = QPushButton("Satır Sil")
        self.btn_add_row.clicked.connect(self.on_add_map_row)
        self.btn_remove_row.clicked.connect(self.on_remove_map_row)
        h2.addWidget(self.btn_add_row)
        h2.addWidget(self.btn_remove_row)
        h2.addStretch()
        vlay3.addLayout(h2)

        self.stacked.addWidget(self.page3)

        # Sayfa4: Tetikleyici
        self.page4 = QtWidgets.QWidget()
        lay4 = QVBoxLayout(self.page4)
        lay4.addWidget(QtWidgets.QLabel("Tetikleyici Ayarları:"))
        self.trigger_panel = TriggerPanel(self.db_manager)
        lay4.addWidget(self.trigger_panel)
        lay4.addStretch()
        self.stacked.addWidget(self.page4)

        btn_h = QHBoxLayout()
        btn_h.addWidget(self.btn_prev)
        btn_h.addWidget(self.btn_next)

        main_v = QVBoxLayout(self)
        main_v.addWidget(self.stacked)
        main_v.addLayout(btn_h)

        self.btn_next.clicked.connect(self.on_next)
        self.btn_prev.clicked.connect(self.on_prev)

    def on_next(self):
        idx = self.stacked.currentIndex()
        if idx < self.stacked.count() - 1:
            self.stacked.setCurrentIndex(idx + 1)
            self.btn_prev.setEnabled(True)
            if (idx + 1) == self.stacked.count() - 1:
                self.btn_next.setText("Kaydet")
            else:
                self.btn_next.setText("İleri")
        else:
            # Kaydet
            self.save_job()
            self.accept()

    def on_prev(self):
        idx = self.stacked.currentIndex()
        if idx > 0:
            self.stacked.setCurrentIndex(idx - 1)
            if (idx - 1) == 0:
                self.btn_prev.setEnabled(False)
            self.btn_next.setText("İleri")

    def on_source_saved_changed(self):
        conn_id = self.cbo_source_saved.currentData()
        if conn_id and conn_id > 0:
            cr = self.db_manager.conn.cursor(as_dict=True)
            cr.execute("SELECT * FROM SavedConnections WHERE conn_id=%s", (conn_id,))
            row = cr.fetchone()
            if row:
                self.le_source_server.setText(row["server"] or "")
                self.le_source_user.setText(row["username"] or "")
                self.le_source_pass.setText(row["passw"] or "")
                self.le_source_db.setText(row["dbname"] or "")
                self.le_source_port.setText(str(row["port"]) if row["port"] else "1433")
        else:
            self.le_source_server.clear()
            self.le_source_user.clear()
            self.le_source_pass.clear()
            self.le_source_db.clear()
            self.le_source_port.setText("1433")

    def on_target_saved_changed(self):
        conn_id = self.cbo_target_saved.currentData()
        if conn_id and conn_id > 0:
            cr = self.db_manager.conn.cursor(as_dict=True)
            cr.execute("SELECT * FROM SavedConnections WHERE conn_id=%s", (conn_id,))
            row = cr.fetchone()
            if row:
                self.le_target_server.setText(row["server"] or "")
                self.le_target_user.setText(row["username"] or "")
                self.le_target_pass.setText(row["passw"] or "")
                self.le_target_db.setText(row["dbname"] or "")
                self.le_target_port.setText(str(row["port"]) if row["port"] else "1433")
        else:
            self.le_target_server.clear()
            self.le_target_user.clear()
            self.le_target_pass.clear()
            self.le_target_db.clear()
            self.le_target_port.setText("1433")

    def on_load_tables(self):
        # Kaynak
        self.source_tables = []
        self.source_columns = {}
        try:
            s_server = self.le_source_server.text().strip()
            s_user = self.le_source_user.text().strip()
            s_pass = self.le_source_pass.text().strip()
            s_db = self.le_source_db.text().strip()
            s_port = int(self.le_source_port.text().strip()) if self.le_source_port.text().isdigit() else 1433
            sc = pymssql.connect(server=s_server, user=s_user, password=s_pass, database=s_db, port=s_port, timeout=5)
            c = sc.cursor()
            c.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
            tables = [r[0] for r in c.fetchall()]
            self.source_tables = tables
            for t in tables:
                c.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY COLUMN_NAME")
                cols = [r[0] for r in c.fetchall()]
                self.source_columns[t] = cols
            sc.close()
        except Exception as e:
            QMessageBox.warning(self, "Kaynak DB", f"Hata: {str(e)}")

        # Hedef
        self.target_tables = []
        self.target_columns = {}
        try:
            t_server = self.le_target_server.text().strip()
            t_user = self.le_target_user.text().strip()
            t_pass = self.le_target_pass.text().strip()
            t_db = self.le_target_db.text().strip()
            t_port = int(self.le_target_port.text().strip()) if self.le_target_port.text().isdigit() else 1433
            tc = pymssql.connect(server=t_server, user=t_user, password=t_pass, database=t_db, port=t_port, timeout=5)
            c2 = tc.cursor()
            c2.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME")
            tables2 = [r[0] for r in c2.fetchall()]
            self.target_tables = tables2
            for t in tables2:
                c2.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='{t}' ORDER BY COLUMN_NAME")
                cols = [r[0] for r in c2.fetchall()]
                self.target_columns[t] = cols
            tc.close()
        except Exception as e:
            QMessageBox.warning(self, "Hedef DB", f"Hata: {str(e)}")

        QMessageBox.information(self, "Bilgi", "Tablolar yüklendi, artık eşleştirme satırlarını ekleyebilirsiniz.")

    def mapping_context_menu(self, pos):
        menu = QMenu()
        action_copy = QAction("Satırı Kopyala", self)
        action_copy.triggered.connect(self.copy_current_map_row)
        menu.addAction(action_copy)
        menu.exec_(self.tbl_map.viewport().mapToGlobal(pos))

    def copy_current_map_row(self):
        row = self.tbl_map.currentRow()
        if row < 0:
            return
        # Widget değerlerini okuyup yeni satıra ekleme
        data = self.get_map_row_data(row)
        new_row = self.tbl_map.rowCount()
        self.tbl_map.insertRow(new_row)
        self.populate_map_row(new_row, data)

    def get_map_row_data(self, row):
        d = {}
        # Kaynak Tablo
        cb_stab = self.tbl_map.cellWidget(row, 0)
        d["source_table"] = cb_stab.currentText() if cb_stab else ""
        # Kaynak Sütun
        cb_scol = self.tbl_map.cellWidget(row, 1)
        d["source_column"] = cb_scol.currentText() if cb_scol else ""
        # Hedef Tablo
        cb_ttab = self.tbl_map.cellWidget(row, 2)
        d["target_table"] = cb_ttab.currentText() if cb_ttab else ""
        # Hedef Sütun
        cb_tcol = self.tbl_map.cellWidget(row, 3)
        d["target_column"] = cb_tcol.currentText() if cb_tcol else ""
        # Sabit tip
        widget_fixed = self.tbl_map.cellWidget(row, 4)
        fixed_type = "guid"
        for child in widget_fixed.findChildren(QRadioButton):
            if child.isChecked() and child.text() == "Sabit":
                fixed_type = "sabit"
                break
        # Sabit değer
        le_fixed = self.tbl_map.cellWidget(row, 5)
        d["fixed_value"] = "GUID" if fixed_type == "guid" else (le_fixed.text() if le_fixed else "")
        # Convert
        cb_conv = self.tbl_map.cellWidget(row, 6)
        d["convert_type"] = cb_conv.currentText() if cb_conv else ""
        # is_key
        cb_key = self.tbl_map.cellWidget(row, 7)
        d["is_key"] = (cb_key.currentText() == "True") if cb_key else False
        return d

    def populate_map_row(self, row, d):
        self.tbl_map.setRowCount(row+1)
        # Kaynak Tablo
        cb_src_table = QComboBox()
        cb_src_table.setEditable(True)
        cb_src_table.addItem("")
        for t in self.source_tables:
            cb_src_table.addItem(t)
        cb_src_table.setCurrentText(d["source_table"])
        # completer
        sc = QtWidgets.QCompleter(self.source_tables, self)
        sc.setCaseSensitivity(Qt.CaseInsensitive)
        cb_src_table.setCompleter(sc)

        cb_src_table.currentIndexChanged.connect(lambda idx, r=row: self.update_source_columns(r))

        self.tbl_map.setCellWidget(row, 0, cb_src_table)

        # Kaynak sütun
        cb_src_col = QComboBox()
        cb_src_col.setEditable(True)
        cb_src_col.addItem("")
        cb_src_col.setCurrentText(d["source_column"])
        self.tbl_map.setCellWidget(row, 1, cb_src_col)

        # Hedef Tablo
        cb_tgt_table = QComboBox()
        cb_tgt_table.setEditable(True)
        cb_tgt_table.addItem("")
        for t in self.target_tables:
            cb_tgt_table.addItem(t)
        cb_tgt_table.setCurrentText(d["target_table"])
        tc = QtWidgets.QCompleter(self.target_tables, self)
        tc.setCaseSensitivity(Qt.CaseInsensitive)
        cb_tgt_table.setCompleter(tc)

        cb_tgt_table.currentIndexChanged.connect(lambda idx, r=row: self.update_target_columns(r))

        self.tbl_map.setCellWidget(row, 2, cb_tgt_table)

        # Hedef sütun
        cb_tgt_col = QComboBox()
        cb_tgt_col.setEditable(True)
        cb_tgt_col.addItem("")
        cb_tgt_col.setCurrentText(d["target_column"])
        self.tbl_map.setCellWidget(row, 3, cb_tgt_col)

        # Sabit tip
        widget_fixed = QtWidgets.QWidget()
        h_fixed = QHBoxLayout(widget_fixed)
        h_fixed.setContentsMargins(0, 0, 0, 0)
        rb_guid = QRadioButton("GUID")
        rb_manual = QRadioButton("Sabit")
        group_fixed = QButtonGroup(widget_fixed)
        group_fixed.addButton(rb_guid)
        group_fixed.addButton(rb_manual)
        if (d["fixed_value"] or "").lower() == "guid":
            rb_guid.setChecked(True)
        else:
            rb_manual.setChecked(True)
        h_fixed.addWidget(rb_guid)
        h_fixed.addWidget(rb_manual)
        self.tbl_map.setCellWidget(row, 4, widget_fixed)

        # Sabit değer
        le_fixed = QLineEdit()
        if (d["fixed_value"] or "").lower() == "guid":
            le_fixed.setText("")
            le_fixed.setEnabled(False)
        else:
            le_fixed.setText(d["fixed_value"])
            le_fixed.setEnabled(rb_manual.isChecked())

        self.tbl_map.setCellWidget(row, 5, le_fixed)

        def on_radio_change():
            le_fixed.setEnabled(rb_manual.isChecked())

        group_fixed.buttonClicked.connect(on_radio_change)

        # Convert type
        cb_conv = QComboBox()
        cb_conv.addItem("")
        cb_conv.addItem("datetime")
        cb_conv.addItem("int")
        cb_conv.addItem("float")
        cb_conv.setCurrentText(d["convert_type"])
        self.tbl_map.setCellWidget(row, 6, cb_conv)

        # is_key
        cb_key = QComboBox()
        cb_key.addItems(["False", "True"])
        cb_key.setCurrentText("True" if d["is_key"] else "False")
        self.tbl_map.setCellWidget(row, 7, cb_key)

        # Sütun listesi doldurma
        self.update_source_columns(row)
        self.update_target_columns(row)

    def update_source_columns(self, row):
        cb_table = self.tbl_map.cellWidget(row, 0)
        cb_col = self.tbl_map.cellWidget(row, 1)
        if not cb_table or not cb_col:
            return
        table_name = cb_table.currentText()
        cb_col.clear()
        cb_col.setEditable(True)
        cb_col.addItem("")
        if table_name in self.source_columns:
            for col in self.source_columns[table_name]:
                cb_col.addItem(col)
            cc = QtWidgets.QCompleter(self.source_columns[table_name], self)
            cc.setCaseSensitivity(Qt.CaseInsensitive)
            cb_col.setCompleter(cc)

    def update_target_columns(self, row):
        cb_table = self.tbl_map.cellWidget(row, 2)
        cb_col = self.tbl_map.cellWidget(row, 3)
        if not cb_table or not cb_col:
            return
        table_name = cb_table.currentText()
        cb_col.clear()
        cb_col.setEditable(True)
        cb_col.addItem("")
        if table_name in self.target_columns:
            for col in self.target_columns[table_name]:
                cb_col.addItem(col)
            cc = QtWidgets.QCompleter(self.target_columns[table_name], self)
            cc.setCaseSensitivity(Qt.CaseInsensitive)
            cb_col.setCompleter(cc)

    def on_add_map_row(self):
        row = self.tbl_map.rowCount()
        self.tbl_map.insertRow(row)
        d = {
            "source_table": "",
            "source_column": "",
            "target_table": "",
            "target_column": "",
            "fixed_value": "GUID",
            "convert_type": "",
            "is_key": False
        }
        self.populate_map_row(row, d)

    def on_remove_map_row(self):
        selected = self.tbl_map.selectionModel().selectedRows()
        for s in reversed(selected):
            self.tbl_map.removeRow(s.row())

    def save_job(self):
        job_name = self.le_job_name.text().strip()
        if not job_name:
            QMessageBox.warning(self, "Uyarı", "İş adı boş olamaz!")
            return

        job_data = {
            "job_name": job_name,
            "source_server": self.le_source_server.text().strip(),
            "source_user": self.le_source_user.text().strip(),
            "source_password": self.le_source_pass.text().strip(),
            "source_db": self.le_source_db.text().strip(),
            "target_server": self.le_target_server.text().strip(),
            "target_user": self.le_target_user.text().strip(),
            "target_password": self.le_target_pass.text().strip(),
            "target_db": self.le_target_db.text().strip(),
        }

        # Yalnızca 1 kez ekle!
        job_id = self.db_manager.insert_transfer_job(job_data)

        details = []
        for i in range(self.tbl_map.rowCount()):
            cb_stab = self.tbl_map.cellWidget(i, 0)
            cb_scol = self.tbl_map.cellWidget(i, 1)
            cb_ttab = self.tbl_map.cellWidget(i, 2)
            cb_tcol = self.tbl_map.cellWidget(i, 3)
            widget_fixed = self.tbl_map.cellWidget(i, 4)
            le_fixed = self.tbl_map.cellWidget(i, 5)
            cb_conv = self.tbl_map.cellWidget(i, 6)
            cb_key = self.tbl_map.cellWidget(i, 7)

            src_table = cb_stab.currentText() if cb_stab else ""
            src_col = cb_scol.currentText() if cb_scol else ""
            tgt_table = cb_ttab.currentText() if cb_ttab else ""
            tgt_col = cb_tcol.currentText() if cb_tcol else ""

            rb_guid = None
            rb_manual = None
            for ch in widget_fixed.findChildren(QRadioButton):
                if ch.text() == "GUID":
                    rb_guid = ch
                elif ch.text() == "Sabit":
                    rb_manual = ch
            fixed_type = "guid" if (rb_guid and rb_guid.isChecked()) else "sabit"
            fixed_val = "GUID" if fixed_type == "guid" else le_fixed.text().strip()

            conv_type = cb_conv.currentText() if cb_conv else ""
            key_str = cb_key.currentText() if cb_key else "False"

            d = {
                "job_id": job_id,
                "source_table": src_table,
                "source_column": src_col,
                "target_table": tgt_table,
                "target_column": tgt_col,
                "fixed_value": fixed_val if fixed_val else None,
                "convert_type": conv_type if conv_type else None,
                "is_key": (key_str == "True")
            }
            details.append(d)

        self.db_manager.insert_transfer_job_details(details)

        trig_data = self.trigger_panel.get_trigger_data()
        if all(trig_data.values()):
            self.db_manager.insert_trigger(
                job_id=job_id,
                dep_job_id=trig_data["dep_job_id"],
                check_table=trig_data["check_table"],
                check_column=trig_data["check_column"],
                check_value=trig_data["check_value"]
            )
        QMessageBox.information(self, "Bilgi", f"Aktarım işi (ID={job_id}) oluşturuldu.")

###############################################################################
# GENEL AYARLAR DİYALOG
###############################################################################
class GeneralSettingsDialog(QtWidgets.QDialog):
    def __init__(self, db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setWindowTitle("Genel Ayarlar")
        self.resize(400, 300)
        lay = QFormLayout(self)

        self.chk_auto = QtWidgets.QCheckBox()
        val = self.db_manager.get_setting("auto_start_transfers")
        self.chk_auto.setChecked(val == "1")

        self.le_auto_jobs = QLineEdit(self.db_manager.get_setting("auto_start_jobs") or "")
        self.le_retry = QLineEdit(self.db_manager.get_setting("error_retry_seconds") or "60")
        self.le_interval = QLineEdit(self.db_manager.get_setting("auto_transfer_interval") or "0")
        self.le_smtp_server = QLineEdit(self.db_manager.get_setting("smtp_server") or "")
        self.le_smtp_port = QLineEdit(self.db_manager.get_setting("smtp_port") or "587")
        self.le_smtp_user = QLineEdit(self.db_manager.get_setting("smtp_user") or "")
        self.le_smtp_pass = QLineEdit(self.db_manager.get_setting("smtp_pass") or "")
        self.le_smtp_pass.setEchoMode(QLineEdit.Password)
        self.le_smtp_to = QLineEdit(self.db_manager.get_setting("smtp_to") or "")

        lay.addRow("Otomatik başlasın mı?", self.chk_auto)
        lay.addRow("Oto. İş ID'leri (virgül):", self.le_auto_jobs)
        lay.addRow("Hata sonrası retry (sn):", self.le_retry)
        lay.addRow("Oto. Aktarım Sıklığı (sn):", self.le_interval)
        lay.addRow("SMTP Server:", self.le_smtp_server)
        lay.addRow("SMTP Port:", self.le_smtp_port)
        lay.addRow("SMTP User:", self.le_smtp_user)
        lay.addRow("SMTP Pass:", self.le_smtp_pass)
        lay.addRow("SMTP To:", self.le_smtp_to)

        btn = QPushButton("Kaydet")
        btn.clicked.connect(self.on_save)
        lay.addRow(btn)

    def on_save(self):
        self.db_manager.set_setting("auto_start_transfers", "1" if self.chk_auto.isChecked() else "0")
        self.db_manager.set_setting("auto_start_jobs", self.le_auto_jobs.text())
        self.db_manager.set_setting("error_retry_seconds", self.le_retry.text())
        self.db_manager.set_setting("auto_transfer_interval", self.le_interval.text())
        self.db_manager.set_setting("smtp_server", self.le_smtp_server.text())
        self.db_manager.set_setting("smtp_port", self.le_smtp_port.text())
        self.db_manager.set_setting("smtp_user", self.le_smtp_user.text())
        self.db_manager.set_setting("smtp_pass", self.le_smtp_pass.text())
        self.db_manager.set_setting("smtp_to", self.le_smtp_to.text())
        QMessageBox.information(self, "Bilgi", "Ayarlar kaydedildi.")
        self.accept()

###############################################################################
# DB AYARLARI DİYALOG
###############################################################################
class DBSettingsDialog(QtWidgets.QDialog):
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Veritabanı Ayarları (config.json)")
        self.resize(400, 250)
        lay = QFormLayout(self)

        self.le_server = QLineEdit(self.config.config_data["db_server"])
        self.le_user = QLineEdit(self.config.config_data["db_user"])
        self.le_pass = QLineEdit(self.config.config_data["db_password"])
        self.le_pass.setEchoMode(QLineEdit.Password)
        self.le_db = QLineEdit(self.config.config_data["db_name"])
        self.le_port = QLineEdit(str(self.config.config_data["db_port"]))

        lay.addRow("Server:", self.le_server)
        lay.addRow("User:", self.le_user)
        lay.addRow("Password:", self.le_pass)
        lay.addRow("DB Name:", self.le_db)
        lay.addRow("Port:", self.le_port)

        btn_save = QPushButton("Kaydet")
        btn_save.clicked.connect(self.on_save)
        lay.addRow(btn_save)

    def on_save(self):
        self.config.config_data["db_server"] = self.le_server.text().strip()
        self.config.config_data["db_user"] = self.le_user.text().strip()
        self.config.config_data["db_password"] = self.le_pass.text().strip()
        self.config.config_data["db_name"] = self.le_db.text().strip()
        try:
            self.config.config_data["db_port"] = int(self.le_port.text().strip())
        except:
            self.config.config_data["db_port"] = 1433

        self.config.write_config()
        QMessageBox.information(self, "Bilgi", "config.json güncellendi.")
        self.accept()

###############################################################################
# ANA PENCERE
###############################################################################
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
        self.setWindowTitle("Mikro Veri Aktarma")
        self.resize(1100, 600)

        menubar = self.menuBar()
        menu_settings = menubar.addMenu("Ayarlar")
        act_gen = QAction("Genel Ayarlar", self)
        act_gen.triggered.connect(self.on_general_settings)
        menu_settings.addAction(act_gen)

        act_db = QAction("Veritabanı Ayarları", self)
        act_db.triggered.connect(self.on_db_settings)
        menu_settings.addAction(act_db)

        menu_saved_db = menubar.addMenu("Kayıtlı Veritabanları")
        act_manage_saved = QAction("Yönet", self)
        act_manage_saved.triggered.connect(self.on_manage_saved)
        menu_saved_db.addAction(act_manage_saved)

        tb = self.addToolBar("MainToolbar")
        act_new = QAction("Yeni Aktarım", self)
        act_new.triggered.connect(self.on_new_transfer)
        tb.addAction(act_new)

        act_run = QAction("Aktarımı Başlat", self)
        act_run.triggered.connect(self.on_run_transfer)
        tb.addAction(act_run)

        act_edit = QAction("Düzenle", self)
        act_edit.triggered.connect(self.on_edit_job)
        tb.addAction(act_edit)

        act_del = QAction("Sil", self)
        act_del.triggered.connect(self.on_delete_job)
        tb.addAction(act_del)

        act_trig = QAction("Tetikleyici Ekle", self)
        act_trig.triggered.connect(self.on_add_trigger)
        tb.addAction(act_trig)

        act_refresh = QAction("Yenile", self)
        act_refresh.triggered.connect(self.load_jobs)
        tb.addAction(act_refresh)

        w = QtWidgets.QWidget()
        self.setCentralWidget(w)
        v = QVBoxLayout(w)
        lbl = QtWidgets.QLabel("Aktarım İşleri Listesi (Sağ tık ile düzenle/sil, kopyala):")
        v.addWidget(lbl)

        self.tbl_jobs = QTableWidget()
        self.tbl_jobs.setColumnCount(3)
        self.tbl_jobs.setHorizontalHeaderLabels(["job_id", "İş Adı", "Son Çalışma"])
        self.tbl_jobs.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_jobs.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_jobs.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tbl_jobs.customContextMenuRequested.connect(self.on_jobs_context)

        v.addWidget(self.tbl_jobs)

        self.load_jobs()

        auto_start = self.db_manager.get_setting("auto_start_transfers")
        if auto_start == "1":
            self.auto_start_transfers()

        interval_str = self.db_manager.get_setting("auto_transfer_interval") or "0"
        try:
            self.auto_interval = int(interval_str)
        except:
            self.auto_interval = 0

        if self.auto_interval > 0:
            self.auto_timer = QtCore.QTimer(self)
            self.auto_timer.timeout.connect(self.on_auto_timer_tick)
            self.auto_timer.start(self.auto_interval * 1000)
        else:
            self.auto_timer = None

        self.create_tray_icon()

    def create_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        if os.path.exists(ICON_FILE):
            self.tray_icon.setIcon(QtGui.QIcon(ICON_FILE))
        else:
            self.tray_icon.setIcon(QtGui.QIcon.fromTheme("computer"))
        menu = QMenu(self)
        act_show = QAction("Göster", self, triggered=self.showNormal)
        act_hide = QAction("Gizle", self, triggered=self.hide)
        act_exit = QAction("Çıkış", self, triggered=self.close_app)
        menu.addAction(act_show)
        menu.addAction(act_hide)
        menu.addSeparator()
        menu.addAction(act_exit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def closeEvent(self, event):
        self.hide()
        event.ignore()

    def close_app(self):
        if self.auto_timer:
            self.auto_timer.stop()
        self.tray_icon.hide()
        QtWidgets.QApplication.quit()

    def load_jobs(self):
        c = self.db_manager.conn.cursor(as_dict=True)
        c.execute("SELECT job_id, job_name, last_run_date FROM TransferJobs ORDER BY job_id DESC")
        rows = c.fetchall()
        self.tbl_jobs.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self.tbl_jobs.setItem(i, 0, QTableWidgetItem(str(r["job_id"])))
            self.tbl_jobs.setItem(i, 1, QTableWidgetItem(r["job_name"]))
            self.tbl_jobs.setItem(i, 2, QTableWidgetItem(str(r["last_run_date"]) if r["last_run_date"] else ""))

    def on_jobs_context(self, pos):
        menu = QMenu()
        menu.addAction("Düzenle", self.on_edit_job)
        menu.addAction("Sil", self.on_delete_job)
        menu.addAction("Aktarımı Başlat", self.on_run_transfer)
        menu.addAction("Kopyala (İşi Çoğalt)", self.on_duplicate_job)
        menu.exec_(self.tbl_jobs.mapToGlobal(pos))

    def on_new_transfer(self):
        wiz = TransferWizard(self.db_manager, self)
        if wiz.exec_() == QtWidgets.QDialog.Accepted:
            self.load_jobs()

    def on_run_transfer(self):
        row = self.tbl_jobs.currentRow()
        if row < 0:
            return
        job_id_item = self.tbl_jobs.item(row, 0)
        if not job_id_item:
            return
        job_id = int(job_id_item.text())
        runner = TransferJobRunner(self.db_manager, job_id)
        runner.run()
        self.load_jobs()

    def on_edit_job(self):
        row = self.tbl_jobs.currentRow()
        if row < 0:
            return
        job_id_item = self.tbl_jobs.item(row, 0)
        if not job_id_item:
            return
        job_id = int(job_id_item.text())
        dlg = EditJobDialog(self.db_manager, job_id, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.load_jobs()

    def on_delete_job(self):
        row = self.tbl_jobs.currentRow()
        if row < 0:
            return
        job_id_item = self.tbl_jobs.item(row, 0)
        if not job_id_item:
            return
        job_id = int(job_id_item.text())
        msg = QMessageBox.question(self, "Sil?", "Seçili aktarım işi silinsin mi?")
        if msg == QMessageBox.Yes:
            self.db_manager.delete_transfer_job(job_id)
            self.load_jobs()

    def on_add_trigger(self):
        row = self.tbl_jobs.currentRow()
        if row < 0:
            return
        job_id_item = self.tbl_jobs.item(row, 0)
        if not job_id_item:
            return
        job_id = int(job_id_item.text())
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Tetikleyici Ekle")
        layout = QVBoxLayout(dlg)
        trigger_panel = TriggerPanel(self.db_manager)
        layout.addWidget(trigger_panel)
        btn = QPushButton("Kaydet")
        def do_save():
            trig_data = trigger_panel.get_trigger_data()
            if all(trig_data.values()):
                self.db_manager.insert_trigger(
                    job_id=job_id,
                    dep_job_id=trig_data["dep_job_id"],
                    check_table=trig_data["check_table"],
                    check_column=trig_data["check_column"],
                    check_value=trig_data["check_value"]
                )
            dlg.accept()
        btn.clicked.connect(do_save)
        layout.addWidget(btn)

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.load_jobs()

    def on_duplicate_job(self):
        row = self.tbl_jobs.currentRow()
        if row < 0:
            return
        job_id_item = self.tbl_jobs.item(row, 0)
        if not job_id_item:
            return
        job_id = int(job_id_item.text())
        new_id = self.db_manager.duplicate_job(job_id)
        if new_id:
            QMessageBox.information(self, "Kopyalama", f"Aktarım işi kopyalandı (Yeni ID: {new_id}).")
            self.load_jobs()

    def on_general_settings(self):
        dlg = GeneralSettingsDialog(self.db_manager, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            # Timer güncelle
            if self.auto_timer:
                self.auto_timer.stop()
            interval_str = self.db_manager.get_setting("auto_transfer_interval") or "0"
            try:
                val = int(interval_str)
            except:
                val = 0
            self.auto_interval = val
            if val > 0:
                self.auto_timer = QtCore.QTimer(self)
                self.auto_timer.timeout.connect(self.on_auto_timer_tick)
                self.auto_timer.start(val * 1000)
            else:
                self.auto_timer = None

    def on_db_settings(self):
        dlg = DBSettingsDialog(self.db_manager.config, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self.db_manager.close()
            self.db_manager.connect()
            self.db_manager.create_tables_if_not_exists()
            self.load_jobs()

    def on_manage_saved(self):
        dlg = SavedDBDialog(self.db_manager, self)
        dlg.exec_()

    def auto_start_transfers(self):
        jstr = self.db_manager.get_setting("auto_start_jobs") or ""
        if not jstr:
            return
        job_ids = jstr.split(",")
        for j in job_ids:
            j = j.strip()
            if j.isdigit():
                runner = TransferJobRunner(self.db_manager, int(j))
                runner.run()

    def on_auto_timer_tick(self):
        jstr = self.db_manager.get_setting("auto_start_jobs") or ""
        if not jstr:
            return
        job_ids = jstr.split(",")
        for j in job_ids:
            j = j.strip()
            if j.isdigit():
                runner = TransferJobRunner(self.db_manager, int(j))
                runner.run()
        self.load_jobs()

###############################################################################
# MAIN
###############################################################################
def main():
    app = QtWidgets.QApplication(sys.argv)
    config = ConfigManager()
    dbm = DatabaseManager(config)
    dbm.create_tables_if_not_exists()

    mw = MainWindow(dbm)
    mw.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
