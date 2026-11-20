
import os
from dotenv import load_dotenv
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
from azure.core.credentials import AzureKeyCredential

load_dotenv()


def extract_text_with_azure(pdf_bytes):
    endpoint = os.getenv("AZURE_DOCUMENT_ENDPOINT")
    key = os.getenv("AZURE_DOCUMENT_KEY")

    if not endpoint or not key:
        return "Azure configuration is missing."

    try:
        client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(key)
        )

        poller = client.begin_analyze_document(
            "prebuilt-read",
            AnalyzeDocumentRequest(bytes_source=pdf_bytes)
        )

        result = poller.result()

        return result.content or "No text found in document."

    except Exception as e:
        return f"Azure Error: {str(e)}"
