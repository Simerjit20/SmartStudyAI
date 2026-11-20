
from azure_service import extract_text_with_azure

with open("sample.pdf", "rb") as file:
    pdf_bytes = file.read()

result = extract_text_with_azure(pdf_bytes)

print(result)
