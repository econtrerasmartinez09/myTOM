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

DEFAULT_DATA_PROCESSOR_CLASS = 'ztf_app.ztf_data_processor.MyDataProcessor'

def run_data_processor(dp, target):
    try:
        processor_class = settings.DATA_PROCESSORS[dp.data_product_type]
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

        ##################################

        data = []   # dp = raw text content; data = list containing final reduced data

        for index, line in enumerate(dp):   # dp is the text file
            entries = line.replace("\n", "").split()
            line_data = []

            if index > 54:  # index at start of actual and onwards

                for idx, x in enumerate(entries):
                    if index == 55:   # locate the headers of the file
                        # should only contain filter, diffmaglim, zpdiff, jd, forcediffimflux, forcediffimfluxunc as headers
                        if idx == 22 or idx == 4 or idx == 24 or idx == 25 or idx == 20 or idx == 19:
                            line_data.append(str(x))
                    elif idx == 4 or idx == 22:   # 
                        line_data.append(str(x))
                    elif idx == 24 or idx == 25 or idx == 19 or idx == 20:  # might need to change jd to str
                        line_data.append(float(x))

                data.append(line_data)

        del data[1]
        del data[-1]

        ###################################

        for item in dp[1:]:
            t = Time(item[3], format='jd',scale='utc')
            iso = {'timestamp': t.iso}
            values = {'magnitude':item[],
                      'magnitude_error': item[],
                      'filter': item[]}

            datum = ReducedDatum(target = target, data_type = 'photometry',
                                      timestamp = iso['timestamp'], value = values)

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

    def process_data(self, data_product):
        """
        Routes a photometry processing call to a method specific to a file-format. This method is expected to be
        implemented by any subclasses.

        :param data_product: DataProduct which will be processed into a list
        :type data_product: DataProduct

        :returns: python list of 2-tuples, each with a timestamp and corresponding data
        :rtype: list of 2-tuples
        """
        return []