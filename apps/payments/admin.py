from django.contrib import admin

from .models import AdvanceDeduction, CreditPayment, Payment, PaymentDeduction

admin.site.register(Payment)
admin.site.register(PaymentDeduction)
admin.site.register(AdvanceDeduction)
admin.site.register(CreditPayment)
