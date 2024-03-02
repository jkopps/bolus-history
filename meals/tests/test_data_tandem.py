from django.test import TestCase

import json
import os

from meals.models import GlucoseMeasurement, InsulinDelivery
from meals import tconnectdata




class TConnectTestClass(TestCase):
    @classmethod
    def testfilename(cls):
        return os.path.join(os.path.dirname(__file__),
                            "tandem_20240108_20240114_sanitized.json")
    
    @classmethod
    def setUpTestData(cls):
        with open(cls.testfilename()) as fp:
            data = json.load(fp)
        tconnectdata.commit(data)

    def test_json_commit(self):
        numBolusEvents = len(InsulinDelivery.objects.all())
        self.assertEqual(numBolusEvents, 72)
        numCGMEvents = len(GlucoseMeasurement.objects.all())
        self.assertEqual(numCGMEvents, 1987)

    def test_rejects_duplicates(self):
        numBolusEvents_before = len(InsulinDelivery.objects.all())
        with open(self.testfilename()) as fp:
            data = json.load(fp)
        tconnectdata.commit(data)
        numBolusEvents_after = len(InsulinDelivery.objects.all())
        self.assertEqual(numBolusEvents_before, numBolusEvents_after)
