"""
SQLite Database Models for User Authentication & Patient Management
Stores: Doctors, Patients, Prescriptions metadata
"""

import sqlite3
from datetime import datetime
from typing import Optional, Dict, List
import hashlib
import json

class Database:
    def __init__(self, db_path: str = "./medical_records.db"):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        return conn
    
    def init_db(self):
        """Initialize database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Doctors table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS doctors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                specialization TEXT,
                phone TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Patients table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                age INTEGER,
                gender TEXT,
                phone TEXT,
                email TEXT,
                address TEXT,
                blood_group TEXT,
                emergency_contact TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Prescriptions metadata table (actual files stored separately)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prescriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prescription_id TEXT UNIQUE NOT NULL,
                patient_id TEXT NOT NULL,
                doctor_id TEXT,
                file_path TEXT,
                file_type TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                diagnosis TEXT,
                medications TEXT,
                notes TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
                FOREIGN KEY (doctor_id) REFERENCES doctors(doctor_id)
            )
        ''')
        
        # Sessions table (for login tracking)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_type TEXT NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # Add default demo accounts
        self.create_demo_accounts()
    
    def hash_password(self, password: str) -> str:
        """Hash password for security"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_demo_accounts(self):
        """Create demo doctor and patient accounts"""
        # Use a separate connection with autocommit
        conn = None
        try:
            conn = self.get_connection()
            conn.isolation_level = None  # Autocommit mode
            cursor = conn.cursor()
            
            # Demo Doctor
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO doctors (doctor_id, name, email, password_hash, 
                                       specialization, phone)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', ("DOC001", " Rajesh Kumar", "doctor@demo.com", 
                      self.hash_password("doctor123"), "General Medicine", "+91 9876543210"))
            except:
                pass
            
            # Demo Patient
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO patients (patient_id, name, age, gender, phone, 
                                        email, address, blood_group, emergency_contact)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', ("P001", "Sachin sansare", 28, "Male", "+91 9876543211",
                      "sachin@demo.com", "Chennai, Tamil Nadu", "O+", None))
            except:
                pass
                
        finally:
            if conn:
                conn.close()
    
    # ==================== DOCTOR METHODS ====================
    
    def add_doctor(self, doctor_id: str, name: str, email: str, 
                   password: str, specialization: str = None, 
                   phone: str = None) -> bool:
        """Add new doctor"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO doctors (doctor_id, name, email, password_hash, 
                                   specialization, phone)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (doctor_id, name, email, self.hash_password(password), 
                  specialization, phone))
            
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            if conn:
                conn.close()
    
    def verify_doctor(self, email: str, password: str) -> Optional[Dict]:
        """Verify doctor login"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM doctors 
            WHERE email = ? AND password_hash = ?
        ''', (email, self.hash_password(password)))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_doctor(self, doctor_id: str) -> Optional[Dict]:
        """Get doctor information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM doctors WHERE doctor_id = ?', (doctor_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    # ==================== PATIENT METHODS ====================
    
    def add_patient(self, patient_id: str, name: str, age: int = None,
                   gender: str = None, phone: str = None, email: str = None,
                   address: str = None, blood_group: str = None,
                   emergency_contact: str = None) -> bool:
        """Add new patient"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO patients (patient_id, name, age, gender, phone, 
                                    email, address, blood_group, emergency_contact)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (patient_id, name, age, gender, phone, email, address, 
                  blood_group, emergency_contact))
            
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            if conn:
                conn.close()
    
    def get_patient(self, patient_id: str) -> Optional[Dict]:
        """Get patient information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM patients WHERE patient_id = ?', (patient_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def update_patient(self, patient_id: str, **kwargs) -> bool:
        """Update patient information"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Build dynamic update query
        fields = []
        values = []
        for key, value in kwargs.items():
            if value is not None:
                fields.append(f"{key} = ?")
                values.append(value)
        
        if not fields:
            return False
        
        values.append(patient_id)
        query = f"UPDATE patients SET {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE patient_id = ?"
        
        cursor.execute(query, values)
        conn.commit()
        conn.close()
        return True
    
    def search_patients(self, query: str) -> List[Dict]:
        """Search patients by name or ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM patients 
            WHERE patient_id LIKE ? OR name LIKE ?
            ORDER BY name
        ''', (f'%{query}%', f'%{query}%'))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def verify_patient(self, patient_id: str) -> bool:
        """Verify if patient exists"""
        return self.get_patient(patient_id) is not None
    
    # ==================== PRESCRIPTION METHODS ====================
    
    def add_prescription_record(self, prescription_id: str, patient_id: str,
                               doctor_id: str, file_path: str, file_type: str,
                               diagnosis: str = None, medications: str = None,
                               notes: str = None) -> bool:
        """Add prescription record"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO prescriptions (prescription_id, patient_id, doctor_id,
                                         file_path, file_type, diagnosis, 
                                         medications, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (prescription_id, patient_id, doctor_id, file_path, file_type,
                  diagnosis, medications, notes))
            
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def get_patient_prescriptions(self, patient_id: str) -> List[Dict]:
        """Get all prescriptions for a patient"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT p.*, d.name as doctor_name 
            FROM prescriptions p
            LEFT JOIN doctors d ON p.doctor_id = d.doctor_id
            WHERE p.patient_id = ?
            ORDER BY p.upload_date DESC
        ''', (patient_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_prescription_count(self, patient_id: str) -> int:
        """Get count of prescriptions for a patient"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) as count FROM prescriptions 
            WHERE patient_id = ?
        ''', (patient_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result['count'] if result else 0
    
    # ==================== STATS METHODS ====================
    
    def get_dashboard_stats(self, doctor_id: str = None) -> Dict:
        """Get dashboard statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        stats = {}
        
        # Total patients
        cursor.execute('SELECT COUNT(*) as count FROM patients')
        stats['total_patients'] = cursor.fetchone()['count']
        
        # Total prescriptions
        if doctor_id:
            cursor.execute('SELECT COUNT(*) as count FROM prescriptions WHERE doctor_id = ?', (doctor_id,))
        else:
            cursor.execute('SELECT COUNT(*) as count FROM prescriptions')
        stats['total_prescriptions'] = cursor.fetchone()['count']
        
        # Recent patients (last 7 days)
        cursor.execute('''
            SELECT COUNT(*) as count FROM patients 
            WHERE created_at >= datetime('now', '-7 days')
        ''')
        stats['new_patients_week'] = cursor.fetchone()['count']
        
        conn.close()
        return stats


# Example Usage
if __name__ == "__main__":
    db = Database()
    
    # Test doctor login
    doctor = db.verify_doctor("doctor@demo.com", "doctor123")
    if doctor:
        print(f"✅ Doctor logged in: {doctor['name']}")
    
    # Test patient lookup
    patient = db.get_patient("P001")
    if patient:
        print(f"✅ Patient found: {patient['name']}, Age: {patient['age']}")
    
    # Get stats
    stats = db.get_dashboard_stats()
    print(f"📊 Stats: {stats}")