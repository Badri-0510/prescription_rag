Feature Implemented:

Developed and implemented the Prescription Summarizer module.
Completed RAG (Retrieval-Augmented Generation) pipeline for summarization.

Technical Stack Used:

Vector Database: ChromaDB for efficient embedding storage and retrieval.
Model: Gemini 2.5 Flash for text and document understanding.
Database: SQLite for lightweight data handling.

Functionality Overview:

The summarizer generates two types of outputs:
For Doctors: Summary focused on medical terms and case-specific insights.
For Patients: Simplified summary based on prescription content.

Prescription Input Options: Users can upload images or PDFs of prescriptions.

The file is sent to Gemini, which extracts data and returns a JSON file.
The JSON output is then processed by the RAG model to produce a final summarized report.

Testing Status:
Functionality tested successfully — summarizer works as expected for both input formats (image and PDF).
