import mimetypes

from django.conf import settings
from importlib import import_module

from tom_dataproducts.models import ReducedDatum
from tom_targets.models import Target

DEFAULT_DATA_PROCESSOR_CLASS = '.data_processor.DataProcessor'

def run_data_processor(dp):
    try:
        processor_class = settings.DATA_PROCESSORS[dp.data_product_type]  # need to resolve settings, reduceddatum,
    except Exception:
        processor_class = DEFAULT_DATA_PROCESSOR_CLASS

    try:
        mod_name, class_name = processor_class.rsplit('.', 1)
        mod = import_modele(mod_name)
        clazz = getattr(mod, class_name)
    except (ImportError, AttributeError):
        raise ImportError('Could not import {}. Did you provide the correct path?'.format(processor_class))


    data_processor = clazz()
    data = data_processor.process_data(dp)

    reduced_datums = [ReducedDatum(target = dp.target, data_product = dp, data_type = dp.data_product_type,
                                   mjd = datum[0], mag = datum[1], mag_err = datum[2], filter = datum[5]) for datum in data]

    ReducedDatum.objects.bulk_create(reduced_datums)

    return ReducedDatum.objects.filter(data_product=dp)

class DataProcessor():

    FITS_MIMETYPES = ['image/fits', 'application/fits']
    PLAINTEXT_MIMETYPES = ['text/plain', 'text/csv']

    mimetypes.add_type('image/fits', '.fits')
    mimetypes.add_type('image/fits', '.fz')
    mimetypes.add_type('application/fits', '.fits')
    mimetypes.add_type('application/fits', '.fz')
    mimetypes.add_type('application/json', '.json')   # appropriate date type file for 'text data'

    def process_data(self, data_product):
        return []