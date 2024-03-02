from django.urls import path

from . import views

from meals.views import MealHistoryView, DishCreateView, \
    MealCreateView

app_name = "meals"
urlpatterns = [
    path("", views.index, name="index"),
    path("search/", views.search, name="search"),
    path("history/<int:pk>/", MealHistoryView.as_view(), name="history"),
    path("history/updated/<int:pk>/", MealHistoryView.as_view(), {"showform": False}, name="history-noform"),
    path("add/", views.add_dish, name="add"),
    path("add/<str:initial>", views.add_dish, name="add"),
    path("addmeal/", MealCreateView.as_view(), name="addmeal"),
]
