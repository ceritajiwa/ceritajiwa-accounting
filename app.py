"""
Cerita Jiwa - Sistem Pembukuan Internal (Supabase Edition)
Database: PostgreSQL via Supabase
"""

import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from datetime import datetime, date, timedelta
import os
import re
from io import BytesIO

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# ============================================================
# DATABASE CONFIG (SUPABASE POSTGRESQL)
# ============================================================

def get_db_url():
    try:
        return st.secrets["database"]["url"]
    except:
        pass
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://postgres:password@localhost:5432/postgres"
    )

def get_connection():
    conn = psycopg2.connect(get_db_url(), cursor_factory=RealDictCursor)
    return conn

def init_database():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS akun (
        id SERIAL PRIMARY KEY, kode_akun VARCHAR(20) UNIQUE NOT NULL,
        nama_akun VARCHAR(100) NOT NULL, tipe_akun VARCHAR(20) NOT NULL CHECK(tipe_akun IN ('Aset','Kewajiban','Ekuitas','Pendapatan','Beban')),
        saldo_normal VARCHAR(10) NOT NULL CHECK(saldo_normal IN ('debit','kredit')),
        parent_id INTEGER, is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (parent_id) REFERENCES akun(id)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jurnal (
        id SERIAL PRIMARY KEY, tanggal DATE NOT NULL, no_bukti VARCHAR(50),
        keterangan TEXT NOT NULL, total_debit NUMERIC(15,2) DEFAULT 0,
        total_kredit NUMERIC(15,2) DEFAULT 0, is_posted INTEGER DEFAULT 1,
        periode VARCHAR(10), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        created_by VARCHAR(50)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS jurnal_detail (
        id SERIAL PRIMARY KEY, jurnal_id INTEGER NOT NULL, akun_id INTEGER NOT NULL,
        debit NUMERIC(15,2) DEFAULT 0, kredit NUMERIC(15,2) DEFAULT 0, keterangan TEXT,
        FOREIGN KEY (jurnal_id) REFERENCES jurnal(id) ON DELETE CASCADE,
        FOREIGN KEY (akun_id) REFERENCES akun(id)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoice (
        id SERIAL PRIMARY KEY, no_invoice VARCHAR(50) UNIQUE NOT NULL,
        tanggal DATE NOT NULL, due_date DATE, customer_name VARCHAR(200) NOT NULL,
        customer_email VARCHAR(100), customer_phone VARCHAR(50), customer_address TEXT,
        subtotal NUMERIC(15,2) DEFAULT 0, ppn NUMERIC(15,2) DEFAULT 0,
        total NUMERIC(15,2) DEFAULT 0, status VARCHAR(20) DEFAULT 'draft' CHECK(status IN ('draft','sent','paid','cancelled')),
        is_paid INTEGER DEFAULT 0, paid_date DATE, payment_method VARCHAR(50), notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoice_item (
        id SERIAL PRIMARY KEY, invoice_id INTEGER NOT NULL, deskripsi TEXT NOT NULL,
        qty NUMERIC(10,2) DEFAULT 1, satuan VARCHAR(20) DEFAULT 'pcs',
        harga NUMERIC(15,2) DEFAULT 0, total NUMERIC(15,2) DEFAULT 0,
        FOREIGN KEY (invoice_id) REFERENCES invoice(id) ON DELETE CASCADE
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS periode_akuntansi (
        id SERIAL PRIMARY KEY, tahun INTEGER NOT NULL, bulan INTEGER,
        is_closed INTEGER DEFAULT 0, closed_at TIMESTAMP, closed_by VARCHAR(50),
        UNIQUE(tahun, bulan)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pajak_config (
        id SERIAL PRIMARY KEY, jenis_pajak VARCHAR(50) NOT NULL,
        tarif NUMERIC(5,2) DEFAULT 0, keterangan TEXT, is_active INTEGER DEFAULT 1
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS log_aktivitas (
        id SERIAL PRIMARY KEY, tipe VARCHAR(50), deskripsi TEXT,
        user_name VARCHAR(50), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    conn.commit()
    cursor.execute("SELECT COUNT(*) as cnt FROM akun")
    if cursor.fetchone()['cnt'] == 0:
        insert_default_accounts(cursor)
    cursor.execute("SELECT COUNT(*) as cnt FROM pajak_config")
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("""
            INSERT INTO pajak_config (jenis_pajak, tarif, keterangan) VALUES
            ('PPN', 11.0, 'Pajak Pertambahan Nilai'),
            ('PPh 21', 5.0, 'Pajak Penghasilan Pasal 21'),
            ('PPh 23', 2.0, 'Pajak Penghasilan Pasal 23'),
            ('PPh Final', 0.5, 'Pajak Penghasilan Final')
        """)
    conn.commit()
    conn.close()

def insert_default_accounts(cursor):
    accounts = [
        ('1-1000','Aset Lancar','Aset','debit',None),('1-1100','Kas','Aset','debit',1),
        ('1-1101','Kas Kecil','Aset','debit',1),('1-1200','Bank','Aset','debit',1),
        ('1-1201','Bank BCA','Aset','debit',4),('1-1202','Bank Mandiri','Aset','debit',4),
        ('1-1203','Bank BNI','Aset','debit',4),('1-1204','Bank BRI','Aset','debit',4),
        ('1-1300','Piutang Usaha','Aset','debit',1),('1-1400','Perlengkapan','Aset','debit',1),
        ('1-1500','Pajak Dibayar Dimuka','Aset','debit',1),('1-2000','Aset Tetap','Aset','debit',None),
        ('1-2100','Peralatan Kantor','Aset','debit',6),('1-2200','Kendaraan','Aset','debit',6),
        ('1-2300','Akumulasi Penyusutan','Aset','kredit',6),('2-1000','Kewajiban Lancar','Kewajiban','kredit',None),
        ('2-1100','Utang Usaha','Kewajiban','kredit',8),('2-1200','Utang Bank','Kewajiban','kredit',8),
        ('2-1300','Utang Cicilan','Kewajiban','kredit',8),('2-1400','Pendapatan Diterima Dimuka','Kewajiban','kredit',8),
        ('2-1500','Utang Pajak','Kewajiban','kredit',8),('3-1000','Ekuitas','Ekuitas','kredit',None),
        ('3-1100','Modal Pemilik','Ekuitas','kredit',15),('3-1200','Prive','Ekuitas','debit',15),
        ('3-1300','Laba Ditahan','Ekuitas','kredit',15),('3-1400','Laba Rugi Berjalan','Ekuitas','kredit',15),
        ('4-1000','Pendapatan','Pendapatan','kredit',None),('4-1100','Pendapatan Training','Pendapatan','kredit',20),
        ('4-1200','Pendapatan Produk Digital','Pendapatan','kredit',20),('4-1300','Pendapatan Konsultasi','Pendapatan','kredit',20),
        ('4-1400','Pendapatan Lain-lain','Pendapatan','kredit',20),('5-1000','Beban','Beban','debit',None),
        ('5-1100','Beban Gaji','Beban','debit',25),('5-1200','Beban Sewa','Beban','debit',25),
        ('5-1300','Beban Listrik & Air','Beban','debit',25),('5-1400','Beban Internet & Telepon','Beban','debit',25),
        ('5-1500','Beban Perlengkapan','Beban','debit',25),('5-1600','Beban Pemasaran','Beban','debit',25),
        ('5-1700','Beban Perjalanan Dinas','Beban','debit',25),('5-1800','Beban Penyusutan','Beban','debit',25),
        ('5-1900','Beban Bunga','Beban','debit',25),('5-2000','Beban Pajak','Beban','debit',25),
        ('5-2100','Beban Lain-lain','Beban','debit',25),
    ]
    parent_map = {}
    for i, (kode, nama, tipe, saldo, parent) in enumerate(accounts, 1):
        if parent is None:
            cursor.execute("INSERT INTO akun (kode_akun, nama_akun, tipe_akun, saldo_normal, parent_id) VALUES (%s,%s,%s,%s,NULL) RETURNING id", (kode, nama, tipe, saldo))
            parent_map[i] = cursor.fetchone()['id']
        else:
            cursor.execute("INSERT INTO akun (kode_akun, nama_akun, tipe_akun, saldo_normal, parent_id) VALUES (%s,%s,%s,%s,%s)", (kode, nama, tipe, saldo, parent_map.get(parent)))

def format_rupiah(angka):
    if angka is None: return "Rp 0"
    try: return f"Rp {float(angka):,.0f}".replace(",",".")
    except: return str(angka)

def parse_rupiah(text):
    if not text: return None
    cleaned = re.sub(r'[Rp\s\.]','',str(text)).replace(',','.')
    try: return float(cleaned)
    except: return None

def get_next_invoice_number():
    conn = get_connection()
    cursor = conn.cursor()
    current_year = datetime.now().year
    cursor.execute("SELECT no_invoice FROM invoice WHERE no_invoice LIKE %s ORDER BY id DESC LIMIT 1", (f"INV-{current_year}%",))
    result = cursor.fetchone()
    conn.close()
    if result:
        last_num = int(result['no_invoice'].split('-')[-1])
        return f"INV-{current_year}-{last_num+1:04d}"
    return f"INV-{current_year}-0001"

def get_next_journal_number():
    conn = get_connection()
    cursor = conn.cursor()
    current_year = datetime.now().year
    cursor.execute("SELECT id FROM jurnal WHERE periode LIKE %s ORDER BY id DESC LIMIT 1", (f"{current_year}%",))
    result = cursor.fetchone()
    conn.close()
    if result:
        return f"BUK-{current_year}-{result['id']+1:04d}"
    return f"BUK-{current_year}-0001"

def log_activity(tipe, deskripsi):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO log_aktivitas (tipe, deskripsi, user_name) VALUES (%s,%s,%s)", (tipe, deskripsi, st.session_state.get('username','admin')))
    conn.commit()
    conn.close()

def get_month_name(bulan):
    months = ['','Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember']
    return months[bulan] if 1 <= bulan <= 12 else ''

 # ============================================================
# AI JOURNAL ASSISTANT
# ============================================================

def ai_journal_assistant(deskripsi, nilai_rupiah=None):
    if nilai_rupiah is None:
        numbers = re.findall(r'[\d\.]+(?:\,\d+)?', deskripsi)
        amounts = []
        for num in numbers:
            try:
                clean = num.replace('.','').replace(',','.')
                val = float(clean)
                if val > 1000: amounts.append(val)
            except: continue
        if amounts: nilai_rupiah = max(amounts)
    
    deskripsi_lower = deskripsi.lower()
    jurnal_entries = []
    questions = []
    
    if nilai_rupiah is None:
        questions.append("Berapa nilai rupiah transaksi ini?")
    
    if any(w in deskripsi_lower for w in ['beli','pembelian','membeli']):
        if any(w in deskripsi_lower for w in ['motor','mobil','kendaraan']):
            if any(w in deskripsi_lower for w in ['cicil','cicilan','kredit']):
                dp = None
                dp_match = re.search(r'dp\s*[:\s]*([\d\.]+(?:\,\d+)?)', deskripsi_lower)
                if dp_match: dp = parse_rupiah(dp_match.group(1))
                if dp and nilai_rupiah:
                    jurnal_entries = [
                        {'akun':'Kendaraan','debit':nilai_rupiah,'kredit':0},
                        {'akun':'Utang Cicilan','debit':0,'kredit':nilai_rupiah-dp},
                        {'akun':'Bank BCA','debit':0,'kredit':dp},
                    ]
                elif nilai_rupiah:
                    questions.append("Berapa DP (Down Payment) yang dibayarkan?")
            else:
                jurnal_entries = [
                    {'akun':'Kendaraan','debit':nilai_rupiah,'kredit':0},
                    {'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah},
                ]
        elif any(w in deskripsi_lower for w in ['peralatan','perlengkapan','komputer','laptop']):
            jurnal_entries = [
                {'akun':'Peralatan Kantor','debit':nilai_rupiah,'kredit':0},
                {'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah},
            ]
        else:
            jurnal_entries = [
                {'akun':'Perlengkapan','debit':nilai_rupiah,'kredit':0},
                {'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah},
            ]
    elif any(w in deskripsi_lower for w in ['jual','penjualan','terima']):
        if any(w in deskripsi_lower for w in ['training','pelatihan']):
            jurnal_entries = [
                {'akun':'Bank BCA','debit':nilai_rupiah,'kredit':0},
                {'akun':'Pendapatan Training','debit':0,'kredit':nilai_rupiah},
            ]
        elif any(w in deskripsi_lower for w in ['produk digital','ebook','template','digital']):
            jurnal_entries = [
                {'akun':'Bank BCA','debit':nilai_rupiah,'kredit':0},
                {'akun':'Pendapatan Produk Digital','debit':0,'kredit':nilai_rupiah},
            ]
        elif any(w in deskripsi_lower for w in ['konsultasi','consulting']):
            jurnal_entries = [
                {'akun':'Bank BCA','debit':nilai_rupiah,'kredit':0},
                {'akun':'Pendapatan Konsultasi','debit':0,'kredit':nilai_rupiah},
            ]
        else:
            jurnal_entries = [
                {'akun':'Bank BCA','debit':nilai_rupiah,'kredit':0},
                {'akun':'Pendapatan Lain-lain','debit':0,'kredit':nilai_rupiah},
            ]
    elif any(w in deskripsi_lower for w in ['bayar','pembayaran','dibayar']):
        if any(w in deskripsi_lower for w in ['gaji','honor']):
            jurnal_entries = [{'akun':'Beban Gaji','debit':nilai_rupiah,'kredit':0},{'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah}]
        elif any(w in deskripsi_lower for w in ['sewa','kontrakan','ruko','kantor']):
            jurnal_entries = [{'akun':'Beban Sewa','debit':nilai_rupiah,'kredit':0},{'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah}]
        elif any(w in deskripsi_lower for w in ['listrik','air','pln','pdam']):
            jurnal_entries = [{'akun':'Beban Listrik & Air','debit':nilai_rupiah,'kredit':0},{'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah}]
        elif any(w in deskripsi_lower for w in ['internet','telepon','hp','pulsa','wifi']):
            jurnal_entries = [{'akun':'Beban Internet & Telepon','debit':nilai_rupiah,'kredit':0},{'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah}]
        elif any(w in deskripsi_lower for w in ['iklan','promosi','marketing','ads']):
            jurnal_entries = [{'akun':'Beban Pemasaran','debit':nilai_rupiah,'kredit':0},{'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah}]
        elif any(w in deskripsi_lower for w in ['pajak','spt','pph','ppn']):
            jurnal_entries = [{'akun':'Beban Pajak','debit':nilai_rupiah,'kredit':0},{'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah}]
        elif any(w in deskripsi_lower for w in ['cicilan','angsuran','kredit']):
            bunga_match = re.search(r'bunga\s*[:\s]*(\d+(?:[\.,]\d+)?)\s*%?', deskripsi_lower)
            if bunga_match and nilai_rupiah:
                bunga_rate = float(bunga_match.group(1).replace(',','.'))/100
                bunga_amount = nilai_rupiah * bunga_rate
                pokok = nilai_rupiah - bunga_amount
                jurnal_entries = [
                    {'akun':'Beban Bunga','debit':bunga_amount,'kredit':0},
                    {'akun':'Utang Cicilan','debit':pokok,'kredit':0},
                    {'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah},
                ]
            else:
                jurnal_entries = [{'akun':'Utang Cicilan','debit':nilai_rupiah,'kredit':0},{'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah}]
    elif any(w in deskripsi_lower for w in ['modal','setor','investasi']):
        jurnal_entries = [{'akun':'Bank BCA','debit':nilai_rupiah,'kredit':0},{'akun':'Modal Pemilik','debit':0,'kredit':nilai_rupiah}]
    elif any(w in deskripsi_lower for w in ['tarik','prive','pengambilan']):
        jurnal_entries = [{'akun':'Prive','debit':nilai_rupiah,'kredit':0},{'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah}]
    elif any(w in deskripsi_lower for w in ['biaya','beban','ongkir','transport']):
        if any(w in deskripsi_lower for w in ['perjalanan','dinas','hotel','transport']):
            jurnal_entries = [{'akun':'Beban Perjalanan Dinas','debit':nilai_rupiah,'kredit':0},{'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah}]
        else:
            jurnal_entries = [{'akun':'Beban Lain-lain','debit':nilai_rupiah,'kredit':0},{'akun':'Bank BCA','debit':0,'kredit':nilai_rupiah}]
    
    if not jurnal_entries and not questions:
        questions.append("Transaksi ini termasuk kategori apa? (Pembelian, Penjualan, Pembayaran, dll)")
    
    return {'jurnal':jurnal_entries,'questions':questions,'nilai_terdeteksi':nilai_rupiah}

def get_all_accounts():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT a.*, p.nama_akun as parent_name 
        FROM akun a LEFT JOIN akun p ON a.parent_id = p.id 
        WHERE a.is_active = 1 ORDER BY a.kode_akun
    """, conn)
    conn.close()
    return df

# ============================================================
# FINANCIAL REPORTS
# ============================================================

def get_neraca(tahun=None, bulan=None):
    conn = get_connection()
    date_filter = ""
    params = []
    if tahun and bulan:
        date_filter = "AND TO_CHAR(j.tanggal,'YYYY-MM') <= %s"
        params.append(f"{tahun}-{bulan:02d}")
    elif tahun:
        date_filter = "AND TO_CHAR(j.tanggal,'YYYY') <= %s"
        params.append(str(tahun))
    
    query = f"""
    SELECT a.kode_akun, a.nama_akun, a.tipe_akun, a.saldo_normal,
        COALESCE(SUM(CASE WHEN jd.debit > 0 THEN jd.debit ELSE 0 END), 0) as total_debit,
        COALESCE(SUM(CASE WHEN jd.kredit > 0 THEN jd.kredit ELSE 0 END), 0) as total_kredit
    FROM akun a
    LEFT JOIN jurnal_detail jd ON a.id = jd.akun_id
    LEFT JOIN jurnal j ON jd.jurnal_id = j.id AND j.is_posted = 1 {date_filter}
    WHERE a.is_active = 1 AND a.parent_id IS NOT NULL
    GROUP BY a.id, a.kode_akun, a.nama_akun, a.tipe_akun, a.saldo_normal
    ORDER BY a.kode_akun
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    def calc_balance(row):
        if row['saldo_normal'] == 'debit':
            return row['total_debit'] - row['total_kredit']
        return row['total_kredit'] - row['total_debit']
    df['saldo'] = df.apply(calc_balance, axis=1)
    return df

def get_laba_rugi(tahun=None, bulan=None):
    conn = get_connection()
    date_filter = ""
    params = []
    if tahun and bulan:
        date_filter = "AND TO_CHAR(j.tanggal,'YYYY-MM') = %s"
        params.append(f"{tahun}-{bulan:02d}")
    elif tahun:
        date_filter = "AND TO_CHAR(j.tanggal,'YYYY') = %s"
        params.append(str(tahun))
    
    query = f"""
    SELECT a.kode_akun, a.nama_akun, a.tipe_akun,
        COALESCE(SUM(CASE WHEN jd.debit > 0 THEN jd.debit ELSE 0 END), 0) as total_debit,
        COALESCE(SUM(CASE WHEN jd.kredit > 0 THEN jd.kredit ELSE 0 END), 0) as total_kredit
    FROM akun a
    LEFT JOIN jurnal_detail jd ON a.id = jd.akun_id
    LEFT JOIN jurnal j ON jd.jurnal_id = j.id AND j.is_posted = 1 {date_filter}
    WHERE a.is_active = 1 AND a.tipe_akun IN ('Pendapatan','Beban')
    GROUP BY a.id, a.kode_akun, a.nama_akun, a.tipe_akun
    ORDER BY a.kode_akun
    """
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    def calc_balance(row):
        if row['tipe_akun'] == 'Pendapatan':
            return row['total_kredit'] - row['total_debit']
        return row['total_debit'] - row['total_kredit']
    df['saldo'] = df.apply(calc_balance, axis=1)
    return df

def get_buku_besar(akun_id, tahun=None, bulan=None):
    conn = get_connection()
    date_filter = ""
    params = [akun_id]
    if tahun and bulan:
        date_filter = "AND TO_CHAR(j.tanggal,'YYYY-MM') = %s"
        params.append(f"{tahun}-{bulan:02d}")
    elif tahun:
        date_filter = "AND TO_CHAR(j.tanggal,'YYYY') = %s"
        params.append(str(tahun))
    
    query = f"""
    SELECT j.tanggal, j.no_bukti, j.keterangan, jd.debit, jd.kredit, jd.keterangan as detail_keterangan
    FROM jurnal_detail jd
    JOIN jurnal j ON jd.jurnal_id = j.id
    WHERE jd.akun_id = %s AND j.is_posted = 1 {date_filter}
    ORDER BY j.tanggal, j.id
    """
    df = pd.read_sql_query(query, conn, params=params)
    akun_info = pd.read_sql_query("SELECT * FROM akun WHERE id = %s", conn, params=(akun_id,))
    conn.close()
    if not df.empty and not akun_info.empty:
        saldo_normal = akun_info.iloc[0]['saldo_normal']
        balance = 0
        balances = []
        for _, row in df.iterrows():
            if saldo_normal == 'debit': balance += row['debit'] - row['kredit']
            else: balance += row['kredit'] - row['debit']
            balances.append(balance)
        df['saldo'] = balances
    return df, akun_info

def get_jurnal_list(limit=100, tahun=None, bulan=None):
    conn = get_connection()
    date_filter = ""
    params = []
    if tahun and bulan:
        date_filter = "WHERE TO_CHAR(tanggal,'YYYY-MM') = %s"
        params.append(f"{tahun}-{bulan:02d}")
    elif tahun:
        date_filter = "WHERE TO_CHAR(tanggal,'YYYY') = %s"
        params.append(str(tahun))
    query = f"SELECT * FROM jurnal {date_filter} ORDER BY tanggal DESC, id DESC LIMIT %s"
    params.append(limit)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_jurnal_detail(jurnal_id):
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT jd.*, a.kode_akun, a.nama_akun, a.tipe_akun
        FROM jurnal_detail jd
        JOIN akun a ON jd.akun_id = a.id
        WHERE jd.jurnal_id = %s
    """, conn, params=(jurnal_id,))
    conn.close()
    return df

 # ============================================================
# INVOICE FUNCTIONS
# ============================================================

def create_invoice(data, items):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO invoice (no_invoice, tanggal, due_date, customer_name, customer_email,
                           customer_phone, customer_address, subtotal, ppn, total, status, notes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (data['no_invoice'], data['tanggal'], data['due_date'], data['customer_name'],
          data.get('customer_email'), data.get('customer_phone'), data.get('customer_address'),
          data['subtotal'], data.get('ppn',0), data['total'], data.get('status','draft'), data.get('notes')))
    invoice_id = cursor.fetchone()['id']
    for item in items:
        cursor.execute("""
            INSERT INTO invoice_item (invoice_id, deskripsi, qty, satuan, harga, total)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (invoice_id, item['deskripsi'], item['qty'], item.get('satuan','pcs'), item['harga'], item['total']))
    conn.commit()
    conn.close()
    return invoice_id

def get_invoices(status=None, limit=100):
    conn = get_connection()
    query = "SELECT * FROM invoice"
    params = []
    if status:
        query += " WHERE status = %s"
        params.append(status)
    query += " ORDER BY tanggal DESC LIMIT %s"
    params.append(limit)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def get_invoice_by_id(invoice_id):
    conn = get_connection()
    invoice = pd.read_sql_query("SELECT * FROM invoice WHERE id = %s", conn, params=(invoice_id,))
    items = pd.read_sql_query("SELECT * FROM invoice_item WHERE invoice_id = %s", conn, params=(invoice_id,))
    conn.close()
    return invoice, items

def update_invoice_status(invoice_id, status, paid_date=None, payment_method=None):
    conn = get_connection()
    cursor = conn.cursor()
    if status == 'paid':
        cursor.execute("UPDATE invoice SET status=%s, is_paid=1, paid_date=%s, payment_method=%s WHERE id=%s",
                     (status, paid_date or datetime.now().date(), payment_method, invoice_id))
    else:
        cursor.execute("UPDATE invoice SET status=%s, is_paid=0, paid_date=NULL WHERE id=%s", (status, invoice_id))
    conn.commit()
    conn.close()

# ============================================================
# PDF GENERATORS
# ============================================================

def generate_invoice_pdf(invoice_id):
    if not REPORTLAB_AVAILABLE: return None
    invoice_df, items_df = get_invoice_by_id(invoice_id)
    if invoice_df.empty: return None
    inv = invoice_df.iloc[0]
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#344A61'), spaceAfter=30, alignment=TA_CENTER)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=12, textColor=colors.HexColor('#344A61'), spaceAfter=6)
    normal_style = styles['Normal']
    elements = []
    elements.append(Paragraph("<b>INVOICE</b>", title_style))
    elements.append(Spacer(1, 20))
    company_data = [
        [Paragraph("<b>CERITA JIWA</b>", heading_style), Paragraph(f"<b>No. Invoice:</b> {inv['no_invoice']}", normal_style)],
        [Paragraph("Training & Produk Digital", normal_style), Paragraph(f"<b>Tanggal:</b> {inv['tanggal']}", normal_style)],
        [Paragraph("", normal_style), Paragraph(f"<b>Jatuh Tempo:</b> {inv['due_date'] or '-'}", normal_style)],
    ]
    company_table = Table(company_data, colWidths=[8*cm, 8*cm])
    company_table.setStyle(TableStyle([('ALIGN',(0,0),(0,-1),'LEFT'),('ALIGN',(-1,0),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'TOP')]))
    elements.append(company_table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<b>Ditagihkan Kepada:</b>", heading_style))
    elements.append(Paragraph(f"{inv['customer_name']}", normal_style))
    if inv['customer_address']: elements.append(Paragraph(f"{inv['customer_address']}", normal_style))
    if inv['customer_email']: elements.append(Paragraph(f"Email: {inv['customer_email']}", normal_style))
    if inv['customer_phone']: elements.append(Paragraph(f"Telepon: {inv['customer_phone']}", normal_style))
    elements.append(Spacer(1, 20))
    table_data = [['No','Deskripsi','Qty','Satuan','Harga','Total']]
    for i, (_, item) in enumerate(items_df.iterrows(), 1):
        table_data.append([str(i), item['deskripsi'], str(item['qty']), item['satuan'], format_rupiah(item['harga']), format_rupiah(item['total'])])
    table_data.append(['','','','','Subtotal', format_rupiah(inv['subtotal'])])
    if inv['ppn'] and inv['ppn'] > 0:
        table_data.append(['','','','','PPN (11%)', format_rupiah(inv['ppn'])])
    table_data.append(['','','','', Paragraph("<b>Total</b>", normal_style), Paragraph(f"<b>{format_rupiah(inv['total'])}</b>", normal_style)])
    items_table = Table(table_data, colWidths=[1*cm, 6*cm, 2*cm, 2*cm, 3*cm, 3*cm])
    items_table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0), colors.HexColor('#344A61')),
        ('TEXTCOLOR',(0,0),(-1,0), colors.whitesmoke),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),('ALIGN',(1,1),(1,-1),'LEFT'),('ALIGN',(-2,-3),(-1,-1),'RIGHT'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,0),10),('BOTTOMPADDING',(0,0),(-1,0),12),
        ('GRID',(0,0),(-1,-1),0.5, colors.grey),('BACKGROUND',(0,-1),(-1,-1), colors.HexColor('#E8EAEC')),
        ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("<b>Informasi Pembayaran:</b>", heading_style))
    elements.append(Paragraph("Bank BCA: 123-456-7890 a.n. PT Cerita Jiwa", normal_style))
    elements.append(Paragraph("Bank Mandiri: 098-765-4321 a.n. PT Cerita Jiwa", normal_style))
    elements.append(Spacer(1, 30))
    status_text = inv['status'].upper()
    status_color = colors.green if status_text == 'PAID' else colors.orange
    elements.append(Paragraph(f"<b>Status:</b> <font color='{status_color.hexval()}'>{status_text}</font>", normal_style))
    if inv['notes']:
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"<b>Catatan:</b> {inv['notes']}", normal_style))
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

def generate_neraca_pdf(tahun, bulan=None):
    if not REPORTLAB_AVAILABLE: return None
    df = get_neraca(tahun, bulan)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("<b>NERACA</b>", styles['Heading1']))
    periode = f"Periode: {get_month_name(bulan)} {tahun}" if bulan else f"Tahun: {tahun}"
    elements.append(Paragraph(periode, styles['Normal']))
    elements.append(Spacer(1, 20))
    for tipe in ['Aset','Kewajiban','Ekuitas']:
        tipe_df = df[df['tipe_akun'] == tipe]
        if not tipe_df.empty:
            elements.append(Paragraph(f"<b>{tipe.upper()}</b>", styles['Heading2']))
            data = [['Kode Akun','Nama Akun','Saldo']]
            total = 0
            for _, row in tipe_df.iterrows():
                data.append([row['kode_akun'], row['nama_akun'], format_rupiah(row['saldo'])])
                total += row['saldo']
            data.append(['', f'Total {tipe}', format_rupiah(total)])
            table = Table(data, colWidths=[3*cm, 8*cm, 5*cm])
            table.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0), colors.HexColor('#344A61')),
                ('TEXTCOLOR',(0,0),(-1,0), colors.whitesmoke),
                ('ALIGN',(0,0),(-1,-1),'LEFT'),('ALIGN',(-1,0),(-1,-1),'RIGHT'),
                ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('GRID',(0,0),(-1,-2),0.5, colors.grey),
                ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('BACKGROUND',(0,-1),(-1,-1), colors.HexColor('#E8EAEC')),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 10))
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

def generate_laba_rugi_pdf(tahun, bulan=None):
    if not REPORTLAB_AVAILABLE: return None
    df = get_laba_rugi(tahun, bulan)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("<b>LAPORAN LABA RUGI</b>", styles['Heading1']))
    periode = f"Periode: {get_month_name(bulan)} {tahun}" if bulan else f"Tahun: {tahun}"
    elements.append(Paragraph(periode, styles['Normal']))
    elements.append(Spacer(1, 20))
    pendapatan_df = df[df['tipe_akun'] == 'Pendapatan']
    elements.append(Paragraph("<b>PENDAPATAN</b>", styles['Heading2']))
    data = [['Nama Akun','Saldo']]; total_pendapatan = 0
    for _, row in pendapatan_df.iterrows():
        data.append([row['nama_akun'], format_rupiah(row['saldo'])]); total_pendapatan += row['saldo']
    data.append([f'Total Pendapatan', format_rupiah(total_pendapatan)])
    table = Table(data, colWidths=[10*cm, 6*cm])
    table.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'LEFT'),('ALIGN',(-1,0),(-1,-1),'RIGHT'),
        ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('BACKGROUND',(0,-1),(-1,-1), colors.HexColor('#E8EAEC')),
        ('LINEABOVE',(0,-1),(-1,-1),1, colors.black)]))
    elements.append(table); elements.append(Spacer(1, 10))
    beban_df = df[df['tipe_akun'] == 'Beban']
    elements.append(Paragraph("<b>BEBAN</b>", styles['Heading2']))
    data = [['Nama Akun','Saldo']]; total_beban = 0
    for _, row in beban_df.iterrows():
        data.append([row['nama_akun'], format_rupiah(row['saldo'])]); total_beban += row['saldo']
    data.append([f'Total Beban', format_rupiah(total_beban)])
    table = Table(data, colWidths=[10*cm, 6*cm])
    table.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'LEFT'),('ALIGN',(-1,0),(-1,-1),'RIGHT'),
        ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('BACKGROUND',(0,-1),(-1,-1), colors.HexColor('#FFEBEE')),
        ('LINEABOVE',(0,-1),(-1,-1),1, colors.black)]))
    elements.append(table); elements.append(Spacer(1, 20))
    laba_rugi = total_pendapatan - total_beban
    laba_text = "LABA BERSIH" if laba_rugi >= 0 else "RUGI BERSIH"
    elements.append(Paragraph(f"<b>{laba_text}: {format_rupiah(abs(laba_rugi))}</b>", styles['Heading1']))
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

def generate_tax_report(tahun, bulan=None):
    conn = get_connection()
    date_filter = ""
    params = []
    if tahun and bulan:
        date_filter = "WHERE TO_CHAR(j.tanggal,'YYYY-MM') = %s"
        params.append(f"{tahun}-{bulan:02d}")
    elif tahun:
        date_filter = "WHERE TO_CHAR(j.tanggal,'YYYY') = %s"
        params.append(str(tahun))
    
    pendapatan_query = f"""
        SELECT COALESCE(SUM(jd.kredit), 0) as total
        FROM jurnal_detail jd JOIN jurnal j ON jd.jurnal_id = j.id
        JOIN akun a ON jd.akun_id = a.id
        {date_filter} AND a.tipe_akun = 'Pendapatan' AND j.is_posted = 1
    """
    beban_query = f"""
        SELECT a.nama_akun, COALESCE(SUM(jd.debit), 0) as total
        FROM jurnal_detail jd JOIN jurnal j ON jd.jurnal_id = j.id
        JOIN akun a ON jd.akun_id = a.id
        {date_filter} AND a.tipe_akun = 'Beban' AND j.is_posted = 1
        GROUP BY a.id, a.nama_akun
    """
    total_pendapatan = pd.read_sql_query(pendapatan_query, conn, params=params).iloc[0]['total'] or 0
    beban_df = pd.read_sql_query(beban_query, conn, params=params)
    total_beban = beban_df['total'].sum() if not beban_df.empty else 0
    conn.close()
    laba_rugi = total_pendapatan - total_beban
    return {
        'periode': f"{get_month_name(bulan)} {tahun}" if bulan else str(tahun),
        'total_pendapatan': total_pendapatan, 'total_beban': total_beban, 'laba_rugi': laba_rugi,
        'pph_21': max(0, laba_rugi * 0.05), 'pph_23': max(0, total_pendapatan * 0.02),
        'ppn': max(0, total_pendapatan * 0.11), 'beban_detail': beban_df
    }

def generate_tax_pdf(tahun, bulan=None):
    if not REPORTLAB_AVAILABLE: return None
    report = generate_tax_report(tahun, bulan)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("<b>LAPORAN PAJAK</b>", styles['Heading1']))
    elements.append(Paragraph(f"Periode: {report['periode']}", styles['Normal']))
    elements.append(Paragraph("<b>CERITA JIWA</b>", styles['Normal']))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<b>Ringkasan Perpajakan</b>", styles['Heading2']))
    data = [
        ['Total Pendapatan', format_rupiah(report['total_pendapatan'])],
        ['Total Beban', format_rupiah(report['total_beban'])],
        ['Laba/Rugi Bersih', format_rupiah(report['laba_rugi'])], ['', ''],
        ['Estimasi PPh 21 (5%)', format_rupiah(report['pph_21'])],
        ['Estimasi PPh 23 (2%)', format_rupiah(report['pph_23'])],
        ['Estimasi PPN (11%)', format_rupiah(report['ppn'])], ['', ''],
        ['TOTAL ESTIMASI PAJAK', format_rupiah(report['pph_21'] + report['pph_23'] + report['ppn'])],
    ]
    table = Table(data, colWidths=[10*cm, 6*cm])
    table.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'LEFT'),('ALIGN',(-1,0),(-1,-1),'RIGHT'),
        ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('BACKGROUND',(0,-1),(-1,-1), colors.HexColor('#E8EAEC')),
        ('LINEABOVE',(0,-1),(-1,-1),1, colors.black)]))
    elements.append(table); elements.append(Spacer(1, 20))
    if not report['beban_detail'].empty:
        elements.append(Paragraph("<b>Detail Beban</b>", styles['Heading2']))
        data = [['Nama Akun','Jumlah']]
        for _, row in report['beban_detail'].iterrows():
            data.append([row['nama_akun'], format_rupiah(row['total'])])
        table = Table(data, colWidths=[10*cm, 6*cm])
        table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0), colors.HexColor('#344A61')),
            ('TEXTCOLOR',(0,0),(-1,0), colors.whitesmoke),
            ('ALIGN',(0,0),(-1,-1),'LEFT'),('ALIGN',(-1,0),(-1,-1),'RIGHT'),
            ('GRID',(0,0),(-1,-1),0.5, colors.grey),
        ]))
        elements.append(table)
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("<i>Catatan: Perhitungan pajak ini merupakan estimasi. Konsultasikan dengan konsultan pajak untuk perhitungan yang akurat.</i>", styles['Italic']))
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf

