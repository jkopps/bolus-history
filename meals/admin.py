from django.contrib import admin
from .models import Dish, Meal, InsulinDelivery, GlucoseMeasurement

admin.site.register(Dish)
admin.site.register(Meal)
admin.site.register(InsulinDelivery)
admin.site.register(GlucoseMeasurement)


