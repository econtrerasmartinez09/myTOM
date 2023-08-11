import mimetypes

from django.conf import settings
from importlib import import_module

from tom_dataproducts.models import ReducedDatum
from tom_targets.models import Target

from astropy import units
from astropy.io import ascii
from astropy.time import Time, TimezoneInfo
from datetime import datetime
import numpy as np

from tom_dataproducts.data_processor import DataProcessor
from tom_dataproducts.exceptions import InvalidFileFormatException

DEFAULT_DATA_PROCESSOR_CLASS = 'atlas_app.data_processor.MyDataProcessor'

def run_data_processor(dp, target):
    try:
        processor_class = settings.DATA_PROCESSORS[dp.data_product_type]   # custom data processor is accepted
    except Exception:
        processor_class = DEFAULT_DATA_PROCESSOR_CLASS
    try:
        mod_name, class_name = processor_class.rsplit('.', 1)
        mod = import_module(mod_name)
        clazz = getattr(mod, class_name)
    except (ImportError, AttributeError):
        raise ImportError('Could not import {}. Did you provide the correct path?'.format(processor_class))  #

    data_processor = clazz()

    # use a try/except wrap around this entire section for true/false values for test_dataprocessor
    try:
        reduced_datums = []

        for item in dp[1:]:
            t = Time(item[0], format='mjd', scale='utc')
            mjd = {'timestamp': t.iso}
            values = {'magnitude': item[1],
                      'magnitude_error': item[2],
                      'filter': item[3]}

            datum = ReducedDatum(target = target, data_type = 'photometry',
                                      timestamp = mjd['timestamp'], value = values)

            reduced_datums.append(datum)

        ReducedDatum.objects.bulk_create(reduced_datums)

        return True

    except RuntimeError:
        return False

class MyDataProcessor(DataProcessor):

    FITS_MIMETYPES = ['image/fits', 'application/fits']
    PLAINTEXT_MIMETYPES = ['text/plain', 'text/csv']

    mimetypes.add_type('image/fits', '.fits')
    mimetypes.add_type('image/fits', '.fz')
    mimetypes.add_type('application/fits', '.fits')
    mimetypes.add_type('application/fits', '.fz')
    mimetypes.add_type('application/json', '.json')
