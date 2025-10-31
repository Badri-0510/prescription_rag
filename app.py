"""
Flask Web Interface with Database Integration
Handles authentication, patient management, and prescriptions
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
import secrets
from prescription_summarizer import PrescriptionSummarizer
from database_models import Database
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['UPLOAD_FOLDER'] = './uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)

# Initialize systems
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("⚠️  WARNING: GEMINI_API_KEY not found!")
    print("Get free key: https://makersuite.google.com/app/apikey")

summarizer = PrescriptionSummarizer(api_key=API_KEY)
db = Database()

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(user_type=None):
    """Decorator to check if user is logged in"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'error': 'Not authenticated'}), 401
            if user_type and session.get('user_type') != user_type:
                return jsonify({'error': 'Unauthorized'}), 403
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

# ==================== AUTHENTICATION ROUTES ====================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    """Handle login for both doctors and patients"""
    data = request.json
    user_type = data.get('user_type')  # 'doctor' or 'patient'
    identifier = data.get('identifier')  # email for doctor, patient_id for patient
    password = data.get('password')
    
    if user_type == 'doctor':
        user = db.verify_doctor(identifier, password)
        if user:
            session['user_id'] = user['doctor_id']
            session['user_type'] = 'doctor'
            session['user_name'] = user['name']
            session.permanent = True
            return jsonify({
                'success': True,
                'user_type': 'doctor',
                'user_id': user['doctor_id'],
                'name': user['name'],
                'specialization': user['specialization']
            })
    
    elif user_type == 'patient':
        # For patients, just verify patient_id exists (simple auth)
        patient = db.get_patient(identifier)
        if patient:
            session['user_id'] = patient['patient_id']
            session['user_type'] = 'patient'
            session['user_name'] = patient['name']
            session.permanent = True
            return jsonify({
                'success': True,
                'user_type': 'patient',
                'user_id': patient['patient_id'],
                'name': patient['name']
            })
    
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    """Handle logout"""
    session.clear()
    return jsonify({'success': True})

@app.route('/api/session')
def check_session():
    """Check if user is logged in"""
    if 'user_id' in session:
        return jsonify({
            'logged_in': True,
            'user_type': session.get('user_type'),
            'user_id': session.get('user_id'),
            'user_name': session.get('user_name')
        })
    return jsonify({'logged_in': False})

# ==================== PATIENT ROUTES ====================

@app.route('/api/patient/<patient_id>')
@login_required()
def get_patient(patient_id):
    """Get patient information"""
    patient = db.get_patient(patient_id)
    if patient:
        # Remove sensitive fields
        patient.pop('id', None)
        return jsonify(patient)
    return jsonify({'error': 'Patient not found'}), 404

@app.route('/api/patient/search')
@login_required('doctor')
def search_patients():
    """Search patients (doctors only)"""
    query = request.args.get('q', '')
    if len(query) < 2:
        return jsonify([])
    
    results = db.search_patients(query)
    return jsonify(results)

@app.route('/api/patient/add', methods=['POST'])
@login_required('doctor')
def add_patient():
    """Add new patient (doctors only)"""
    data = request.json
    
    success = db.add_patient(
        patient_id=data.get('patient_id'),
        name=data.get('name'),
        age=data.get('age'),
        gender=data.get('gender'),
        phone=data.get('phone'),
        email=data.get('email'),
        address=data.get('address'),
        blood_group=data.get('blood_group'),
        emergency_contact=data.get('emergency_contact')
    )
    
    if success:
        return jsonify({'success': True})
    return jsonify({'error': 'Patient ID already exists'}), 400

# ==================== PRESCRIPTION ROUTES ====================

@app.route('/api/upload', methods=['POST'])
@login_required('doctor')
def upload_prescription():
    """Upload and process prescription"""
    try:
        if 'prescription' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['prescription']
        patient_id = request.form.get('patient_id')
        
        if not patient_id:
            return jsonify({'error': 'Patient ID is required'}), 400
        
        # Verify patient exists
        if not db.verify_patient(patient_id):
            return jsonify({'error': 'Patient not found. Please add patient first.'}), 404
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{patient_id}_{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Process prescription
            file_type = filename.rsplit('.', 1)[1].lower()
            result = summarizer.process_prescription(
                file_path=filepath,
                patient_id=patient_id,
                file_type=file_type
            )
            
            # Save prescription record to database
            prescription_id = f"RX_{timestamp}_{patient_id}"
            db.add_prescription_record(
                prescription_id=prescription_id,
                patient_id=patient_id,
                doctor_id=session.get('user_id'),
                file_path=filepath,
                file_type=file_type,
                diagnosis=result['extracted_data'].get('diagnosis'),
                medications=str(result['extracted_data'].get('medications')),
                notes=result['extracted_data'].get('notes')
            )
            
            return jsonify({
                'success': True,
                'prescription_id': prescription_id,
                'doctor_summary': result['doctor_view'],
                'patient_summary': result['patient_view'],
                'extracted_data': result['extracted_data']
            })
        
        return jsonify({'error': 'Invalid file type'}), 400
    
    except Exception as e:
        print(f"Error processing prescription: {e}")
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@app.route('/api/history/<patient_id>')
@login_required()
def get_patient_history(patient_id):
    """Get patient's medical history"""
    # Check authorization
    if session.get('user_type') == 'patient' and session.get('user_id') != patient_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get summary from ChromaDB
    existing_summary = summarizer.get_existing_summary(patient_id)
    
    if existing_summary:
        # Get patient info
        patient = db.get_patient(patient_id)
        
        # Get prescription records
        prescriptions = db.get_patient_prescriptions(patient_id)
        
        return jsonify({
            'summary': existing_summary,
            'patient': patient,
            'prescriptions': prescriptions,
            'total_prescriptions': len(prescriptions)
        })
    
    return jsonify({'message': 'No history found for this patient'}), 404

@app.route('/api/prescriptions/<patient_id>')
@login_required()
def get_prescriptions(patient_id):
    """Get list of prescriptions for a patient"""
    # Check authorization
    if session.get('user_type') == 'patient' and session.get('user_id') != patient_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    prescriptions = db.get_patient_prescriptions(patient_id)
    return jsonify(prescriptions)

# ==================== DASHBOARD ROUTES ====================

@app.route('/api/dashboard/stats')
@login_required('doctor')
def get_dashboard_stats():
    """Get dashboard statistics"""
    doctor_id = session.get('user_id')
    stats = db.get_dashboard_stats(doctor_id)
    return jsonify(stats)

# ==================== DEMO ACCOUNTS INFO ====================

@app.route('/api/demo-accounts')
def get_demo_accounts():
    """Get demo account credentials for testing"""
    return jsonify({
        'doctor': {
            'email': 'doctor@demo.com',
            'password': 'doctor123',
            'name': 'Dr. Rajesh Kumar'
        },
        'patient': {
            'patient_id': 'P001',
            'name': 'Priya Sharma'
        }
    })

# ==================== HEALTH CHECK ====================

@app.route('/health')
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'gemini_configured': bool(API_KEY),
        'database_connected': True
    })

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    print("=" * 60)
    print("🏥 MediSummarize - Patient Prescription System")
    print("=" * 60)
    print(f"Server: http://localhost:5000")
    print(f"Gemini API: {'✅ Configured' if API_KEY else '❌ Not configured'}")
    print(f"Database: ✅ Initialized")
    print("\n📝 Demo Accounts:")
    print("   Doctor: doctor@demo.com / doctor123")
    print("   Patient: P001")
    print("=" * 60)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

