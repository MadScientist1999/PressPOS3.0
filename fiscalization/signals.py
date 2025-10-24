import os
from pathlib import Path
from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.conf import settings
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.hazmat.backends import default_backend
from django.db import connection
import threading
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import FiscalReceipt, FiscalCredit,FiscalDebit,OpenDay,DailyReports,ReceiptError,FiscalBranch,FiscalReportEntry,DailyReports,ReceiptCounters
from pos.models import Currency,Company
from .views import submit_receipt
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from decimal import Decimal
import threading
import time
import json
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import os
import logging
from django.db.models import F

CERTIFICATE_ROOT = os.path.join(settings.BASE_DIR, "FILES/certificates")
processing_threads = {}
processing_locks = {}
logging.basicConfig(
    filename="debug.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
ERRORS = {
    "RCPT010": {"severity": "RED", "blocks_submission": False, "message": "Wrong currency code is used"},
    "RCPT011": {"severity": "RED", "blocks_submission": True,  "message": "Receipt counter is not sequential"},
    "RCPT012": {"severity": "RED", "blocks_submission": True,  "message": "Receipt global number is not sequential"},
    "RCPT013": {"severity": "RED", "blocks_submission": False, "message": "Invoice number is not unique"},
    "RCPT014": {"severity": "YELLOW", "blocks_submission": False, "message": "Receipt date is earlier than fiscal day opening date"},
    "RCPT015": {"severity": "RED", "blocks_submission": False, "message": "Credited/debited invoice data is not provided"},
    "RCPT016": {"severity": "RED", "blocks_submission": False, "message": "No receipt lines provided"},
    "RCPT017": {"severity": "RED", "blocks_submission": False, "message": "Taxes information is not provided"},
    "RCPT018": {"severity": "RED", "blocks_submission": False, "message": "Payment information is not provided"},
    "RCPT019": {"severity": "RED", "blocks_submission": False, "message": "Invoice total amount is not equal to sum of all invoice lines"},
    "RCPT020": {"severity": "RED", "blocks_submission": False, "message": "Invoice signature is not valid"},
    "RCPT021": {"severity": "RED", "blocks_submission": False, "message": "VAT tax is used in invoice while taxpayer is not VAT taxpayer"},
    "RCPT022": {"severity": "RED", "blocks_submission": False, "message": "Invoice sales line price must be greater than 0 (less than 0 for Credit note), discount line price must be less than 0 for Invoice"},
    "RCPT023": {"severity": "RED", "blocks_submission": False, "message": "Invoice line quantity must be positive"},
    "RCPT024": {"severity": "RED", "blocks_submission": False, "message": "Invoice line total is not equal to unit price × quantity"},
    "RCPT025": {"severity": "RED", "blocks_submission": False, "message": "Invalid tax is used"},
    "RCPT026": {"severity": "RED", "blocks_submission": False, "message": "Incorrectly calculated tax amount"},
    "RCPT027": {"severity": "RED", "blocks_submission": False, "message": "Incorrectly calculated total sales amount (including tax)"},
    "RCPT028": {"severity": "RED", "blocks_submission": False, "message": "Payment amount must be ≥ 0 (≤ 0 for Credit note)"},
    "RCPT029": {"severity": "RED", "blocks_submission": False, "message": "Credited/debited invoice information provided for regular invoice"},
    "RCPT030": {"severity": "RED", "blocks_submission": True,  "message": "Invoice date is earlier than previously submitted receipt date"},
    "RCPT031": {"severity": "YELLOW", "blocks_submission": False, "message": "Invoice is submitted with a future date"},
    "RCPT032": {"severity": "RED", "blocks_submission": False, "message": "Credit / debit note refers to non-existing invoice"},
    "RCPT033": {"severity": "RED", "blocks_submission": False, "message": "Credited/debited invoice is issued more than 12 months ago"},
    "RCPT034": {"severity": "RED", "blocks_submission": False, "message": "Note for credit/debit note is not provided"},
    "RCPT035": {"severity": "RED", "blocks_submission": False, "message": "Total credit note amount exceeds original invoice amount"},
    "RCPT036": {"severity": "RED", "blocks_submission": False, "message": "Credit/debit note uses other taxes than used in the original invoice"},
    "RCPT037": {"severity": "RED", "blocks_submission": False, "message": "Invoice total amount is not equal to sum of all invoice lines and taxes applied"},
    "RCPT038": {"severity": "RED", "blocks_submission": False, "message": "Invoice total amount is not equal to sum of sales amount including tax in tax table"},
    "RCPT039": {"severity": "RED", "blocks_submission": False, "message": "Invoice total amount is not equal to sum of all payment amounts"},
    "RCPT040": {"severity": "RED", "blocks_submission": False, "message": "Invoice total amount must be ≥ 0 (≤ 0 for Credit note)"},
    "RCPT041": {"severity": "YELLOW", "blocks_submission": False, "message": "Invoice is issued after fiscal day end"},
    "RCPT042": {"severity": "RED", "blocks_submission": False, "message": "Credit/debit note uses other currency than used in the original invoice"},
    "RCPT043": {"severity": "RED", "blocks_submission": False, "message": "Mandatory buyer data fields are not provided"},
    "RCPT047": {"severity": "RED", "blocks_submission": False, "message": "HS code must be sent if taxpayer is a VAT payer"},
    "RCPT048": {"severity": "RED", "blocks_submission": False, "message": "HS code length must be 4 or 8 digits depending on taxpayer VAT status and applied tax"},
}



def load_fiscal_variables(branch_name):
    """Load certificate and device info for a branch."""
    branch_path = os.path.join(CERTIFICATE_ROOT, branch_name)
    Path(branch_path).mkdir(exist_ok=True)

    config = {
        "branch": branch_name,
        "device_id": None,
        "serial": None,
        "production": None,
        "keystore_path": None,
        'public_path': None,
        "password": None,
        "private_path": None,
        "certificate_path": None,
        "base_url": None,
        "logo":None
    }
    keys = {"private_key": None, "certificate": None}

    for filename in os.listdir(branch_path):
        full_path = os.path.join(branch_path, filename)

        if filename.endswith("CN.txt"):
            with open(full_path, "r") as f:
                content = f.read()
                try:
                    config["device_id"] = content.split("00000")[1]
                    config["serial"] = content.split("-00000")[0].replace("ZIMRA-", "")
                    config["production"] = filename.endswith("PCN.txt")
                except IndexError:
                    pass  # malformed CN.txt

        elif filename.endswith(".p12"):
            config["keystore_path"] = full_path
        elif filename.endswith("password.txt"):
            with open(full_path, "r") as f:
                config["password"] = f.read().strip()
        elif filename.endswith("private.pem"):
            config["private_path"] = full_path
        elif filename.endswith("public.pem"):
            config["public_path"] = full_path
        elif filename.endswith("certificate.pem"):
            config["certificate_path"] = full_path
        elif filename.endswith(".png"):
            config["logo"]=full_path
    if config["device_id"]:
        url = "https://fdmsapi.zimra.co.zw" if config["production"] else "https://fdmsapitest.zimra.co.zw"
        config["base_url"] = f"{url}/Device/v1/{config['device_id']}/"

        if config["keystore_path"] and config["password"]:
            with open(config["keystore_path"], "rb") as f:
                p12_data = f.read()
                private_key, certificate, _ = load_key_and_certificates(
                    p12_data,
                    config["password"].encode(),
                    backend=default_backend()
                )
                keys["private_key"] = private_key
                keys["certificate"] = certificate

    return config, keys


@receiver(post_migrate)
def populate_errors(sender, **kwargs):
   
    errors=ReceiptError.objects.all().__len__()
    if not errors>0:
        for code, details in ERRORS.items():
            ReceiptError.objects.get_or_create(
                code=code,
                defaults={
                    "severity": details["severity"],
                    "blocks_submission": details["blocks_submission"],
                    "message": details["message"],
                },
            )

@receiver(post_save, sender=FiscalBranch)
def fiscalbranch_post_save(sender, instance, created, **kwargs):
    """Initialize certificates and keys when a FiscalBranch is created."""
    if created:
        try:
            config, keys = load_fiscal_variables(instance.fiscal_branch)
            # Save paths or info to model if needed
            instance.device_id = config.get("device_id")
            instance.serial = config.get("serial")
            instance.production = config.get("production")
            instance.keystore_path = config.get("keystore_path")
            instance.password = config.get("password")
            instance.private_key = config.get("private_path")
            instance.public_key = config.get("public_path")
            instance.certificate_path = config.get("certificate_path")
            instance.save(update_fields=[
                "device_id", "serial", "production",
                "keystore_path", "password",
                "private_key", "certificate", "public_key"
            ])
        except Exception as e:
            print(f"Error initializing fiscal variables for {instance.name}: {e}")



@receiver(post_migrate)
def fiscal_post_migrate(sender, **kwargs):
    print("Post-migrate signal triggered for fiscalization!")
    CERTIFICATE_ROOT = "FILES/certificates"  # or your actual path
    branches=FiscalBranch.objects.count()
    reg_branches=os.listdir(CERTIFICATE_ROOT).__len__()
    if not branches==reg_branches:
        # Loop over folders in certificate root
        for branch_name in os.listdir(CERTIFICATE_ROOT):
            branch_path = os.path.join(CERTIFICATE_ROOT, branch_name)
            if not os.path.isdir(branch_path):
                continue  # skip files, only folders
            
            # Create or get the FiscalBranch
            branch, created = FiscalBranch.objects.get_or_create(name=branch_name)
            company= Company.objects.all().last()
            if company is None:
               company= Company.objects.create(name="Substitute" )

            # Load the fiscal variables
            try:
                config, keys = load_fiscal_variables(branch_name)
                if config:
                    branch.name=branch_name
                    branch.device_id = config.get("device_id")
                    branch.serial = config.get("serial")
                    branch.production = config.get("production")
                    branch.keystore = config.get("keystore_path")
                    branch.password = config.get("password")
                    branch.private_key = config.get("private_path")
                    branch.public_key = config.get("public_path")
                    branch.certificate = config.get("certificate_path")
                    branch.company=company
                    branch.base_url=config.get("base_url")
                    branch.logo=config.get("logo")
                    branch.save(update_fields=[
                        "name","logo",
                        "device_id", "serial", "production",
                        "keystore", "password",
                        "private_key", "certificate", "base_url","public_key"
                    ])
                    print(f"Branch {branch_name} updated")
                else:
                    print(f"No config found for branch {branch_name}")
            except Exception as e:
                print(f"Error initializing branch {branch_name}: {e}")


# Global lock to prevent concurrent processing threads
@receiver(post_save, sender=FiscalReceipt)
@receiver(post_save, sender=FiscalCredit)
@receiver(post_save, sender=FiscalDebit)
def handle_fiscal_receipt_or_credit(sender, instance, created, **kwargs):
    print("fiscal_receipt_post")
    print(instance.signature)
    if instance.submited:
        return  # Only act on new unsubmitted instances
    if instance.signature is None:
        return  # Cannot process without a signature
    branch = instance.fiscal_branch
    print("This is an impoerANT ARE")
    if branch.name not in processing_locks:
        processing_locks[branch.name] = threading.Lock()
    if branch.name not in processing_threads or not processing_threads[branch.name].is_alive():
            thread = threading.Thread(target=process_unsubmitted_receipts_or_credits, args=(branch,))
            processing_threads[branch.name] = thread
            thread.start()
    # Get or create daily report
    openday = OpenDay.objects.filter(open=True, branch=branch).last()
    daily_report, _ = DailyReports.objects.get_or_create(FiscalDay=openday)

    # Get or create currency
    currency, _ = Currency.objects.get_or_create(symbol=instance.currency.symbol)

   
    multiplier = -1 if sender.__name__ == "FiscalCredit" else 1
    # Add Sale or Credit Note entries
    def add_entry(report_type, tax_percent, value, money_type=None):
        if value < 0.01:
            return
        entry, _ = FiscalReportEntry.objects.get_or_create(
            daily_report=daily_report,
            currency=currency,
            report_type=report_type,
            tax_percent=tax_percent,
            money_type=money_type,
            fiscal=True,
            defaults={"value": 0},
        )
        entry.value += Decimal(value) * multiplier
        entry.save()
    def add_counter(counter_type):
        
        counter, _ = ReceiptCounters.objects.get_or_create(
           
            currency=currency,
            type=counter_type,
            day=openday,
        )
        counter.value += 1
        counter.save()
    
    # Balance by payment method
    mobile_methods = ["Ecocash", "OneMoney", "InnBucks", "Mukuru", "Telecash"]
    if instance.payment_method == "Cash":
        money_type = "Cash"
    elif instance.payment_method in mobile_methods:
        money_type = "MobileWallet"
    elif instance.payment_method in ["Card", "Swipe"]:
        money_type = "Card"
    elif instance.payment_method == "Coupon":
        money_type = "Coupon"
    elif instance.payment_method in ["Bank", "BankTranfer"]:
        money_type = "BankTransfer"
    else:
        money_type = "Other"
    
    if sender.__name__ == "FiscalCredit":
        # Credit Note amounts
        add_entry("CreditNoteByTax", "0.00", instance.TotalNonVAT)
        add_entry("CreditNoteByTax", "15.00", instance.Total15VAT)
        add_entry("CreditNoteByTax", "Exempt", instance.TotalExempt)  # Exempt has no tax
        add_entry("CreditNoteTaxByTax", "15.00", instance.tax)
        add_entry("BalanceByMoneyType", None, instance.total, money_type)
        add_counter(counter_type="CreditNote")
    elif sender.__name__ == "FiscalReceipt":  # Sale / Credit Note amounts
        add_entry("SaleByTax", "0.00", instance.TotalNonVAT)
        add_entry("SaleByTax", "15.00", instance.Total15VAT)
        add_entry("SaleByTax", "Exempt", instance.TotalExempt)  # Exempt has no tax
        add_entry("SaleTaxByTax", "15.00", instance.tax)
        add_entry("BalanceByMoneyType", None, instance.total, money_type)
        add_counter(counter_type="FiscalReceipt")
    elif sender.__name__ == "FiscalDebit":  # Sale / Credit Note amounts
        add_entry("DebitNoteByTax", "0.00", instance.TotalNonVAT)
        add_entry("DebitNoteByTax", "15.00", instance.Total15VAT)
        add_entry("DebitNoteByTax", "Exempt", instance.TotalExempt)  # Exempt has no tax
        add_entry("DebitNoteTaxByTax", "15.00", instance.tax)
        add_counter(counter_type="DebitNote")

def process_unsubmitted_receipts_or_credits(branch):
    if branch.name not in processing_locks:
        processing_locks[branch.name] = threading.Lock()
       
    if not processing_locks[branch.name].acquire(blocking=False):
        print("A processing thread is already running. Skipping new thread.")
        return

    try:
        # Load FDMS public key
        branch.public_key.seek(0)
        fdms_public_key = serialization.load_pem_public_key(
            branch.public_key.read(),
            backend=default_backend()
        )
        logging.info("FDMS public key loaded successfully.")

        # Query all unsubmitted receipts, credits, debits
        receipts_qs = FiscalReceipt.objects.filter(submited=False, fiscal_branch=branch).values(
            'id', 'receiptGlobalNo', 'receiptJsonbody', 'signature', 'pk', 'submited', 'fiscal_branch_id'
        )
        credits_qs = FiscalCredit.objects.filter(submited=False, fiscal_branch=branch).values(
            'id', 'receiptGlobalNo', 'receiptJsonbody', 'signature', 'pk', 'submited', 'fiscal_branch_id'
        )
        debits_qs = FiscalDebit.objects.filter(submited=False, fiscal_branch=branch).values(
            'id', 'receiptGlobalNo', 'receiptJsonbody', 'signature', 'pk', 'submited', 'fiscal_branch_id'
        )

        # Combine all and order by receiptGlobalNo
        combined_qs = receipts_qs.union(credits_qs, debits_qs).order_by('receiptGlobalNo')

        for item in combined_qs:
            # Fetch full instance to handle save() and related fields
            if FiscalCredit.objects.filter(pk=item['pk']).exists():
                receipt_instance = FiscalCredit.objects.get(pk=item['pk'])
            elif FiscalDebit.objects.filter(pk=item['pk']).exists():
                receipt_instance = FiscalDebit.objects.get(pk=item['pk'])
            else:
                receipt_instance = FiscalReceipt.objects.get(pk=item['pk'])

            try:
                print(f"Submitting {receipt_instance.__class__.__name__} #{receipt_instance.id}")
                response = submit_receipt(
                    base_url=branch.base_url,
                    certificate_path=branch.certificate.path,
                    private_path=branch.private_key.path,
                    data=receipt_instance.receiptJsonbody
                )
                response_json = json.loads(response.decode("utf-8"))
                receipt_instance.serverResponse = response.decode("utf-8")

                # Validation errors
                errors = response_json.get("validationErrors", [])
                codes = [err["validationErrorCode"] for err in errors]
                receipt_errors = ReceiptError.objects.filter(code__in=codes)
                receipt_instance.errors.set(receipt_errors)

                # FDMS signature verification
                signature_b64 = response_json["receiptServerSignature"]["signature"]
                signature = base64.b64decode(signature_b64)
                hash_input = (
                    str(receipt_instance.signature) +
                    str(response_json["receiptID"]) +
                    str(response_json["serverDate"])
                )
                digest = hashes.Hash(hashes.SHA256())
                digest.update(hash_input.encode("utf-8"))
                computed_hash = digest.finalize()

                try:
                    fdms_public_key.verify(
                        signature,
                        computed_hash,
                        padding.PKCS1v15(),
                        hashes.SHA256()
                    )
                    print(f"{receipt_instance.__class__.__name__} #{receipt_instance.id} signature verified")
                    receipt_instance.verified = True
                except Exception as e:
                    print(f"{receipt_instance.__class__.__name__} #{receipt_instance.id} INVALID signature: {e}")
                    receipt_instance.verified = False
                from django.utils import timezone
                receipt_instance.verified_at = timezone.now()
                receipt_instance.submited = True
                receipt_instance.save()

                time.sleep(0.1)

            except Exception as e:
                logging.info(f"Error submitting {receipt_instance.__class__.__name__}: {e}")
                import traceback
                traceback.print_exc()
                break
    except Exception as e:
        logging.error(str(e))
    finally:
        print("Processing complete. Releasing lock.")
        processing_locks[branch.name].release()




@csrf_exempt
def submitAll(request=None,branch=None):
    if not request is None:
        branch=FiscalBranch.objects.get(id=request.session["branch"])
    global processing_thread
    processing_thread = threading.Thread(
        target=process_unsubmitted_receipts_or_credits,
        args=(branch,),  # must be a tuple
        daemon=True
    )
    processing_thread.start()

    return JsonResponse({'status': f'Processing started for branch {branch.name}'})
