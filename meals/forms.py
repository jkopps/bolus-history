from django import forms

from .models import Dish, Meal

class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"

class DateTimeLocalField(forms.DateTimeField):
    input_formats = [
        "%Y-%m-%dT%H:%M:%S", 
        "%Y-%m-%dT%H:%M:%S.%f", 
        "%Y-%m-%dT%H:%M",
    ]
    widget = DateTimeLocalInput(format="%Y-%m-%dT%H:%M")

class SearchForm(forms.Form):
    desc = forms.CharField(label="Dish",
                           max_length = Dish.desc.field.max_length,
                           # widget=forms.Select,
                           # choices=Dish.objects.all()
                           )

class DishForm(forms.ModelForm):
    class Meta:
        model = Dish
        fields = ["desc"]

class MealForm(forms.ModelForm):
    class Meta:
        model = Meal
        fields = "__all__"
    date = DateTimeLocalField()
