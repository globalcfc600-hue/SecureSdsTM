import os
import time
import sqlite3
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_FILE = "sds_security.db"

def init_db():
    """Veritabanını ve gerekli tabloları oluşturur."""
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # 2 Saatlik kilitleri tutan tablo
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS kilitler (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kilit_bitis REAL
            )
        """)
        # Gelen SMS loglarını tutan tablo
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sms_loglari (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zaman REAL
            )
        """)
        conn.commit()

def kilit_durumu_kontrol_et():
    """Mevcut aktif bir 2 saatlik kilit olup olmadığına bakar."""
    su_an = time.time()
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT kilit_bitis FROM kilitler ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            kilit_bitis = row[0]
            if su_an < kilit_bitis:
                return int((kilit_bitis - su_an) / 60) # Kalan dakikayı dön
    return 0

def kilidi_baslat():
    """Sisteme 2 saatlik (7200 saniye) kesin kilit yazar."""
    su_an = time.time()
    kilit_bitis = su_an + 7200
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO kilitler (kilit_bitis) VALUES (?)", (kilit_bitis,))
        conn.commit()

def sms_logla_ve_saldiri_bak():
    """Gelen şüpheli SMS'i kaydeder ve son 1 dakikadaki yoğunluğu ölçer."""
    su_an = time.time()
    bir_dakika_once = su_an - 60
    
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        # Yeni log ekle
        cursor.execute("INSERT INTO sms_loglari (zaman) VALUES (?)", (su_an,))
        # 1 dakikadan eski logları temizle (Veritabanı şişmesin)
        cursor.execute("DELETE FROM sms_loglari WHERE zaman < ?", (bir_dakika_once,))
        # Son 1 dakikadaki toplam istek sayısını say
        cursor.execute("SELECT COUNT(*) FROM sms_loglari")
        istek_sayisi = cursor.fetchone()[0]
        conn.commit()
        
    return istek_sayisi > 3

# Sunucu ilk açıldığında veritabanını hazırla
init_db()

@app.route("/sms-kontrol", methods=["POST"])
def sms_kontrol():
    # 1. AŞAMA: Kalıcı Veritabanından Kilit Kontrolü
    kalan_dk = kilit_durumu_kontrol_et()
    if kalan_dk > 0:
        return jsonify({
            "durum": "KİLİTLİ",
            "aksiyon": "KORUMAYI_AC",
            "mesaj": f"SDS Defans Aktif: Sistem kilitli. Kalan süre: {kalan_dk} dakika."
        }), 200

    # iOS Kestirmeler'den gelen JSON verisini al
    data = request.get_json() or {}
    mesaj = data.get("mesaj", "").lower()
    
    # Profesyonel OTP Filtre Kelimeleri
    tetikleyiciler = ["kod", "onay", "verification", "otp", "shifre", "giriş", "şifre"]
    
    if any(kelime in mesaj for kelime in tetikleyiciler):
        # 2. AŞAMA: Hız ve Yoğunluk Kontrolü
        saldiri_var_mi = sms_logla_ve_saldiri_bak()
        
        if saldiri_var_mi:
            # 3. AŞAMA: Kalıcı Kilit Başlatma
            kilidi_baslat()
            return jsonify({
                "durum": "SALDIRI_ALINDI",
                "aksiyon": "KORUMAYI_AC",
                "mesaj": "SDS Security: SMS Bomber algılandı! Kalkan devreye alınıyor."
            }), 200

    return jsonify({"durum": "TEMİZ", "aksiyon": "YOK"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
