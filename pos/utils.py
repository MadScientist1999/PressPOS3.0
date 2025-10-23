# utils/pdf_generator.py
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import io
from django.template.loader import render_to_string
from django.core.files.base import ContentFile
from main.settings import RECEIPT_ROOT
from django.http import FileResponse, HttpResponse
from .saver import save
import os
import logging
from .models import BankingDetails

logger = logging.getLogger(__name__)

def generate_document_pdf(transaction):
    
    try:
       
        context = {
            "transaction": transaction,  
        }
        html_content = render_to_string("sale_complete.html", context)
        if transaction.isA4:    
                footer_html = render_to_string("footerA4.html", {
                    "transaction": transaction
                })
                header_html = render_to_string("headerA4.html", {
                    "transaction": transaction
                })
        else:
            footer_html = None
            header_html = None

        # 3️⃣ Generate PDF using save(), passing both HTMLs
        pdf_path = save(html_content=html_content, filename=f"{transaction.branch.name}_{transaction.invoiceNo}", footer_html=footer_html,header_html=header_html)

        if os.path.exists(pdf_path):
            transaction.file=pdf_path
            transaction.save()
            return FileResponse(open(pdf_path, 'rb'), content_type='application/pdf')
    except Exception as e:
          print(str(e))
          logger.error(f"Error generating PDF: {e}")
          return HttpResponse(status=500)
   