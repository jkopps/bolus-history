from django.test import TestCase
from django.db import transaction, IntegrityError

from datetime import datetime, timedelta
from math import sin, pi
import os
import random

from meals.models import GlucoseMeasurement, InsulinDelivery

class GlucoseMeasurementTestClass(TestCase):
    @classmethod
    def sampledata(cls, i):
        """
        :param cls: class member
        :param i: Sample index; increment is 5 minutes
        """
        dt = datetime(2000, 1, 1, 12, 0) + timedelta(minutes=i*5)
        val= round(100 + 30*sin(float(i)*2*pi/25))
        return dt, val
    
    @classmethod
    def setUpTestData(cls):
        # Test data:
        inds = list(range(500))
        random.shuffle(inds)
        for i in inds:
            dt, val = cls.sampledata(i)
            record = GlucoseMeasurement(when=dt, value=val)
            record.save()

    def test_rejects_duplicates(self):
        x = GlucoseMeasurement.objects.all()[0]
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                record = GlucoseMeasurement(when=x.when, value=x.value)
                record.save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                record = GlucoseMeasurement(when=x.when, value=x.value + 10)
                record.save()

    def test_filter_by_date(self):
        i = 110
        before=2
        after=3
        t = self.sampledata(i)[0] + timedelta(minutes=-2)
        data = GlucoseMeasurement.getEventsInWindow(t, pre=before, post=after)

        nsamples = int((before+after)*60/5)        
        t0 = t + timedelta(hours = -1*before)
        t1 = t + timedelta(hours = after)
        i0 = int(i - before*60/5)
        i1 = int(i + after*60/5 - 1)

        # check filtering        
        self.assertEqual(len(data), nsamples)
        for record in data:
            self.assertTrue(record.when >= t0)
            self.assertTrue(record.when <= t1)
        self.assertEqual(data[0].value, self.sampledata(i0)[1])
        self.assertEqual(data[nsamples-1].value, self.sampledata(i1)[1])

        # check ordering
        for j in range(len(data) - 1):
            self.assertTrue(data[j].when <= data[j+1].when)
