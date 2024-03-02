from django.db import models
from django.urls import reverse

from datetime import timedelta
from math import ceil, floor
from types import SimpleNamespace

import plotly.graph_objects as go
import numpy as np

import logging
logger = logging.getLogger(__name__)

class Dish(models.Model):
    desc = models.CharField(max_length=200, unique=True,
                            verbose_name="description")
    def __str__(self):
        return str(self.desc)

class Meal(models.Model):
    dish = models.ForeignKey('Dish', on_delete=models.PROTECT)
    when = models.DateTimeField("Time meal started")
    appx = models.BooleanField("Meal time is approximate", default=False)

    def __str__(self):
        return "%s: %s" % (self.when, self.dish.desc)

    def get_absolute_url(self):
        return reverse("meals:history", args=(self.dish.pk,))

    def has_egv_data(self):
        egvs = GlucoseMeasurement.getEventsInWindow(self.when)
        return len(egvs) > 0

    def plot_as_div(self):
        """Generate bolus and bg plot for time of meal
        """
        def format_dt(dt, tickval=None):
            """Format datetime according to django template 'D, N j, Y, P'

            Manually reproduce since strftime zero-pads all numbers
            """
            weekday = dt.strftime('%A')[0:3] # Day of week, 3-char abbr.
            month = dt.strftime('%b') # Month, 3-char abbr.
            day = int(dt.strftime('%d')) # Day, numeric, no padding
            year = dt.strftime('%Y') # Year, 4-digits
            hour = int(dt.strftime('%I')) # hour on 12-hour clock, no padding
            minutes = dt.strftime('%M') # minutes, 0 padded
            ampm = 'a.m.' if dt.hour < 12 else 'p.m.' # a.m. or p.m.

            if tickval == None:
                return '%s, %s. %s, %s, %s:%s %s' % (
                    weekday, month, day, year, hour, minutes, ampm
                )
            elif tickval == 0:
                return '%s:%s<br>%s' % (hour, minutes, ampm)
            else:
                return '%s:%s' % (hour, minutes)
        
        params = SimpleNamespace(
            
            meal_line = SimpleNamespace(
                color = 'purple',
                width = 4,
                opacity = 0.7
                ),
            
            bolus_line = SimpleNamespace(
                color = 'red',
            ),
            
            xaxis = SimpleNamespace(
                grid = SimpleNamespace(
                    dtickhours=1,
                    dtickstep=2,
                    color="white",
                    width=2,
                ),
                ticklabelstep=2,
                spikes = SimpleNamespace(
                    color = 'black',
                    dash = 'dot',
                    thickness = 2,
                ),
            ),
            
            yaxis = SimpleNamespace(
                range = SimpleNamespace(
                    min = 40,
                    max = 250,
                    step = 50,
                ),
                fillcolor0 = 'white',
                fillcolor1 = 'gray',
                stops = [0,70,90,140,180,200],
                title = 'EGV (mg/dL)'
            ),
        )
        
        egvs = GlucoseMeasurement.getEventsInWindow(self.when)
        bolus = InsulinDelivery.getEventsInWindow(self.when)

        if len(egvs) == 0:
            return None
        
        fig = go.Figure()
        
        t0 = min([r.when for r in egvs] + [r.when for r in bolus])
        
        # Convert all x values from dates to a numeric domain
        # as a workaround for bug
        # https://github.com/plotly/plotly.py/issues/3065
        # Solution suggested there (timestamp()*1000) does not work here
        # since dates are in naive (local) time and timestamp is in UTC
        xunit = timedelta(minutes=1)
        
        def dt_to_labeltext(dt):
            return dt.strftime('%I:%M')

        x1 = [int((r.when - t0)/xunit) for r in egvs]
        y1 = np.array([r.value for r in egvs])

        # Add cgm event data
        fig.add_trace(go.Scatter(
            x=x1,
            y=y1,
        ))

        # Add vertical line at mealtime
        if not self.appx:
            fig.add_vline(
                x=(self.when-t0)/xunit,
                line_width=params.meal_line.width,
                opacity=params.meal_line.opacity,
                line_color=params.meal_line.color,
            )

        # Add bolus event data as vertical lines
        # Make line weight proportional to bolus amount
        # @todo - If boluses are large, may want to scale to a max line weight
        for r in bolus:
            t = r.when
            # If same time as meal, dither by 90 seconds to reduce overlap
            # Dither to right of meal line since text will be right of bolus
            if r.when == self.when:
                t += timedelta(seconds=90)

            fig.add_vline(
                x=(t-t0)/xunit,
                line_width=ceil(r.amount),
                annotation_text = ("%.2f u" % r.amount),
                line_color=params.bolus_line.color,
            )

        # Adjust x-axis ticks relative to meal start
        tick0 = round((self.when-t0)/xunit)
        dtick = round(timedelta(hours=params.xaxis.grid.dtickhours)/xunit)
        fig.update_xaxes(
            tick0=tick0,
            dtick=dtick*params.xaxis.grid.dtickstep,
            gridwidth=params.xaxis.grid.width,
            gridcolor=params.xaxis.grid.color,
            minor_showgrid=True,
            minor_tick0=tick0,
            minor_dtick=dtick,
            minor_gridwidth=params.xaxis.grid.width,
            minor_gridcolor=params.xaxis.grid.color,
        )
        
        # Need an alias for each egv point (for spikeline hover display)
        #      and each tick mark (for x-axis labeling)
        xalias = [dt_to_labeltext(r.when) for r in egvs]
        xalias = dict(zip(x1, xalias))
        for i in range(tick0 % dtick, max(x1)+1, dtick):
            xalias[i] = dt_to_labeltext((i-tick0)*xunit + self.when)

        # Replace numeric x-axis indices with date (as string)
        fig.update_xaxes(labelalias = xalias)

        # Replace y-axis grid with shading of different regions of BG level
        stops = params.yaxis.stops
        
        fig.update_yaxes(showgrid=False)
        for i in range(len(stops)-1):
            fig.add_hrect(
                y0 = stops[i],
                y1 = stops[i+1],
                fillcolor = (
                    params.yaxis.fillcolor0 if (i%2) == 0
                    else params.yaxis.fillcolor1
                ),
                opacity = 0.2,
            )

        # Explicitly set y-axis height
        ymin = params.yaxis.range.min
        ymax = params.yaxis.range.max
        m = max(egvs, key=lambda r: r.value).value
        if m > ymax:
            ymax = ceil(m/params.yaxis.range.step)*params.yaxis.range.step
        
        fig.update_yaxes(range=(ymin,ymax))

        # Set title/label
        fig.update_layout(
            title_text = format_dt(self.when)
        )
        fig.update_yaxes(title_text = params.yaxis.title)

        # Adjust interaction to show spike top-to-bottom, following cursor x
        fig.update_layout(hovermode='x')
        fig.update_xaxes(
            showspikes=True,
            spikemode='across',
            spikethickness=params.xaxis.spikes.thickness,
            spikedash=params.xaxis.spikes.dash,
            spikecolor=params.xaxis.spikes.color,
        )
        
        return fig.to_html(
            include_plotlyjs="cdn",
            include_mathjax="cdn",
            full_html=False,
        )



class EventSeriesModel(models.Model):
    when = models.DateTimeField("Date/Time", unique=True)

    class Meta:
        abstract = True
        ordering = ["when"]

    @classmethod
    def getEventsInWindow(self, dt, pre=1, post=6):
        """Return values in a window around given date

        :param dt: datatime to anchor the window
        :param pre: Number of hours before dt to include
        :param post: Number of hours after dt to include
        :returns: Queryset of events in window
        """
        
        begin = dt - timedelta(hours=pre)
        end = dt + timedelta(hours=post)
        return self.objects.filter(when__gte=begin, when__lte=end)

    
class InsulinDelivery(EventSeriesModel):
    amount = models.DecimalField("Insulin units", max_digits=5, decimal_places=2)
    duration = models.DurationField("Duration", default=timedelta(0))

    def __str__(self):
        ret = "%s: %f units" % (self.when, self.amount)
        if self.duration != 0:
            ret = ret + " over %s" % self.duration
        return ret

class GlucoseMeasurement(EventSeriesModel):
    value = models.IntegerField()
    def __str__(self):
        return "%s: %s mg/dL" % (self.when, self.value)
