from .models import *
from django.views.decorators.csrf import csrf_exempt

import pdfkit
import logging
from main.settings import HTML_ROOT,RECEIPT_ROOT,REPORT_ROOT
import tempfile
import os
from django.template.loader import render_to_string

@csrf_exempt
def saveReport(html,identifier):
    html_path_local = f"{HTML_ROOT}/{identifier}.html"
   
    pdf_path = f"{REPORT_ROOT}/{identifier}.pdf"

    with open(html_path_local, "w") as file:
        file.write(html)

    options = {
        "disable-javascript": "",
        "enable-local-file-access": "",
    }
    
    config = pdfkit.configuration(wkhtmltopdf='C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe')

    try:
        # Convert HTML to PDF
        pdfkit.from_file(html_path_local, pdf_path, configuration=config, options=options)
        
    except Exception as e:
        logging.error(f"PDF Generation Error: {str(e)}")
   
    # Send the file as a response to the user
    return pdf_path


def save(html_content, filename, footer_html=None,header_html=None):
    print("ASDASDASDASDASD")
    # Ensure output directory exists
    output_dir=RECEIPT_ROOT
    os.makedirs(output_dir, exist_ok=True)
    pdf_path = os.path.join(output_dir, f"{filename}.pdf")

    # Create temporary files for main HTML and footer
    with tempfile.NamedTemporaryFile(suffix=f"{filename}.html", delete=False) as main_file:
        main_file.write(html_content.encode("utf-8"))
        main_file_path = main_file.name
        print(main_file_path)
    try:
        # PDF configuration (Windows example)
        config = pdfkit.configuration(
            wkhtmltopdf=r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
        )
     
        if not footer_html==None:
          footer_file_path=HTML_ROOT+f"/{filename}_footer.html"
          with open(footer_file_path,'wb') as file:
              file.write(footer_html.encode("utf-8"))
        if not header_html==None:
          header_file_path=HTML_ROOT+f"/{filename}_header.html"
          with open(header_file_path,'wb') as file:
              file.write(header_html.encode("utf-8"))
              
          pdfkit.from_file(
                
                main_file_path,
                pdf_path,
                configuration=config,
                 options = {
                    "enable-local-file-access": "",
                    "footer-html":footer_file_path,
                    "header-html":header_file_path
                    }
                 
                    )
        else:
            pdfkit.from_file(
                main_file_path,
                pdf_path,
                configuration=config,
                options = {
                "enable-local-file-access": "",  # REQUIRED for local images
}
            )
    
    except Exception as e:
        print(str(e))
    finally:
        # Clean up temporary HTML files
        os.remove(main_file_path)
        try:
            os.remove(footer_file_path)
        except:
            print("No Footer")
    return pdf_path

@csrf_exempt
def saveLabel(html,report_name):
    html_path_local = f"{HTML_ROOT}/{report_name}.html"
    pdf_path = f"{REPORT_ROOT}/{report_name}.pdf"

    with open(html_path_local, "w") as file:
        file.write(html)

    options = {
        "disable-javascript": "",
        "enable-local-file-access": "",
    }
    
    config = pdfkit.configuration(wkhtmltopdf='C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe')

    try:
        # Convert HTML to PDF
        pdfkit.from_file(html_path_local, pdf_path, configuration=config, options=options)
    except Exception as e:
        logging.error(f"PDF Generation Error: {str(e)}")
   
    # Send the file as a response to the user
    return pdf_path
