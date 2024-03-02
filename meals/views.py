from django.shortcuts import get_object_or_404, render, redirect
from django.views.generic import View, ListView, FormView
from django.views.generic.base import ContextMixin
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import CreateView
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import reverse, reverse_lazy

import logging
logger = logging.getLogger(__name__)

from meals.models import Dish, Meal
from meals.forms import DishForm, MealForm, SearchForm

# Dish select or Add -> Meal Add and History
# Meal Add and History -> Meal History
# Dish edit (or delete?)
# Meal edit or delete
# User settings and authorization

def index(request):
    logger.info("Hello, world")
    return HttpResponse("Hello, world")

class MealListView(ListView):
    template_name = "meals/history.html"
    model = Dish

    showform = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dish = get_object_or_404(Dish, pk=self.kwargs["pk"])
        # Display meals chronologically, most-recent first
        meal_set = Meal.objects.filter(dish=dish).order_by('when').reverse()
        context["dish"] = dish
        context["meal_set"] = meal_set
        context["form"] = MealForm()
        context["showform"] = self.showform
        return context

# @todo: Make the meal support multiple dishes
#        This would simplify future data entry for carb info, etc.
class MealFormView(SingleObjectMixin, FormView):
    template_name = "meals/history.html"
    form_class = MealForm
    model = Dish

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def get_success_url(self):
        return reverse("meals:history-noform", args=(self.object.pk,))

class MealHistoryView(ContextMixin, View):

    def get(self, request, *args, **kwargs):
        showform = kwargs.get("showform", True)
        view = MealListView.as_view(showform=showform)
        return view(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        view = MealFormView.as_view()
        return view(request, *args, **kwargs)

class DishCreateView(CreateView):
    model = Dish
    fields = ["desc"]

    def form_valid(self, form):
        self.object = form.save()
        return self.render_to_response(
            self.get_context_data(
                message="Added %s" % self.object.desc
                )
            )

class MealCreateView(CreateView):
    form_class = MealForm
    model = Meal

def add_dish(request, initial=None):
    logger.debug("views.add_dish()")

    if initial:
        logger.debug("Received initial arg = %s" % initial)
    else:
        logger.debug("Received no initial arg")

    if request.method == "POST":
        # first confirm it doesn't exist already
        form = SearchForm(request.POST)
        if form.is_valid():
            desc = form.cleaned_data["desc"]
            q = Dish.objects.filter(desc=desc)
            if len(q) != 0:
                logger.info("Duplicate create request - rendering history")
                obj = q[0]
                return HttpResponseRedirect(reverse("meals:history",
                                                    args=(obj.pk,)))
        # now try to create object
        form = DishForm(request.POST)
        if form.is_valid():
            desc = form.cleaned_data["desc"]
            logger.info("Received valid dish create request: %s" % desc)
            obj = form.save()
            return HttpResponseRedirect(reverse("meals:history",
                                                args=(obj.pk,)))

        else:
            # todo need to return errors
            return render(request,
                          "meals/dish_add.html")
                          
    else:
        return render(request,
                      "meals/dish_add.html",
                      { 'initial' : initial })

def search(request):
    logger.debug("views.search()")
    
    if request.method == "POST":
        form = SearchForm(request.POST)
        if form.is_valid():
            desc = form.cleaned_data["desc"]
            logger.info("Received request with data '%s'" % desc)
            q = Dish.objects.filter(desc=desc)
            if len(q) > 0:
                logger.info("Requested object exists - rendering history")
                obj = q[0]
                return HttpResponseRedirect(reverse("meals:history",
                                                    args=(obj.pk,)))
            else:
                logger.info("Requested object does not exist - rendering creator")              
                return HttpResponseRedirect(reverse('meals:add',
                                                    args=(desc,)))
        else:
            logger.info("Form invalid: %s" % form._errors)
            return render(request, 
                          "meals/search.html", 
                          {"error": "Error"}
                          )
    else:
        logger.debug("Initial render of meals/search")
        return render(request,
                      "meals/search.html",
                      { "object_list" : Dish.objects.all()}
                      )