# ============================================================
# STREAMLIT UI
# ============================================================

def set_page_config():
    st.set_page_config(page_title="Cerita Jiwa - Pembukuan", page_icon="📚", layout="wide", initial_sidebar_state="expanded")

def apply_custom_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    * { font-family: 'Avenir Next', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; }
    .main-header { font-size: 2.5rem; font-weight: 700; color: #344A61; margin-bottom: 0.5rem; }
    .sub-header { font-size: 1.2rem; color: #6D6F71; margin-bottom: 2rem; }
    .metric-card { background: linear-gradient(135deg, #E8EAEC 0%, #D9DBDC 100%); border-radius: 12px; padding: 20px; border-left: 4px solid #344A61; }
    .metric-value { font-size: 1.8rem; font-weight: 700; color: #344A61; }
    .metric-label { font-size: 0.9rem; color: #6D6F71; }
    .stButton>button { background-color: #344A61; color: white; border-radius: 8px; border: none; padding: 0.5rem 1.5rem; font-weight: 500; }
    .stButton>button:hover { background-color: #243447; }
    div[data-testid=\"stSidebar\"] { background-color: #f5f5f5; }
    .status-paid { color: #2E7D32; font-weight: 600; }
    .status-unpaid { color: #ED6C02; font-weight: 600; }
    .status-draft { color: #757575; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)

def render_sidebar():
    with st.sidebar:
        logo_path = os.path.join(os.path.dirname(__file__), "logo_ceritajiwa.png")
        if os.path.exists(logo_path):
            st.image(logo_path, width=180)
        else:
            st.markdown("<div style='text-align: center; padding: 20px 0;'><h2 style='color: #344A61; margin: 0;'>CERITA JIWA</h2></div>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #6D6F71; font-size: 0.85rem; margin-top: -10px;'>Sistem Pembukuan Internal</p>", unsafe_allow_html=True)
        st.markdown("---")
        menu = st.radio("Menu", ["🏠 Dashboard","📋 Daftar Akun","🤖 AI Jurnal Assistant","📝 Jurnal Umum","📖 Buku Besar","📄 Invoice","📊 Laporan Keuangan","💰 Laporan Pajak","🔒 Tutup Buku","⚙️ Pengaturan"], label_visibility="collapsed")
        st.markdown("---")
        st.markdown("<div style='text-align: center; padding: 10px; background: #E8EAEC; border-radius: 8px;'><p style='margin: 0; font-size: 0.8rem; color: #344A61;'><b>Cerita Jiwa</b><br>Training & Produk Digital</p></div>", unsafe_allow_html=True)
        return menu

# ============================================================
# PAGE: DASHBOARD
# ============================================================

def page_dashboard():
    st.markdown('<p class=\"main-header\">Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class=\"sub-header\">Ringkasan Keuangan Cerita Jiwa</p>', unsafe_allow_html=True)
    conn = get_connection()
    now = datetime.now(); current_year = now.year; current_month = now.month
    
    col1, col2, col3, col4 = st.columns(4)
    pendapatan = pd.read_sql_query("""
        SELECT COALESCE(SUM(jd.kredit), 0) as total FROM jurnal_detail jd
        JOIN jurnal j ON jd.jurnal_id = j.id JOIN akun a ON jd.akun_id = a.id
        WHERE a.tipe_akun = 'Pendapatan' AND j.is_posted = 1 AND TO_CHAR(j.tanggal,'YYYY-MM') = %s
    """, conn, params=[f"{current_year}-{current_month:02d}"]).iloc[0]['total'] or 0
    
    beban = pd.read_sql_query("""
        SELECT COALESCE(SUM(jd.debit), 0) as total FROM jurnal_detail jd
        JOIN jurnal j ON jd.jurnal_id = j.id JOIN akun a ON jd.akun_id = a.id
        WHERE a.tipe_akun = 'Beban' AND j.is_posted = 1 AND TO_CHAR(j.tanggal,'YYYY-MM') = %s
    """, conn, params=[f"{current_year}-{current_month:02d}"]).iloc[0]['total'] or 0
    
    unpaid_invoices = pd.read_sql_query("""
        SELECT COALESCE(SUM(total), 0) as total, COUNT(*) as count FROM invoice
        WHERE is_paid = 0 AND status != 'cancelled'
    """, conn)
    
    with col1: st.markdown(f'<div class=\"metric-card\"><div class=\"metric-label\">Pendapatan {get_month_name(current_month)}</div><div class=\"metric-value\">{format_rupiah(pendapatan)}</div></div>', unsafe_allow_html=True)
    with col2: st.markdown(f'<div class=\"metric-card\"><div class=\"metric-label\">Beban {get_month_name(current_month)}</div><div class=\"metric-value\">{format_rupiah(beban)}</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class=\"metric-card\"><div class=\"metric-label\">Laba/Rugi {get_month_name(current_month)}</div><div class=\"metric-value\">{format_rupiah(pendapatan - beban)}</div></div>', unsafe_allow_html=True)
    with col4: 
    total_unpaid = unpaid_invoices.iloc[0]['total'] or 0
    count_unpaid = unpaid_invoices.iloc[0]['count'] or 0
    st.markdown(f'<div class="metric-card"><div class="metric-label">Invoice Belum Dibayar</div><div class="metric-value">{format_rupiah(total_unpaid)}</div><div style="font-size: 0.8rem; color: #6D6F71;">{count_unpaid} invoice</div></div>', unsafe_allow_html=True)
    
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Tren Pendapatan 6 Bulan Terakhir")
        trend_data = []
        for i in range(5, -1, -1):
            d = now - timedelta(days=i*30)
            p = pd.read_sql_query("""
                SELECT COALESCE(SUM(jd.kredit), 0) as total FROM jurnal_detail jd
                JOIN jurnal j ON jd.jurnal_id = j.id JOIN akun a ON jd.akun_id = a.id
                WHERE a.tipe_akun = 'Pendapatan' AND j.is_posted = 1 AND TO_CHAR(j.tanggal,'YYYY-MM') = %s
            """, conn, params=[f"{d.year}-{d.month:02d}"]).iloc[0]['total'] or 0
            trend_data.append({'Bulan': f"{get_month_name(d.month)[:3]}", 'Pendapatan': p})
        trend_df = pd.DataFrame(trend_data)
        st.bar_chart(trend_df.set_index('Bulan'))
    with col2:
        st.subheader("Komposisi Beban")
        beban_data = pd.read_sql_query("""
            SELECT a.nama_akun, COALESCE(SUM(jd.debit), 0) as total FROM jurnal_detail jd
            JOIN jurnal j ON jd.jurnal_id = j.id JOIN akun a ON jd.akun_id = a.id
            WHERE a.tipe_akun = 'Beban' AND j.is_posted = 1 AND TO_CHAR(j.tanggal,'YYYY-MM') = %s
            GROUP BY a.id, a.nama_akun HAVING SUM(jd.debit) > 0
        """, conn, params=[f"{current_year}-{current_month:02d}"])
        if not beban_data.empty: st.bar_chart(beban_data.set_index('nama_akun'))
        else: st.info("Belum ada data beban bulan ini")
    
    st.markdown("---"); st.subheader("Aktivitas Terbaru")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Jurnal Terbaru**")
        recent_journals = pd.read_sql_query("SELECT tanggal, keterangan, total_debit FROM jurnal ORDER BY created_at DESC LIMIT 5", conn)
        if not recent_journals.empty: st.dataframe(recent_journals, use_container_width=True, hide_index=True)
        else: st.info("Belum ada jurnal")
    with col2:
        st.markdown("**Invoice Terbaru**")
        recent_invoices = pd.read_sql_query("SELECT no_invoice, customer_name, total, status FROM invoice ORDER BY created_at DESC LIMIT 5", conn)
        if not recent_invoices.empty: st.dataframe(recent_invoices, use_container_width=True, hide_index=True)
        else: st.info("Belum ada invoice")
    conn.close()

# ============================================================
# PAGE: CHART OF ACCOUNTS
# ============================================================

def page_chart_of_accounts():
    st.markdown('<p class=\"main-header\">Daftar Akun (Chart of Accounts)</p>', unsafe_allow_html=True)
    st.markdown('<p class=\"sub-header\">Kelola akun-akun pembukuan</p>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["📋 Lihat Daftar Akun", "➕ Tambah Akun Baru"])
    with tab1:
        df = get_all_accounts()
        if not df.empty:
            st.dataframe(df[['kode_akun','nama_akun','tipe_akun','saldo_normal','parent_name']], use_container_width=True, hide_index=True,
                column_config={'kode_akun':'Kode Akun','nama_akun':'Nama Akun','tipe_akun':'Tipe','saldo_normal':'Saldo Normal','parent_name':'Induk'})
            st.markdown("---"); st.subheader("Edit / Hapus Akun")
            col1, col2 = st.columns(2)
            with col1:
                selected = st.selectbox("Pilih Akun", df['nama_akun'].tolist())
                selected_row = df[df['nama_akun'] == selected].iloc[0]
            with col2:
                action = st.radio("Aksi", ["Edit","Hapus"], horizontal=True)
            if action == "Edit":
                with st.form("edit_akun"):
                    new_kode = st.text_input("Kode Akun", value=selected_row['kode_akun'])
                    new_nama = st.text_input("Nama Akun", value=selected_row['nama_akun'])
                    new_tipe = st.selectbox("Tipe Akun", ['Aset','Kewajiban','Ekuitas','Pendapatan','Beban'], index=['Aset','Kewajiban','Ekuitas','Pendapatan','Beban'].index(selected_row['tipe_akun']))
                    new_saldo = st.selectbox("Saldo Normal", ['debit','kredit'], index=['debit','kredit'].index(selected_row['saldo_normal']))
                    if st.form_submit_button("Simpan Perubahan"):
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("UPDATE akun SET kode_akun=%s, nama_akun=%s, tipe_akun=%s, saldo_normal=%s WHERE id=%s",
                                     (new_kode, new_nama, new_tipe, new_saldo, selected_row['id']))
                        conn.commit(); conn.close(); log_activity("EDIT_AKUN", f"Edit akun: {new_nama}")
                        st.success("Akun berhasil diupdate!"); st.rerun()
            else:
                if st.button("Hapus Akun", type="primary"):
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) as cnt FROM jurnal_detail WHERE akun_id = %s", (selected_row['id'],))
                    count = cursor.fetchone()['cnt']
                    if count > 0: st.error(f"Akun ini sudah digunakan dalam {count} jurnal. Tidak dapat dihapus.")
                    else:
                        cursor.execute("UPDATE akun SET is_active=0 WHERE id=%s", (selected_row['id'],))
                        conn.commit(); st.success("Akun berhasil dihapus!"); st.rerun()
                    conn.close()
        else: st.info("Belum ada akun")
    with tab2:
        with st.form("tambah_akun"):
            st.subheader("Tambah Akun Baru")
            kode = st.text_input("Kode Akun*", placeholder="Contoh: 1-1105")
            nama = st.text_input("Nama Akun*", placeholder="Contoh: Kas Besar")
            tipe = st.selectbox("Tipe Akun*", ['Aset','Kewajiban','Ekuitas','Pendapatan','Beban'])
            saldo = st.selectbox("Saldo Normal*", ['debit','kredit'])
            conn = get_connection()
            parents = pd.read_sql_query("SELECT id, kode_akun, nama_akun FROM akun WHERE parent_id IS NULL AND is_active=1", conn)
            conn.close()
            parent_options = ["Tanpa Induk"] + [f"{row['kode_akun']} - {row['nama_akun']}" for _, row in parents.iterrows()]
            parent_selected = st.selectbox("Induk (Parent)", parent_options)
            if st.form_submit_button("Tambah Akun"):
                if not kode or not nama: st.error("Kode akun dan nama akun wajib diisi!")
                else:
                    parent_id = None
                    if parent_selected != "Tanpa Induk":
                        parent_code = parent_selected.split(" - ")[0]
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("SELECT id FROM akun WHERE kode_akun = %s", (parent_code,))
                        result = cursor.fetchone()
                        if result: parent_id = result['id']
                        conn.close()
                    conn = get_connection(); cursor = conn.cursor()
                    try:
                        cursor.execute("INSERT INTO akun (kode_akun, nama_akun, tipe_akun, saldo_normal, parent_id) VALUES (%s,%s,%s,%s,%s)",
                                     (kode, nama, tipe, saldo, parent_id))
                        conn.commit(); log_activity("TAMBAH_AKUN", f"Tambah akun: {nama}")
                        st.success(f"Akun '{nama}' berhasil ditambahkan!"); st.rerun()
                    except psycopg2.IntegrityError: st.error("Kode akun sudah ada!")
                    finally: conn.close()

# ============================================================
# PAGE: AI JOURNAL ASSISTANT
# ============================================================

def page_ai_journal():
    st.markdown('<p class=\"main-header\">AI Jurnal Assistant</p>', unsafe_allow_html=True)
    st.markdown('<p class=\"sub-header\">Deskripsikan transaksi, AI akan menentukan jurnalnya</p>', unsafe_allow_html=True)
    st.info("Contoh: Beli motor 31.500.000 bayar cicil 5 tahun, DP 10.000.000 bunga 7% per bulan | Terima pembayaran training 5.000.000 via BCA | Bayar gaji karyawan 15.000.000")
    if 'ai_result' not in st.session_state: st.session_state.ai_result = None
    if 'ai_questions' not in st.session_state: st.session_state.ai_questions = []
    if 'ai_jurnal_entries' not in st.session_state: st.session_state.ai_jurnal_entries = []
    
    with st.form("ai_journal_form"):
        deskripsi = st.text_area("Deskripsi Transaksi*", placeholder="Contoh: Beli motor 31.500.000 bayar cicil 5 tahun, DP 10.000.000 bunga 7% per bulan", height=100)
        col1, col2 = st.columns(2)
        with col1: nilai_manual = st.text_input("Nilai Rupiah (opsional)", placeholder="31500000")
        with col2: tanggal = st.date_input("Tanggal Transaksi", value=date.today())
        submitted = st.form_submit_button("Analisis dengan AI", use_container_width=True)
        if submitted:
            if not deskripsi: st.error("Deskripsi transaksi wajib diisi!")
            else:
                nilai = parse_rupiah(nilai_manual) if nilai_manual else None
                result = ai_journal_assistant(deskripsi, nilai)
                st.session_state.ai_result = result; st.session_state.ai_questions = result['questions']
                st.session_state.ai_jurnal_entries = result['jurnal']; st.session_state.ai_tanggal = tanggal
                st.session_state.ai_deskripsi = deskripsi
    
    if st.session_state.ai_questions:
        st.warning("AI membutuhkan informasi tambahan:")
        for q in st.session_state.ai_questions: st.markdown(f"- {q}")
        with st.form("answer_questions"):
            jawaban = st.text_input("Jawaban Anda")
            if st.form_submit_button("Kirim Jawaban"):
                combined = st.session_state.ai_deskripsi + " " + jawaban
                result = ai_journal_assistant(combined, parse_rupiah(jawaban))
                st.session_state.ai_result = result; st.session_state.ai_questions = result['questions']
                st.session_state.ai_jurnal_entries = result['jurnal']; st.rerun()
    
    if st.session_state.ai_jurnal_entries and not st.session_state.ai_questions:
        st.success("AI berhasil menentukan jurnal!")
        st.markdown("### Jurnal yang Disarankan")
        accounts_df = get_all_accounts(); total_debit = 0; total_kredit = 0
        for i, entry in enumerate(st.session_state.ai_jurnal_entries):
            col1, col2, col3 = st.columns([3, 2, 2])
            akun_match = accounts_df[accounts_df['nama_akun'].str.lower() == entry['akun'].lower()]
            if akun_match.empty: akun_match = accounts_df[accounts_df['nama_akun'].str.contains(entry['akun'], case=False, na=False)]
            with col1:
                if not akun_match.empty:
                    akun_options = [f"{row['kode_akun']} - {row['nama_akun']}" for _, row in akun_match.iterrows()]
                    selected = st.selectbox(f"Akun #{i+1}", akun_options, key=f"ai_akun_{i}")
                else:
                    all_options = [f"{row['kode_akun']} - {row['nama_akun']}" for _, row in accounts_df.iterrows()]
                    selected = st.selectbox(f"Akun #{i+1}", all_options, key=f"ai_akun_{i}")
            with col2:
                st.text_input("Debit", value=format_rupiah(entry['debit']) if entry['debit'] > 0 else "", key=f"ai_debit_{i}", disabled=True)
                total_debit += entry['debit']
            with col3:
                st.text_input("Kredit", value=format_rupiah(entry['kredit']) if entry['kredit'] > 0 else "", key=f"ai_kredit_{i}", disabled=True)
                total_kredit += entry['kredit']
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Total Debit", format_rupiah(total_debit))
        with col2: st.metric("Total Kredit", format_rupiah(total_kredit))
        with col3:
            balance = total_debit - total_kredit
            st.metric("Balance", format_rupiah(balance), delta="Balance" if balance == 0 else "Tidak Balance!")
        if abs(total_debit - total_kredit) < 0.01:
            if st.button("Simpan Jurnal", type="primary", use_container_width=True):
                conn = get_connection(); cursor = conn.cursor()
                no_bukti = get_next_journal_number()
                periode = f"{st.session_state.ai_tanggal.year}-{st.session_state.ai_tanggal.month:02d}"
                cursor.execute("INSERT INTO jurnal (tanggal, no_bukti, keterangan, total_debit, total_kredit, periode) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                             (st.session_state.ai_tanggal, no_bukti, st.session_state.ai_deskripsi, total_debit, total_kredit, periode))
                jurnal_id = cursor.fetchone()['id']
                for i, entry in enumerate(st.session_state.ai_jurnal_entries):
                    akun_selected = st.session_state[f"ai_akun_{i}"]
                    akun_kode = akun_selected.split(" - ")[0]
                    cursor.execute("SELECT id FROM akun WHERE kode_akun = %s", (akun_kode,))
                    akun_id = cursor.fetchone()['id']
                    cursor.execute("INSERT INTO jurnal_detail (jurnal_id, akun_id, debit, kredit) VALUES (%s,%s,%s,%s)",
                                 (jurnal_id, akun_id, entry['debit'], entry['kredit']))
                conn.commit(); conn.close()
                log_activity("JURNAL_AI", f"Jurnal otomatis: {st.session_state.ai_deskripsi[:50]}")
                st.success(f"Jurnal berhasil disimpan dengan nomor: {no_bukti}")
                st.session_state.ai_result = None; st.session_state.ai_questions = []; st.session_state.ai_jurnal_entries = []
                st.rerun()
        else: st.error("Jurnal tidak balance! Total debit dan kredit harus sama.")

# ============================================================
# PAGE: JURNAL UMUM
# ============================================================

def page_jurnal_umum():
    st.markdown('<p class=\"main-header\">Jurnal Umum</p>', unsafe_allow_html=True)
    st.markdown('<p class=\"sub-header\">Input dan kelola jurnal transaksi</p>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Input Jurnal Baru", "Daftar Jurnal"])
    with tab1:
        with st.form("input_jurnal"):
            st.subheader("Input Jurnal Manual")
            tanggal = st.date_input("Tanggal", value=date.today())
            keterangan = st.text_area("Keterangan*", placeholder="Keterangan transaksi")
            st.markdown("**Detail Jurnal**")
            accounts_df = get_all_accounts()
            account_options = [f"{row['kode_akun']} - {row['nama_akun']}" for _, row in accounts_df.iterrows()]
            entries = []
            for i in range(4):
                cols = st.columns([3, 2, 2])
                with cols[0]: akun = st.selectbox(f"Akun #{i+1}", [""] + account_options, key=f"jurnal_akun_{i}")
                with cols[1]: debit = st.number_input(f"Debit #{i+1}", min_value=0.0, value=0.0, step=1000.0, key=f"jurnal_debit_{i}")
                with cols[2]: kredit = st.number_input(f"Kredit #{i+1}", min_value=0.0, value=0.0, step=1000.0, key=f"jurnal_kredit_{i}")
                if akun: entries.append({'akun': akun, 'debit': debit, 'kredit': kredit})
            if st.form_submit_button("Simpan Jurnal", use_container_width=True):
                if not keterangan: st.error("Keterangan wajib diisi!")
                elif len(entries) < 2: st.error("Minimal 2 akun!")
                else:
                    total_debit = sum(e['debit'] for e in entries); total_kredit = sum(e['kredit'] for e in entries)
                    if abs(total_debit - total_kredit) > 0.01: st.error(f"Jurnal tidak balance! Debit: {total_debit}, Kredit: {total_kredit}")
                    else:
                        conn = get_connection(); cursor = conn.cursor()
                        no_bukti = get_next_journal_number(); periode = f"{tanggal.year}-{tanggal.month:02d}"
                        cursor.execute("INSERT INTO jurnal (tanggal, no_bukti, keterangan, total_debit, total_kredit, periode) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                                     (tanggal, no_bukti, keterangan, total_debit, total_kredit, periode))
                        jurnal_id = cursor.fetchone()['id']
                        for entry in entries:
                            akun_kode = entry['akun'].split(" - ")[0]
                            cursor.execute("SELECT id FROM akun WHERE kode_akun = %s", (akun_kode,))
                            akun_id = cursor.fetchone()['id']
                            cursor.execute("INSERT INTO jurnal_detail (jurnal_id, akun_id, debit, kredit) VALUES (%s,%s,%s,%s)",
                                         (jurnal_id, akun_id, entry['debit'], entry['kredit']))
                        conn.commit(); conn.close()
                        log_activity("JURNAL_MANUAL", f"Jurnal manual: {keterangan[:50]}")
                        st.success(f"Jurnal berhasil disimpan: {no_bukti}"); st.rerun()
    with tab2:
        col1, col2 = st.columns(2)
        with col1: filter_tahun = st.selectbox("Tahun", ["Semua"] + list(range(datetime.now().year, datetime.now().year-5, -1)))
        with col2: filter_bulan = st.selectbox("Bulan", ["Semua"] + [f"{i:02d} - {get_month_name(i)}" for i in range(1,13)])
        tahun = None if filter_tahun == "Semua" else int(filter_tahun)
        bulan = None if filter_bulan == "Semua" else int(filter_bulan.split(" - ")[0])
        df = get_jurnal_list(100, tahun, bulan)
        if not df.empty:
            st.dataframe(df[['tanggal','no_bukti','keterangan','total_debit','total_kredit']], use_container_width=True, hide_index=True,
                column_config={'tanggal':'Tanggal','no_bukti':'No. Bukti','keterangan':'Keterangan',
                    'total_debit': st.column_config.NumberColumn('Total Debit', format="Rp %.0f"),
                    'total_kredit': st.column_config.NumberColumn('Total Kredit', format="Rp %.0f")})
            st.markdown("---"); st.subheader("Detail Jurnal")
            selected_bukti = st.selectbox("Pilih No. Bukti", df['no_bukti'].tolist())
            selected_id = df[df['no_bukti'] == selected_bukti].iloc[0]['id']
            detail = get_jurnal_detail(selected_id)
            if not detail.empty:
                st.dataframe(detail[['kode_akun','nama_akun','debit','kredit']], use_container_width=True, hide_index=True,
                    column_config={'kode_akun':'Kode','nama_akun':'Nama Akun',
                        'debit': st.column_config.NumberColumn('Debit', format="Rp %.0f"),
                        'kredit': st.column_config.NumberColumn('Kredit', format="Rp %.0f")})
        else: st.info("Belum ada jurnal")

# ============================================================
# PAGE: BUKU BESAR
# ============================================================

def page_buku_besar():
    st.markdown('<p class=\"main-header\">Buku Besar</p>', unsafe_allow_html=True)
    st.markdown('<p class=\"sub-header\">Lihat buku kecil per akun</p>', unsafe_allow_html=True)
    accounts_df = get_all_accounts()
    col1, col2, col3 = st.columns(3)
    with col1:
        akun_options = [f"{row['kode_akun']} - {row['nama_akun']}" for _, row in accounts_df.iterrows()]
        selected = st.selectbox("Pilih Akun", akun_options)
    with col2: filter_tahun = st.selectbox("Tahun", list(range(datetime.now().year, datetime.now().year-5, -1)))
    with col3: filter_bulan = st.selectbox("Bulan", ["Semua"] + [f"{i:02d} - {get_month_name(i)}" for i in range(1,13)])
    akun_kode = selected.split(" - ")[0]
    akun_id = accounts_df[accounts_df['kode_akun'] == akun_kode].iloc[0]['id']
    tahun = int(filter_tahun)
    bulan = None if filter_bulan == "Semua" else int(filter_bulan.split(" - ")[0])
    df, akun_info = get_buku_besar(akun_id, tahun, bulan)
    if not akun_info.empty:
        info = akun_info.iloc[0]
        st.info(f"**{info['kode_akun']} - {info['nama_akun']}** | Tipe: {info['tipe_akun']} | Saldo Normal: {info['saldo_normal'].upper()}")
    if not df.empty:
        st.dataframe(df[['tanggal','no_bukti','keterangan','debit','kredit','saldo']], use_container_width=True, hide_index=True,
            column_config={'tanggal':'Tanggal','no_bukti':'No. Bukti','keterangan':'Keterangan',
                'debit': st.column_config.NumberColumn('Debit', format="Rp %.0f"),
                'kredit': st.column_config.NumberColumn('Kredit', format="Rp %.0f"),
                'saldo': st.column_config.NumberColumn('Saldo', format="Rp %.0f")})
        csv = df.to_csv(index=False)
        st.download_button(label="Download CSV", data=csv, file_name=f"buku_besar_{info['kode_akun']}_{tahun}{f'{bulan:02d}' if bulan else ''}.csv", mime="text/csv")
    else: st.info("Tidak ada transaksi untuk akun ini pada periode yang dipilih")

# ============================================================
# PAGE: INVOICE
# ============================================================

def page_invoice():
    st.markdown('<p class=\"main-header\">Invoice</p>', unsafe_allow_html=True)
    st.markdown('<p class=\"sub-header\">Buat dan kelola invoice</p>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["Buat Invoice Baru", "Daftar Invoice"])
    with tab1:
        with st.form("buat_invoice"):
            st.subheader("Buat Invoice Baru")
            col1, col2 = st.columns(2)
            with col1:
                no_invoice = st.text_input("No. Invoice", value=get_next_invoice_number())
                tanggal = st.date_input("Tanggal Invoice", value=date.today())
                due_date = st.date_input("Jatuh Tempo", value=date.today() + timedelta(days=14))
            with col2:
                customer_name = st.text_input("Nama Customer*", placeholder="Nama perusahaan/pelanggan")
                customer_email = st.text_input("Email", placeholder="email@contoh.com")
                customer_phone = st.text_input("Telepon", placeholder="0812xxxxxxx")
            customer_address = st.text_area("Alamat", placeholder="Alamat lengkap customer")
            st.markdown("---"); st.subheader("Item Invoice")
            items = []
            for i in range(5):
                cols = st.columns([4, 1, 1, 2, 2])
                with cols[0]: deskripsi = st.text_input(f"Deskripsi #{i+1}", placeholder="Nama produk/layanan", key=f"inv_desc_{i}")
                with cols[1]: qty = st.number_input(f"Qty #{i+1}", min_value=0.0, value=0.0, step=1.0, key=f"inv_qty_{i}")
                with cols[2]: satuan = st.text_input(f"Satuan #{i+1}", value="pcs", key=f"inv_unit_{i}")
                with cols[3]: harga = st.number_input(f"Harga #{i+1}", min_value=0.0, value=0.0, step=1000.0, key=f"inv_price_{i}")
                with cols[4]: total = qty * harga; st.text_input(f"Total #{i+1}", value=format_rupiah(total), key=f"inv_total_{i}", disabled=True)
                if deskripsi and qty > 0 and harga > 0: items.append({'deskripsi':deskripsi,'qty':qty,'satuan':satuan,'harga':harga,'total':total})
            ppn_check = st.checkbox("Termasuk PPN 11%", value=True)
            notes = st.text_area("Catatan Tambahan", placeholder="Catatan untuk customer")
            if st.form_submit_button("Simpan Invoice", use_container_width=True):
                if not customer_name: st.error("Nama customer wajib diisi!")
                elif len(items) == 0: st.error("Minimal 1 item!")
                else:
                    subtotal = sum(item['total'] for item in items)
                    ppn = subtotal * 0.11 if ppn_check else 0; total = subtotal + ppn
                    data = {'no_invoice':no_invoice,'tanggal':tanggal,'due_date':due_date,'customer_name':customer_name,
                            'customer_email':customer_email,'customer_phone':customer_phone,'customer_address':customer_address,
                            'subtotal':subtotal,'ppn':ppn,'total':total,'status':'draft','notes':notes}
                    invoice_id = create_invoice(data, items)
                    log_activity("INVOICE", f"Buat invoice: {no_invoice}")
                    st.success(f"Invoice {no_invoice} berhasil dibuat!"); st.rerun()
    with tab2:
        status_filter = st.selectbox("Filter Status", ["Semua","draft","sent","paid","cancelled"])
        status = None if status_filter == "Semua" else status_filter
        df = get_invoices(status)
        if not df.empty:
            for _, row in df.iterrows():
                with st.container():
                    col1, col2, col3, col4 = st.columns([3, 3, 2, 2])
                    with col1: st.markdown(f"**{row['no_invoice']}**<br>{row['customer_name']}", unsafe_allow_html=True)
                    with col2: st.markdown(f"Tanggal: {row['tanggal']}<br>Jatuh Tempo: {row['due_date'] or '-'}", unsafe_allow_html=True)
                    with col3:
                        st.markdown(f"**{format_rupiah(row['total'])}**")
                        status_class = "status-paid" if row['status']=='paid' else "status-unpaid" if row['status']=='sent' else "status-draft"
                        st.markdown(f"<span class='{status_class}'>{row['status'].upper()}</span>", unsafe_allow_html=True)
                    with col4:
                        if row['status'] != 'paid':
                            if st.button("Bayar", key=f"pay_{row['id']}"):
                                update_invoice_status(row['id'], 'paid', date.today(), 'Transfer')
                                conn = get_connection(); cursor = conn.cursor()
                                no_bukti = get_next_journal_number(); periode = f"{date.today().year}-{date.today().month:02d}"
                                cursor.execute("INSERT INTO jurnal (tanggal, no_bukti, keterangan, total_debit, total_kredit, periode) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                                             (date.today(), no_bukti, f"Pembayaran invoice {row['no_invoice']} - {row['customer_name']}", row['total'], row['total'], periode))
                                jurnal_id = cursor.fetchone()['id']
                                cursor.execute("SELECT id FROM akun WHERE kode_akun = '1-1201'")
                                bank_id = cursor.fetchone()['id']
                                cursor.execute("INSERT INTO jurnal_detail (jurnal_id, akun_id, debit, kredit) VALUES (%s,%s,%s,%s)", (jurnal_id, bank_id, row['total'], 0))
                                cursor.execute("SELECT id FROM akun WHERE kode_akun = '4-1100'")
                                pendapatan_id = cursor.fetchone()['id']
                                cursor.execute("INSERT INTO jurnal_detail (jurnal_id, akun_id, debit, kredit) VALUES (%s,%s,%s,%s)", (jurnal_id, pendapatan_id, 0, row['total']))
                                conn.commit(); conn.close()
                                st.success("Invoice dibayar dan jurnal otomatis dibuat!"); st.rerun()
                        if st.button("Download PDF", key=f"pdf_{row['id']}"):
                            pdf = generate_invoice_pdf(row['id'])
                            if pdf: st.download_button("Klik untuk Download", data=pdf, file_name=f"Invoice_{row['no_invoice']}.pdf", mime="application/pdf", key=f"dl_{row['id']}")
                            else: st.error("Gagal generate PDF. Pastikan reportlab terinstall.")
                    st.markdown("---")
        else: st.info("Belum ada invoice")

# ============================================================
# PAGE: LAPORAN KEUANGAN
# ============================================================

def page_laporan_keuangan():
    st.markdown('<p class=\"main-header\">Laporan Keuangan</p>', unsafe_allow_html=True)
    st.markdown('<p class=\"sub-header\">Neraca dan Laba Rugi</p>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1: tahun = st.selectbox("Tahun", list(range(datetime.now().year, datetime.now().year-5, -1)))
    with col2: bulan = st.selectbox("Bulan", [None] + list(range(1,13)), format_func=lambda x: "Semua Bulan" if x is None else get_month_name(x))
    tab1, tab2 = st.tabs(["Neraca", "Laba Rugi"])
    with tab1:
        st.subheader("Neraca (Balance Sheet)")
        df = get_neraca(tahun, bulan)
        for tipe in ['Aset','Kewajiban','Ekuitas']:
            tipe_df = df[df['tipe_akun'] == tipe]
            if not tipe_df.empty:
                st.markdown(f"**{tipe.upper()}**")
                total = tipe_df['saldo'].sum()
                display_df = tipe_df[['kode_akun','nama_akun','saldo']].copy()
                display_df['saldo'] = display_df['saldo'].apply(format_rupiah)
                st.dataframe(display_df, use_container_width=True, hide_index=True, column_config={'kode_akun':'Kode','nama_akun':'Nama Akun','saldo':'Saldo'})
                st.markdown(f"**Total {tipe}: {format_rupiah(total)}**"); st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Download Neraca PDF"):
                pdf = generate_neraca_pdf(tahun, bulan)
                if pdf: st.download_button("Download PDF", data=pdf, file_name=f"Neraca_{tahun}{f'_{bulan:02d}' if bulan else ''}.pdf", mime="application/pdf")
                else: st.error("Gagal generate PDF")
        with col2:
            csv = df.to_csv(index=False)
            st.download_button("Download CSV", data=csv, file_name=f"Neraca_{tahun}{f'_{bulan:02d}' if bulan else ''}.csv", mime="text/csv")
    with tab2:
        st.subheader("Laba Rugi (Income Statement)")
        df = get_laba_rugi(tahun, bulan)
        pendapatan_df = df[df['tipe_akun'] == 'Pendapatan']
        st.markdown("**PENDAPATAN**"); total_pendapatan = 0
        if not pendapatan_df.empty:
            display_df = pendapatan_df[['nama_akun','saldo']].copy(); total_pendapatan = pendapatan_df['saldo'].sum()
            display_df['saldo'] = display_df['saldo'].apply(format_rupiah)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.markdown(f"**Total Pendapatan: {format_rupiah(total_pendapatan)}**"); st.markdown("---")
        beban_df = df[df['tipe_akun'] == 'Beban']
        st.markdown("**BEBAN**"); total_beban = 0
        if not beban_df.empty:
            display_df = beban_df[['nama_akun','saldo']].copy(); total_beban = beban_df['saldo'].sum()
            display_df['saldo'] = display_df['saldo'].apply(format_rupiah)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        st.markdown(f"**Total Beban: {format_rupiah(total_beban)}**"); st.markdown("---")
        laba_rugi = total_pendapatan - total_beban
        laba_text = "LABA BERSIH" if laba_rugi >= 0 else "RUGI BERSIH"
        st.markdown(f"<h3 style='color: #344A61;'>{laba_text}: {format_rupiah(abs(laba_rugi))}</h3>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Download Laba Rugi PDF"):
                pdf = generate_laba_rugi_pdf(tahun, bulan)
                if pdf: st.download_button("Download PDF", data=pdf, file_name=f"LabaRugi_{tahun}{f'_{bulan:02d}' if bulan else ''}.pdf", mime="application/pdf")
                else: st.error("Gagal generate PDF")
        with col2:
            csv = df.to_csv(index=False)
            st.download_button("Download CSV", data=csv, file_name=f"LabaRugi_{tahun}{f'_{bulan:02d}' if bulan else ''}.csv", mime="text/csv")

# ============================================================
# PAGE: LAPORAN PAJAK
# ============================================================

def page_laporan_pajak():
    st.markdown('<p class=\"main-header\">Laporan Pajak</p>', unsafe_allow_html=True)
    st.markdown('<p class=\"sub-header\">Ringkasan perpajakan untuk pelaporan</p>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1: tahun = st.selectbox("Tahun", list(range(datetime.now().year, datetime.now().year-5, -1)))
    with col2: bulan = st.selectbox("Bulan", [None] + list(range(1,13)), format_func=lambda x: "Semua Bulan" if x is None else get_month_name(x))
    report = generate_tax_report(tahun, bulan)
    st.markdown("---"); st.subheader(f"Ringkasan Pajak - {report['periode']}")
    col1, col2, col3 = st.columns(3)
    with col1: st.markdown(f'<div class=\"metric-card\"><div class=\"metric-label\">Total Pendapatan</div><div class=\"metric-value\">{format_rupiah(report["total_pendapatan"])}</div></div>', unsafe_allow_html=True)
    with col2: st.markdown(f'<div class=\"metric-card\"><div class=\"metric-label\">Total Beban</div><div class=\"metric-value\">{format_rupiah(report["total_beban"])}</div></div>', unsafe_allow_html=True)
    with col3: st.markdown(f'<div class=\"metric-card\"><div class=\"metric-label\">Laba/Rugi</div><div class=\"metric-value\">{format_rupiah(report["laba_rugi"])}</div></div>', unsafe_allow_html=True)
    st.markdown("---"); st.subheader("Estimasi Pajak Terutang")
    tax_data = [
        ['PPh 21 (estimasi 5%)', format_rupiah(report['pph_21'])],
        ['PPh 23 (estimasi 2%)', format_rupiah(report['pph_23'])],
        ['PPN (estimasi 11%)', format_rupiah(report['ppn'])], ['', ''],
        ['TOTAL ESTIMASI PAJAK', format_rupiah(report['pph_21'] + report['pph_23'] + report['ppn'])],
    ]
    tax_df = pd.DataFrame(tax_data, columns=['Jenis Pajak','Jumlah'])
    st.dataframe(tax_df, use_container_width=True, hide_index=True)
    st.info("Catatan: Perhitungan pajak ini merupakan estimasi. Konsultasikan dengan konsultan pajak untuk perhitungan yang akurat.")
    if not report['beban_detail'].empty:
        st.markdown("---"); st.subheader("Detail Beban")
        display_df = report['beban_detail'].copy(); display_df['total'] = display_df['total'].apply(format_rupiah)
        st.dataframe(display_df, use_container_width=True, hide_index=True, column_config={'nama_akun':'Nama Akun','total':'Jumlah'})
    if st.button("Download Laporan Pajak PDF"):
        pdf = generate_tax_pdf(tahun, bulan)
        if pdf: st.download_button("Download PDF", data=pdf, file_name=f"LaporanPajak_{tahun}{f'_{bulan:02d}' if bulan else ''}.pdf", mime="application/pdf")
        else: st.error("Gagal generate PDF")
    csv_data = f\"\"\"Laporan Pajak Cerita Jiwa\nPeriode: {report['periode']}\n\nTotal Pendapatan,{report['total_pendapatan']}\nTotal Beban,{report['total_beban']}\nLaba/Rugi,{report['laba_rugi']}\n\nPPh 21 (5%),{report['pph_21']}\nPPh 23 (2%),{report['pph_23']}\nPPN (11%),{report['ppn']}\nTotal Pajak,{report['pph_21'] + report['pph_23'] + report['ppn']}\"\"\"
    st.download_button(\"Download CSV\", data=csv_data, file_name=f\"LaporanPajak_{tahun}{f'_{bulan:02d}' if bulan else ''}.csv\", mime=\"text/csv\")

# ============================================================
# PAGE: TUTUP BUKU
# ============================================================

def page_tutup_buku():
    st.markdown('<p class=\"main-header\">Tutup Buku</p>', unsafe_allow_html=True)
    st.markdown('<p class=\"sub-header\">Tutup periode akuntansi bulanan dan tahunan</p>', unsafe_allow_html=True)
    conn = get_connection(); cursor = conn.cursor()
    tab1, tab2, tab3 = st.tabs([\"Tutup Buku Bulanan\", \"Tutup Buku Tahunan\", \"Status Periode\"])
    with tab1:
        st.subheader(\"Tutup Buku Per Bulan\"); st.warning(\"Perhatian: Setelah tutup buku, jurnal untuk periode tersebut tidak dapat diubah!\")
        col1, col2 = st.columns(2)
        with col1: tutup_tahun = st.selectbox(\"Tahun\", list(range(datetime.now().year, datetime.now().year-5, -1)), key=\"tb_tahun\")
        with col2: tutup_bulan = st.selectbox(\"Bulan\", list(range(1,13)), format_func=get_month_name, key=\"tb_bulan\")
        cursor.execute(\"SELECT is_closed FROM periode_akuntansi WHERE tahun = %s AND bulan = %s\", (tutup_tahun, tutup_bulan))
        result = cursor.fetchone()
        if result and result['is_closed'] == 1: st.error(f\"Periode {get_month_name(tutup_bulan)} {tutup_tahun} sudah ditutup!\")
        else:
            pendapatan = pd.read_sql_query(\"\"\"\n                SELECT COALESCE(SUM(jd.kredit), 0) as total FROM jurnal_detail jd\n                JOIN jurnal j ON jd.jurnal_id = j.id JOIN akun a ON jd.akun_id = a.id\n                WHERE a.tipe_akun = 'Pendapatan' AND j.is_posted = 1 AND TO_CHAR(j.tanggal,'YYYY-MM') = %s\n            \"\"\", conn, params=[f\"{tutup_tahun}-{tutup_bulan:02d}\"]).iloc[0]['total'] or 0\n            beban = pd.read_sql_query(\"\"\"\n                SELECT COALESCE(SUM(jd.debit), 0) as total FROM jurnal_detail jd\n                JOIN jurnal j ON jd.jurnal_id = j.id JOIN akun a ON jd.akun_id = a.id\n                WHERE a.tipe_akun = 'Beban' AND j.is_posted = 1 AND TO_CHAR(j.tanggal,'YYYY-MM') = %s\n            \"\"\", conn, params=[f\"{tutup_tahun}-{tutup_bulan:02d}\"]).iloc[0]['total'] or 0\n            col1, col2, col3 = st.columns(3)\n            with col1: st.metric(\"Pendapatan\", format_rupiah(pendapatan))\n            with col2: st.metric(\"Beban\", format_rupiah(beban))\n            with col3: st.metric(\"Laba/Rugi\", format_rupiah(pendapatan - beban))\n            if st.button(\"Tutup Buku Bulan Ini\", type=\"primary\"):\n                cursor.execute(\"\"\"\n                    INSERT INTO periode_akuntansi (tahun, bulan, is_closed, closed_at, closed_by)\n                    VALUES (%s, %s, 1, CURRENT_TIMESTAMP, %s)\n                    ON CONFLICT (tahun, bulan) DO UPDATE SET\n                    is_closed = 1, closed_at = CURRENT_TIMESTAMP, closed_by = EXCLUDED.closed_by\n                \"\"\", (tutup_tahun, tutup_bulan, st.session_state.get('username','admin')))\n                conn.commit(); log_activity(\"TUTUP_BUKU\", f\"Tutup buku {get_month_name(tutup_bulan)} {tutup_tahun}\")\n                st.success(f\"Buku periode {get_month_name(tutup_bulan)} {tutup_tahun} berhasil ditutup!\"); st.rerun()\n    with tab2:\n        st.subheader(\"Tutup Buku Per Tahun\"); st.warning(\"Perhatian: Tutup buku tahunan akan menutup seluruh periode dalam tahun tersebut!\")\n        tutup_tahun_th = st.selectbox(\"Tahun\", list(range(datetime.now().year, datetime.now().year-5, -1)), key=\"th_tahun\")\n        cursor.execute(\"SELECT COUNT(*) as cnt FROM periode_akuntansi WHERE tahun = %s AND is_closed = 1\", (tutup_tahun_th,))\n        closed_months = cursor.fetchone()['cnt']\n        st.info(f\"Sudah {closed_months} bulan yang ditutup dari 12 bulan.\")\n        if st.button(\"Tutup Buku Tahun Ini\", type=\"primary\"):\n            for bulan in range(1, 13):\n                cursor.execute(\"\"\"\n                    INSERT INTO periode_akuntansi (tahun, bulan, is_closed, closed_at, closed_by)\n                    VALUES (%s, %s, 1, CURRENT_TIMESTAMP, %s)\n                    ON CONFLICT (tahun, bulan) DO UPDATE SET\n                    is_closed = 1, closed_at = CURRENT_TIMESTAMP, closed_by = EXCLUDED.closed_by\n                \"\"\", (tutup_tahun_th, bulan, st.session_state.get('username','admin')))\n            conn.commit(); log_activity(\"TUTUP_BUKU_TAHUN\", f\"Tutup buku tahun {tutup_tahun_th}\")\n            st.success(f\"Buku tahun {tutup_tahun_th} berhasil ditutup!\"); st.rerun()\n    with tab3:\n        st.subheader(\"Status Periode Akuntansi\")\n        periode_df = pd.read_sql_query(\"SELECT tahun, bulan, is_closed, closed_at, closed_by FROM periode_akuntansi ORDER BY tahun DESC, bulan DESC\", conn)\n        if not periode_df.empty:\n            periode_df['bulan_nama'] = periode_df['bulan'].apply(get_month_name)\n            periode_df['status'] = periode_df['is_closed'].apply(lambda x: 'Tertutup' if x else 'Terbuka')\n            st.dataframe(periode_df[['tahun','bulan_nama','status','closed_at','closed_by']], use_container_width=True, hide_index=True)\n        else: st.info(\"Belum ada periode yang ditutup\")\n    conn.close()

# ============================================================
# PAGE: PENGATURAN
# ============================================================

def page_pengaturan():
n    st.markdown('<p class=\"main-header\">Pengaturan</p>', unsafe_allow_html=True)
n    st.markdown('<p class=\"sub-header\">Konfigurasi aplikasi pembukuan</p>', unsafe_allow_html=True)
n    tab1, tab2, tab3 = st.tabs([\"Pajak\", \"Data\", \"Tentang\"])
n    with tab1:
n        st.subheader(\"Konfigurasi Pajak\")\n        conn = get_connection()\n        pajak_df = pd.read_sql_query(\"SELECT * FROM pajak_config WHERE is_active = 1\", conn)\n        conn.close()\n        if not pajak_df.empty:\n            for _, row in pajak_df.iterrows():\n                with st.form(f\"pajak_{row['id']}\"):\n                    col1, col2 = st.columns(2)\n                    with col1: jenis = st.text_input(\"Jenis Pajak\", value=row['jenis_pajak'], key=f\"jenis_{row['id']}\")\n                    with col2: tarif = st.number_input(\"Tarif (%)\", value=float(row['tarif']), step=0.5, key=f\"tarif_{row['id']}\")\n                    keterangan = st.text_area(\"Keterangan\", value=row['keterangan'] or \"\", key=f\"ket_{row['id']}\")\n                    if st.form_submit_button(\"Update\"):\n                        conn = get_connection(); cursor = conn.cursor()\n                        cursor.execute(\"UPDATE pajak_config SET jenis_pajak=%s, tarif=%s, keterangan=%s WHERE id=%s\", (jenis, tarif, keterangan, row['id']))\n                        conn.commit(); conn.close(); st.success(\"Updated!\"); st.rerun()\n    with tab2:\n        st.subheader(\"Manajemen Data\"); st.warning(\"Hati-hati! Aksi di bawah ini tidak dapat dibatalkan.\")\n        col1, col2 = st.columns(2)\n        with col1:\n            st.markdown(\"**Export Database**\")\n            st.info(\"Untuk backup, gunakan fitur Export di dashboard Supabase.\")\n        with col2:\n            st.markdown(\"**Reset Data**\")\n            if st.checkbox(\"Saya mengerti risiko reset data\"):\n                if st.button(\"Reset Semua Data\", type=\"primary\"):\n                    conn = get_connection(); cursor = conn.cursor()\n                    cursor.execute(\"DELETE FROM jurnal_detail\")\n                    cursor.execute(\"DELETE FROM jurnal\")\n                    cursor.execute(\"DELETE FROM invoice_item\")\n                    cursor.execute(\"DELETE FROM invoice\")\n                    cursor.execute(\"DELETE FROM periode_akuntansi\")\n                    cursor.execute(\"DELETE FROM log_aktivitas\")\n                    conn.commit(); conn.close()\n                    st.success(\"Semua data transaksi telah dihapus!\"); st.rerun()\n    with tab3:\n        st.subheader(\"Tentang Aplikasi\")\n        logo_path = os.path.join(os.path.dirname(__file__), \"logo_ceritajiwa.png\")\n        if os.path.exists(logo_path): st.image(logo_path, width=120)\n        st.markdown(\"\"\"\n        **Cerita Jiwa - Sistem Pembukuan Internal**\n\n        Versi: 1.0 (Supabase Edition)\n\n        **Brand Guidelines:**\n        - Warna Utama: #344A61 (Navy Blue)\n        - Warna Sekunder: #D9DBDC, #6D6F71\n        - Font: Avenir Next Bold\n\n        **Fitur:**\n        - AI Jurnal Assistant\n        - Chart of Accounts yang dapat dikustomisasi\n        - Jurnal Umum & Buku Besar\n        - Invoice Generator dengan PDF\n        - Laporan Keuangan (Neraca & Laba Rugi)\n        - Laporan Pajak\n        - Tutup Buku Bulanan & Tahunan\n\n        **Database:** PostgreSQL via Supabase\n\n        Dibuat untuk: **Cerita Jiwa** (Training & Produk Digital)\n        \"\"\")\n\n# ============================================================\n# MAIN APP\n# ============================================================\n\ndef main():\n    set_page_config(); apply_custom_css(); init_database()\n    if 'username' not in st.session_state: st.session_state.username = 'admin'\n    menu = render_sidebar()\n    if menu == \"🏠 Dashboard\": page_dashboard()\n    elif menu == \"📋 Daftar Akun\": page_chart_of_accounts()\n    elif menu == \"🤖 AI Jurnal Assistant\": page_ai_journal()\n    elif menu == \"📝 Jurnal Umum\": page_jurnal_umum()\n    elif menu == \"📖 Buku Besar\": page_buku_besar()\n    elif menu == \"📄 Invoice\": page_invoice()\n    elif menu == \"📊 Laporan Keuangan\": page_laporan_keuangan()\n    elif menu == \"💰 Laporan Pajak\": page_laporan_pajak()\n    elif menu == \"🔒 Tutup Buku\": page_tutup_buku()\n    elif menu == \"⚙️ Pengaturan\": page_pengaturan()\n\nif __name__ == \"__main__\":\n    main()\n```

---

## ⚠️ PERHATIAN PENTING

1. **Di BLOK 7**, ada baris yang diawali `n    ` (dengan huruf `n` di depan) — itu adalah typo dari proses copy. **Hapus semua `n` di awal baris** pada fungsi `page_pengaturan()`. Contoh:
   - `n    st.markdown(...)` → `    st.markdown(...)`
   - `n    tab1, tab2, tab3 = ...` → `    tab1, tab2, tab3 = ...`

2. **File `requirements.txt`** harus berisi 4 baris:          
