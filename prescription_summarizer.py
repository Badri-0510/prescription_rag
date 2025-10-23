"""
prescription_summarizer.py
Patient Prescription Summarizer using Google Gemini 1.5 Pro
RAG Implementation with ChromaDB for incremental summary updates
FIXED: Separate doctor and patient view summaries with minimal metadata
"""

import os
from datetime import datetime
from typing import Dict, List, Optional
import json
import pickle
from pathlib import Path

# Required packages:
# pip install google-generativeai pillow pypdf2 chromadb sentence-transformers

import google.generativeai as genai
from chromadb import PersistentClient
from chromadb.config import Settings
import chromadb.utils.embedding_functions as embedding_functions
import PyPDF2
from PIL import Image

class PrescriptionSummarizer:
    def __init__(self, api_key: str, db_path: str = "./patient_db"):
        """Initialize the summarizer with Gemini API key and database path"""
        self.api_key = api_key
        self.db_path = db_path
        
        # Configure Gemini
        genai.configure(api_key=api_key)
        
        # Initialize Gemini model
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Initialize ChromaDB with sentence-transformers for embeddings
        self.chroma_client = PersistentClient(
            path=db_path,
            settings=Settings(
                anonymized_telemetry=False
            )
        )
        
        # Use sentence-transformers for embeddings (free, local)
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        # Create separate collections for doctor and patient views
        collection_names = [c.name for c in self.chroma_client.list_collections()]
        
        if "doctor_summaries" in collection_names:
            self.doctor_collection = self.chroma_client.get_collection(
                name="doctor_summaries",
                embedding_function=self.embedding_function
            )
        else:
            self.doctor_collection = self.chroma_client.create_collection(
                name="doctor_summaries",
                embedding_function=self.embedding_function
            )
        
        if "patient_summaries" in collection_names:
            self.patient_collection = self.chroma_client.get_collection(
                name="patient_summaries",
                embedding_function=self.embedding_function
            )
        else:
            self.patient_collection = self.chroma_client.create_collection(
                name="patient_summaries",
                embedding_function=self.embedding_function
            )
        
        # Create metadata storage
        self.metadata_file = os.path.join(db_path, "patient_metadata.pkl")
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict:
        """Load patient metadata from file"""
        if os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'rb') as f:
                return pickle.load(f)
        return {}
    
    def _save_metadata(self):
        """Save patient metadata to file"""
        os.makedirs(self.db_path, exist_ok=True)
        with open(self.metadata_file, 'wb') as f:
            pickle.dump(self.metadata, f)
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF prescription"""
        text = ""
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text()
        return text
    
    def process_image_directly(self, image_path: str) -> Dict:
        """Use Gemini's vision to read prescription image directly (NO OCR NEEDED!)"""
        img = Image.open(image_path)
        
        prompt = """
        Analyze this prescription image and extract the following information:
        - Patient Name
        - Age/DOB
        - Date of prescription
        - Chief Complaints/Symptoms
        - Diagnosis
        - Medications (name, dosage, frequency, duration)
        - Tests/Lab work ordered
        - Doctor's notes/advice
        
        Return the information in JSON format with keys: patient_name, age, date, complaints, diagnosis, medications, tests, notes
        If any field is not found, use null.
        Be thorough and extract all visible information.
        """
        
        response = self.model.generate_content([prompt, img])
        
        try:
            # Clean response text
            text = response.text.strip()
            # Remove markdown code blocks if present
            if text.startswith('```json'):
                text = text[7:]
            if text.startswith('```'):
                text = text[3:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()
            
            return json.loads(text)
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            print(f"Raw response: {response.text}")
            return {"raw_text": response.text, "error": "Could not parse structured data"}
    
    def extract_prescription_info(self, text: str) -> Dict:
        """Extract structured information from prescription text using Gemini"""
        prompt = f"""
        Extract the following information from this prescription:
        - Patient Name
        - Age/DOB
        - Date of prescription
        - Chief Complaints/Symptoms
        - Diagnosis
        - Medications (name, dosage, frequency, duration)
        - Tests/Lab work ordered
        - Doctor's notes/advice
        
        Prescription Text:
        {text}
        
        Return ONLY valid JSON format with keys: patient_name, age, date, complaints, diagnosis, medications, tests, notes
        If any field is not found, use null.
        Do not include any markdown formatting or code blocks.
        """
        
        response = self.model.generate_content(prompt)
        
        try:
            text = response.text.strip()
            # Remove markdown code blocks if present
            if text.startswith('```json'):
                text = text[7:]
            if text.startswith('```'):
                text = text[3:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()
            
            return json.loads(text)
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            print(f"Raw response: {response.text}")
            return {"raw_text": response.text, "error": "Could not parse structured data"}
    
    def get_existing_summary(self, patient_id: str, role: str = "doctor") -> Optional[str]:
        """
        RETRIEVAL STEP (R in RAG)
        Retrieve existing patient summary from ChromaDB vector store BY ROLE
        """
        # Select the correct collection based on role
        collection = self.doctor_collection if role == "doctor" else self.patient_collection
        
        try:
            results = collection.query(
                query_texts=[f"patient_id:{patient_id} {role} summary"],
                n_results=1,
                where={"patient_id": patient_id}
            )
            
            if results['documents'] and len(results['documents'][0]) > 0:
                return results['documents'][0][0]
        except Exception as e:
            print(f"ChromaDB query error: {e}")
        
        # Fallback to metadata with role-specific key
        if patient_id in self.metadata:
            return self.metadata[patient_id].get(f'latest_summary_{role}')
        
        return None
    
    def generate_summary(self, new_prescription: Dict, existing_summary: Optional[str], 
                        patient_id: str, role: str = "doctor") -> str:
        """
        AUGMENTED GENERATION STEP (AG in RAG)
        Generate or update patient summary based on role (doctor/patient)
        Combines OLD summary + NEW prescription data
        """
        
        if role == "doctor":
            prompt = f"""
            You are a medical assistant helping doctors. Create a comprehensive medical summary.
            Generate with terminologies like 'This patient is' (in third person)
            
            Existing Summary (if any):
            {existing_summary or "No previous summary available. This is the first prescription."}
            
            New Prescription Data:
            {json.dumps(new_prescription, indent=2)}
            
            Generate an UPDATED summary including:
            1. Patient Demographics
            2. Medical History Timeline (chronological, with dates)
            3. Current Active Medications (what they're taking NOW)
            4. Past Medications (discontinued or completed)
            5. Chronic Conditions
            6. Recent Symptoms/Complaints
            7. Test Results & Findings
            8. Treatment Response & Progress
            9. Clinical Notes & Observations
            
            Keep medical terminology. Be precise and clinical.
            Format clearly with sections using numbers for points.
            Merge with existing information intelligently - don't duplicate entries.
            If this is an update, show the progression/changes over time.
            Do not use # or markdown headers, use numbered points instead.
            """
        else:  # patient view
            prompt = f"""
            You are a medical assistant helping patients understand their health record.
            Generate in first person speech like "You are..."
            
            Existing Summary (if any):
            {existing_summary or "No previous summary available. This is your first prescription."}
            
            New Prescription Data:
            {json.dumps(new_prescription, indent=2)}
            
            Generate an UPDATED summary in simple language including:
            1. Your Basic Information
            2. Health History (what you've been treated for, with dates)
            3. Current Medications (what you're taking now and why)
            4. Past Treatments
            5. Health Conditions
            6. Recent Visits & Symptoms
            7. Test Results (in simple terms)
            8. Doctor's Advice & Next Steps
            
            Use simple, non-medical language. Explain medical terms in brackets.
            Be reassuring and clear. Format with sections using numbers for points.
            Merge with existing information intelligently - don't duplicate entries.
            If this is an update, explain what has changed in your treatment.
            Do not use # or markdown headers, use numbered points instead.
            """
        
        response = self.model.generate_content(prompt)
        summary = response.text
        
        # Select the correct collection based on role
        collection = self.doctor_collection if role == "doctor" else self.patient_collection
        
        # Store updated summary in role-specific ChromaDB collection
        doc_id = f"{patient_id}_{role}_{datetime.now().timestamp()}"
        
       

        # MINIMAL METADATA - only primitives, no lists or nested objects
        clean_metadata = {
            "patient_id": patient_id,
            "timestamp": datetime.now().isoformat(),
            "role": role
        }
        
        clean_metadata = self.sanitize_metadata(clean_metadata)

                # Ensure summary is always a string
       # Force summary into a string safe for ChromaDB
        if isinstance(summary, list) or isinstance(summary, dict):
          summary = json.dumps(summary, ensure_ascii=False)
        else:
          summary = str(summary)
        print("DEBUG: type of summary =", type(summary))
        print("DEBUG: type of clean_metadata =", type(clean_metadata))
        # Just before collection.add()
        for k, v in clean_metadata.items():
           print(f"DEBUG metadata key: {k}, type: {type(v)}, value: {v}")

 
        try:
            collection.add(
                documents=[summary],  # The summary contains all the info
                metadatas=[clean_metadata],  # Just for filtering
                ids=[doc_id]
            )
        except Exception as e:
            print(f"ChromaDB storage error: {e}")
            print(f"Attempted metadata: {clean_metadata}")
        
        # Store in metadata as backup with full prescription data
        if patient_id not in self.metadata:
            self.metadata[patient_id] = {}
        
        self.metadata[patient_id][f'latest_summary_{role}'] = summary
        self.metadata[patient_id][f'latest_prescription_{role}'] = new_prescription
        self.metadata[patient_id]['last_updated'] = datetime.now().isoformat()
        self._save_metadata()
        
        return summary
    
    def process_prescription(self, file_path: str, patient_id: str, 
                           file_type: str = "pdf") -> Dict[str, str]:
        """
        MAIN RAG PIPELINE
        1. Extract prescription data
        2. RETRIEVE existing summaries (R) - SEPARATE for doctor and patient
        3. AUGMENT with new data and GENERATE updated summaries (AG)
        4. Return both doctor and patient views
        """
        
        # Step 1: Extract information from prescription
        if file_type.lower() == "pdf":
            text = self.extract_text_from_pdf(file_path)
            prescription_data = self.extract_prescription_info(text)
        elif file_type.lower() in ["jpg", "jpeg", "png"]:
            # Use Gemini's vision directly for images (no OCR needed!)
            prescription_data = self.process_image_directly(file_path)
        else:
            raise ValueError("Unsupported file type. Use PDF or image formats.")
        
        prescription_data["patient_id"] = patient_id
        
        # Step 2: RETRIEVE existing summaries (RAG - Retrieval) - SEPARATE BY ROLE
        existing_doctor_summary = self.get_existing_summary(patient_id, role="doctor")
        existing_patient_summary = self.get_existing_summary(patient_id, role="patient")
        
        # Step 3: GENERATE summaries with AUGMENTATION (RAG - Augmented Generation)
        # Each role gets its own existing summary context
        doctor_summary = self.generate_summary(
            prescription_data, existing_doctor_summary, patient_id, role="doctor"
        )
        
        patient_summary = self.generate_summary(
            prescription_data, existing_patient_summary, patient_id, role="patient"
        )
        
        return {
            "doctor_view": doctor_summary,
            "patient_view": patient_summary,
            "extracted_data": prescription_data
        }
    def sanitize_metadata(self,metadata: Dict) -> Dict[str, str]:
      """Convert all metadata values into safe strings (no lists/dicts)."""
      safe = {}
      for k, v in metadata.items():
         if isinstance(v, (list, dict)):
            safe[k] = json.dumps(v)  # store as JSON string
         else:
            safe[k] = str(v)  # force everything else to string
      return safe
 