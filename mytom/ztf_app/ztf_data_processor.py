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


def run_data_processor(dp):

    try:
        processor_class = settings.DATA_PROCESSORS[dp.data_product_type]
    except Exception:
        processor_class = DEFAULT_DATA_PROCESSOR_CLASS
    try:
        mod_name, class_name = processor_class.rsplit('.', 1)
        mod = import_module(mod_name)
        clazz = getattr(mod, class_name)
    except (ImportError, AttributeError):
        raise ImportError('Could not import {}. Did you provide the correct path?'.format(processor_class))

    data_processor = clazz()
    data = data_processor.process_data(dp)   # MAIN FUNC, returns variables time and data
    try:

        target = Target.objects.filter(target = dp.target)

        reduced_datums = [ReducedDatum(target=target, data_product = dp, data_type='photometry',
                             timestamp=datum[0], value=datum[1], source_name = datum[2]) for datum in data]

        ReducedDatum.objects.bulk_create(reduced_datums)

        return ReducedDatum.objects.filter(data_product=dp)

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
        Routes a photometry processing call to a method specific to a file-format.

        :param data_product: Photometric DataProduct which will be processed into the specified format for database
        ingestion
        :type data_product: DataProduct

        :returns: python list of 2-tuples, each with a timestamp and corresponding data
        :rtype: list
        """

        mimetype = mimetypes.guess_type(data_product.data.path)[0]
        if mimetype in self.PLAINTEXT_MIMETYPES:
            photometry = self._process_photometry_from_plaintext(data_product)   # should this be where all data reduction occurs from text file
            return [(datum.pop('timestamp'), datum, datum.pop('source', 'ZTF')) for datum in photometry]
        else:
            raise InvalidFileFormatException('Unsupported file type')

    def _process_photometry_from_plaintext(self, data_product):
        """
        Processes the photometric data from a plaintext file into a list of dicts. File is read using astropy as
        specified in the below documentation. The file is expected to be a multi-column delimited file, with headers for
        time, magnitude, filter, and error.
        # http://docs.astropy.org/en/stable/io/ascii/read.html

        :param data_product: Photometric DataProduct which will be processed into a list of dicts
        :type data_product: DataProduct

        :returns: python list containing the photometric data from the DataProduct
        :rtype: list
        """

        fin = open(data_product.data.path, 'rt')

        JD = []
        filter = []

        flux = []
        flux_err = []
        zpdiff = []
        diffmaglim = []

        for index, line in enumerate(fin):  # dp is the text file
            entries = line.replace("\n", "").split()

            if index > 55:  # index at start of actual and onwards

                for idx, x in enumerate(entries):
                    if idx == 4:
                        filter.append(str(x))  # filter code + JD == string
                    elif idx == 22:
                        JD.append(str(x))
                    elif idx == 19 or idx == 20 or idx == 24 or idx == 25:
                        if idx == 19:
                            diffmaglim.append(float(x))  # diffmaglim
                        elif idx == 20:
                            zpdiff.append(float(x))  # zpdiff
                        elif idx == 24:
                            flux.append(float(x))  # forcediffimflux
                        elif idx == 25:
                            flux_err.append(float(x))  # forcediffimfluxunc (i.e. uncertainty)

        mag = [i - 2.5 * np.log10(j) for i, j in zip(zpdiff, flux)]
        mag_err = [(2.5 / np.log(10.0)) * i / j for i, j in zip(flux_err, flux)]  # mag_err

        final_mag = [j if i > j or np.isnan(i) else i for i, j in zip(mag, diffmaglim)]  # final mag

        photometry = []

        for i in range(len(JD)):

            t = Time(float(JD[i]), format='jd')
            utc = TimezoneInfo(utc_offset=0*units.hour)
            t.format = 'datetime'
        #    time.append(t.to_datetime(timezone=utc))
            value = {
                'timestamp': t.to_datetime(timezone=utc),
            }
            for x in range(len(final_mag)):
                value['magnitude'] = final_mag[i]
                value['error'] = mag_err[i]
                value['filter'] = filter[i]
            photometry.append(value)

        return photometry