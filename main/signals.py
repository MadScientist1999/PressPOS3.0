from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from .models import User

@receiver(post_migrate)
def main_post_migrate(sender,**kwargs):
    # Create groups
    admin_group, _ = Group.objects.get_or_create(name="Admin")
    cashier_group, _ = Group.objects.get_or_create(name="Cashier")
    user, created = User.objects.get_or_create(
    username="Admin",
    defaults={
        "last_name": "",
        "first_name": "",
        "email": "admin@gmail.com",
        "is_staff": True,
        "is_active": True,
        "is_superuser": True,
        "role": "Admin"
    }
    )

    if created:
        user.set_password("Admin123")
        user.groups.add(admin_group)
        user.save()
        # Assign permissions
    
    admin_perms = Permission.objects.all()  # Admin has all perms
    admin_group.permissions.set(admin_perms)
    cashier_perms = Permission.objects.filter(
        codename__in=[
            "add_transaction", "change_transaction", "view_transaction",
            "add_customer", "change_customer", "view_customer",
            "add_product", "view_product",'add_customer','view_customer',
            'change_customer','delete_customer','add_currency','change_currency','delete_currency',
            'view_currency','add_product','change_product','add_quotation','change_quotation'
            ,'delete_quotation','view_quotation','add_credit','change_credit','delete_credit','view_credit',
            'add_debit','change_debit','delete_debit','view_debit','add_receipt','change_receipt','delete_receipt','view_receipt'
        ]
    )
    cashier_group.permissions.set(cashier_perms)