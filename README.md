
# SmartStudy AI

SmartStudy AI is a Python-based smart study assistant built using Streamlit and Microsoft Azure Document Intelligence.

## Features

- PDF Upload and Text Extraction
- Azure Document Intelligence Integration
- Notes Summarizer
- Ask Your Notes
- Quiz Generator
- Quiz Analytics
- Study Planner
- Pomodoro Timer
- Flashcards
- Study Recommendations
- Learning Progress Dashboard

## Technologies Used

- Python
- Streamlit
- PyPDF2
- Microsoft Azure Document Intelligence
- python-dotenv

## How to Run

1. Download or clone the project.
2. Open the project folder in VS Code.
3. Install the dependencies:

   pip install -r requirements.txt

4. Create a `.env` file with your own Azure credentials:

   AZURE_DOCUMENT_ENDPOINT=your_endpoint
   AZURE_DOCUMENT_KEY=your_api_key

5. Start the application:

   streamlit run app.py

6. Open the local URL displayed in the terminal.

## Azure Integration

SmartStudy AI uses Microsoft Azure Document Intelligence to extract text from PDF documents, including scanned PDFs.

Local PDF extraction using PyPDF2 is also available without Azure.

Azure usage is subject to the resource's pricing tier and quota.

## Note

The summarizer, quiz generator, flashcards, and study recommendations use rule-based techniques. Azure Document Intelligence is used for PDF text extraction.
