from rest_framework import serializers
from .models import FiscalReceipt,FiscalCredit,FiscalDebit
from pos.serializers import ReceiptSerializer

class FiscalReceiptSerializer(ReceiptSerializer):
    day = serializers.PrimaryKeyRelatedField(read_only=True, required=False)
    fiscal_branch = serializers.PrimaryKeyRelatedField(read_only=True, required=False)
    errors = serializers.PrimaryKeyRelatedField(many=True, read_only=True, required=False)

    class Meta(ReceiptSerializer.Meta):
        model = FiscalReceipt
        fields = ReceiptSerializer.Meta.fields + [
            "qrurl", "receiptJsonbody", "receiptHash", "signature",
            "submited", "serverResponse", "md5_hash", "receiptGlobalNo",
            "receiptCounter", "result_string", "fiscal_branch", "errors",
            "day", "verified", "verified_at",
        ]

        
class FiscalCreditSerializer(FiscalReceiptSerializer):
    class Meta(FiscalReceiptSerializer.Meta):
        model = FiscalCredit
        fields = FiscalReceiptSerializer.Meta.fields + [
            
            "reason",
        ]
class FiscalDebitSerializer(FiscalReceiptSerializer):
    class Meta(FiscalReceiptSerializer.Meta):
        model = FiscalDebit
        fields = FiscalReceiptSerializer.Meta.fields + [
            
            "reason",
        ]