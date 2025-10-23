
PERMISSION_MAP = {
  
    "/create_user/": "main.add_user",
    "/user_list/": "main.view_user",

    # Currency
    "/currency_list/": "pos.view_currency",
    "/add_currency/": "pos.add_currency",
    "/update_currency/": "pos.change_currency",
   
    # Company
    "/company_list/": "pos.view_company",
    "/update_company/": "pos.change_company",
    "/update_logo/":"pos.change_branch",
    # Branch
    "/branch_list/": None,
    
    #fiscalization
    "get_config_view/":"pos.add_receipt",
    "open_day_view/":"pos.add_receipt",
    "close_day_view/":"pos.add_receipt",
    "get_status_view/":"pos.add_receipt",

    # Supplier
    "/supplier_list/": "pos.view_supplier",
    "/add_supplier/": "pos.add_supplier",
    "/update_supplier/": "pos.change_supplier",

    # Customer
    "/customer_list/": "pos.view_customer",
    "/add_customer/": "pos.add_customer",
    "/update_customer/": "pos.change_customer",

    # Product
    "/product_list/": "pos.view_product",
    "/update_product/": "pos.change_product",
    "/delete_product/": "pos.delete_product",
    "/break_pack/": "pos.add_product",
    
    # Receipts
    "/receipt_list/": "pos.view_receipt",
    "/make_sale/": "pos.add_receipt",
    "/make_fiscal_sale/": "pos.add_receipt",
    "/credit_fiscal_sale/": "pos.add_credit",
    "/debit_fiscal_sale/": "pos.add_debit",
    "/preview_sale/": "pos.view_receipt",

    # Quotation
    "/quotation_list/": "pos.view_quotation",
    "/quotation_sale/": "pos.add_quotation",

    # Stock & Services
    "/add_service/": "pos.add_service",
    "/add_nonservice/": "pos.add_nonservice",

    # Reprint / Other
    "/reprint_invoice/": "pos.view_receipt",
    "/reprint_quotation/": "pos.view_quotation",
    "/reprint_debit/": "pos.view_debit",
    "/reprint_credit/": "pos.view_credit",
}
