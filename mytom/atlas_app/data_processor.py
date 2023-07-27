import mimetypes

from django.conf import settings
from importlib import import_module

from tom_dataproducts.models import ReducedDatum
from tom_targets.models import Target

from astropy import units
from astropy.io import ascii
from astropy.time import Time, TimezoneInfo
import numpy as np

from tom_dataproducts.data_processor import DataProcessor
from tom_dataproducts.exceptions import InvalidFileFormatException

DEFAULT_DATA_PROCESSOR_CLASS = '.data_processor.DataProcessor'

def run_data_processor(dp):
    try:
        processor_class = settings.DATA_PROCESSORS[dp.data_product_type]  # need to resolve settings, reduceddatum,
    except Exception:
        processor_class = DEFAULT_DATA_PROCESSOR_CLASS

    try:
        mod_name, class_name = processor_class.rsplit('.', 1)
        mod = import_module(mod_name)   # error right here
        clazz = getattr(mod, class_name)
    except (ImportError, AttributeError):
        raise ImportError('Could not import {}. Did you provide the correct path?'.format(processor_class))


    data_processor = clazz()
    data = data_processor.process_data(dp)   # dp is the dfresult (i.e. the outputted atlas data)
    # calls the process_data function in the 'MyDataProcessor' class

    reduced_datums = [ReducedDatum(target = dp.target, data_product = dp, data_type = dp.data_product_type,
                                   timestamp = datum[0], value = {"magnitude":datum['magnitude'], "magnitude_error":datum['magnitude_error'], "filter":datum['filter']}) for datum in data]

    # might have to fix the previous line (i.e. small for loop)

    ReducedDatum.objects.bulk_create(reduced_datums)

    return ReducedDatum.objects.filter(data_product=dp)

class MyDataProcessor(DataProcessor):

    FITS_MIMETYPES = ['image/fits', 'application/fits']
    PLAINTEXT_MIMETYPES = ['text/plain', 'text/csv']

    mimetypes.add_type('image/fits', '.fits')
    mimetypes.add_type('image/fits', '.fz')
    mimetypes.add_type('application/fits', '.fits')
    mimetypes.add_type('application/fits', '.fz')
    mimetypes.add_type('application/json', '.json')

    def process_data(self, data_product):
        # custom data processing here

        mimetypes = mimetypes.guess_type(data_product.data.path)[0]
        if mimetypes in self.PLAINTEXT_MIMETYPES:
            photometry = self._process_photometry_from_plaintext(data_product)
            return [(datum.pop('timestamp'), datum, datum.pop('source', '')) for datum in photometry]
        else:
            raise InvalidFileFormatException('Unsupported file type')

    def _process_photometry_from_plaintext(self,data_product):
        photometry = []

        data = ascii.read(data_product.data.path)
        if len(data) < 1:
            raise InvalidFileFormatException('Empty table or invalid file type')

        for datum in data:
            time = Time(float(datum['time']), format='mjd')   # might have to set this to just mjd from form???
            utc = TimezoneInfo(utc_offset=0*units.hour)
            time.format = 'datetime'
            value = {
                'timestamp': time.to_datetime(timezone=utc),
            }
            for column_name in datum.colnames:
                if not np.ma.is_masked(datum[column_name]):
                    value[column_name] = datum[column_name]
                photometry.append(value)

        return photometry
