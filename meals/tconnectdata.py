from django.db import IntegrityError, transaction

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
import re
import sys
from typing import Callable

import arrow

from tconnectsync.api import TConnectApi
from tconnectsync.domain import therapy_event
from tconnectsync.parser.tconnect import TConnectEntry

import logging
logger = logging.getLogger(__name__)

@dataclass
class TconnectLogin:
    email: str
    password: str
    sn: int

    def __str__(self):
        return "(%s, *******, *******)" % self.email

def getLogin():
    logger.info("Looking for TCONNECT login info environment variables...")
    email = os.environ.get("TCONNECT_EMAIL")
    password = os.environ.get("TCONNECT_PASSWORD")
    sn = os.environ.get("TCONNECT_SERIAL_NUMBER")

    fail = False
    if not email:
        logger.warning("Missing login email (TCONNECT_EMAIL)")
        fail = True
    if not password:
        logger.warning("Missing login password (TCONNECT_PASSWORD)")
        fail = True
    if not sn:
        logger.warning("Missing t:slim serial number (TCONNECT_SERIAL_NUMBER)")
        fail = True

    if sn:
        try:
            sn = int(sn)
        except ValueError as err:
            logger.warning("Could not interpret s:slim serial number as int")
            fail = True
    
    if fail:
        return None

    logger.info("Located TCONNECT login info environment variables")    
    return TconnectLogin(email, password, sn)
    

def getTandemData(login, time_start, time_end, allsources=False):
    """Retrieve CGM and insulin event data from Tandem

    :param email: t:connect account login email
    :param password: t:connect account login password
    :param sn: Serial number for associated t:slim pump
    :param allsources: Retrieve data sources not used in app models
    :returns: dict of tconnect API query types and results
    """
    tconnect = TConnectApi(login.email,login.password)

    @dataclass
    class DataQuery:
        key: str
        get: Callable
        desc: str
        used: bool

    queries = (DataQuery("ciqSummary",
                         tconnect.controliq.dashboard_summary,
                         "ControlIQ dashboard summary",
                         False),
               DataQuery("ciqTimeline",
                         tconnect.controliq.therapy_timeline,
                         "ControlIQ therapy timeline",
                         False),
               DataQuery("ciqEvents",
                         tconnect.controliq.therapy_events,
                         "ControlIQ event history",
                         True),
               DataQuery("biqSummary",
                         tconnect.ws2.basaliqtech,
                         "BasalIQ summary",
                         False),
               DataQuery("csvTimeline",
                         tconnect.ws2.therapy_timeline_csv,
                         "WS2 timeline CSV",
                         False),
               )

    data = {}

    for q in filter(lambda x: x.used or allsources, queries):
        try:
            logger.info("Querying for %s" % q.desc)
            _data = q.get(time_start, time_end)
            data[q.key] = _data
        except Exception as err:
            logger.error("Error querying for %s: %s" % (q.desc, err))
            
    return data

def parseTime(timestring):
    # t:slim clock is not timezone aware
    # We'll assume user changes the pump's time for Daylight Savings
    # or travel across time zones, so we won't try to insert a timezone
    m = re.match("^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})([.]\d+)?$",
                         timestring)
    if m == None:       
        return None

    return datetime.strptime(m.groups()[0], "%Y-%m-%dT%H:%M:%S")

def commit(data):
    """Import Tandem data to app models

    data: json-formatted as returned by getTandemData
    """

    import django
    django.setup()
    from django.conf import settings
    from meals.models import GlucoseMeasurement, InsulinDelivery
    
    accepted = {}
    discarded = {}

    for event in map(TConnectEntry.parse_therapy_event,
                     data["ciqEvents"]["event"]):

        t = parseTime(event.eventDateTime)
        if not t:
            logger.error("Ignoring unexpected time format: %s" %
                         event.eventDateTime)
            continue
        
        if event.type == "CGM":
            logger.debug("Adding CGM record: %s - %s" % (t, event.egv))
            record = GlucoseMeasurement(
                when = t,
                value = event.egv,
            )
        elif event.type == "Bolus":
            logger.debug("Adding Bolus record: %s - %s" % (t, event.insulin))
            if event.extended_bolus:
                logger.warning("Discarding extended bolus duration data")
            record = InsulinDelivery(
                when = t,
                amount = event.insulin,
            )
        else:
            discarded[event.type] = discarded.get(event.type, 0) + 1
            continue

        try:
            with transaction.atomic():
                record.save()
                accepted[event.type] = accepted.get(event.type, 0) + 1
        except IntegrityError:
            discarded[event.type] = discarded.get(event.type, 0) + 1
            rec0 = record.__class__.objects.get(when=record.when)
            duplicate = True
            for f in filter(lambda x: x.auto_created == False,
                            rec0._meta.get_fields()):
                duplicate = (duplicate and
                             (getattr(rec0, f.name) == getattr(record, f.name)))
            if duplicate:
                logger.info("Ignoring duplicate entry")
            else:
                logger.warning(
                    "Ignoring collision in %s: exists %s; rejecting %s"
                    % (record.__class__, rec0, record)
                    )
        except Exception as err:
            import sys
            sys.stderr.write("Unexpected exception type: %s" % err.__class__)

    for (k, v) in accepted.items():
        logger.info("Parsed %d records of type %s" % (v, k))
    for (k, v) in discarded.items():
        logger.warning("Discarded %d records of type %s" % (v, k))

    

if __name__ == "__main__":

    sys.path.append(os.path.join(os.path.dirname(__file__), os.path.pardir))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bolushistory.settings")

    import argparse
    parser = argparse.ArgumentParser(
        description="Download CGM and bolus data from Tandem")
    parser.add_argument("--start", dest="start",
                        help="Start of date range to retrieve")
    parser.add_argument("--end", dest="end",
                        help="End of date range to retrieve; defaults to today")
    parser.add_argument("--days", dest="days", type=int,
                        help="Number of days to retrieve")
    parser.add_argument("--out", dest="outfile",
                        help="File to write JSON output")
    parser.add_argument("--commit", dest="commit", type=bool, default=False,
                        help="Commit retrieved data to database")

    args = parser.parse_args()

    if args.days and args.days <= 0:
        parser.error("--days value must be greater than 0")
    
    if args.start:
        if args.end and args.days:
            parser.error("May specify only two from (--start, --end, --days)")
        start_date = arrow.get(args.start).floor('day')
        if start_date > arrow.now():
            parser.error("--start date may not be in the future")
        if args.days:
            end_date = start_date.shift(days=args.days)
        elif args.end:
            end_date = arrow.get(args.end)
            if end_date < start_date:
                parser.error("--end date must be later than --start date")
        else:
            end_date = arrow.now()
    elif args.days:
        if args.end:
            end_date = arrow.get(args.end)
        else:
            end_date = arrow.now()
        start_date = end_date.shift(days=-args.days).floor('day')
    else:
        parser.error("Must specify at least one from (--start, --days)")

    assert(start_date < end_date)
    logger.warning("Using date range %s to %s" % (start_date, end_date))

    login = getLogin()

    if not login:
        sys.stderr.write("Missing login credentials - aborting")
        sys.exit(1)

    allsources = (args.outfile != None)
        
    data = getTandemData(login, start_date, end_date, allsources)

    if args.outfile:
        logger.info("Writing retrieved Tandem data to file %s" % args.outfile)
        with open(args.outfile, "w") as fp:
            json.dump(data, fp)

    if args.commit:
        logger.info("Committing retrieved Tandem data to databases")
        commit(data)
