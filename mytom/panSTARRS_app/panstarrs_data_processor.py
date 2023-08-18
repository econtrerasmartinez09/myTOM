import mimetypes


from django.conf import settings
from importlib import import_module

from tom_dataproducts.models import ReducedDatum
from tom_targets.models import Target

from astropy import units
from astropy.io import ascii, fits
from astropy.time import Time, TimezoneInfo
from astropy.wcs import WCS
from specutils import Spectrum1D
from datetime import datetime

from tom_dataproducts.data_processor import DataProcessor
from tom_dataproducts.exceptions import InvalidFileFormatException
from tom_dataproducts.processors.data_serializers import SpectrumSerializer
from tom_observations.facility import get_service_class, get_service_classes

DEFAULT_DATA_PROCESSOR_CLASS = 'panSTARRS_app.panstarrs_data_processor.MyDataProcessor'

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
    data = data_processor.process_data(dp)   # calls for custom data processor

    try:

        target = Target.objects.filter(target = dp.target)

        reduced_datums = [ReducedDatum(target=target, data_product=dp, data_type='spectroscopy',
                                       timestamp=datum[0], value=datum[1], source_name=datum[2]) for datum in data]
        ReducedDatum.objects.bulk_create(reduced_datums)

        return ReducedDatum.objects.filter(data_product=dp)

    except RuntimeError:
        return False


class MyDataProcessor():

    FITS_MIMETYPES = ['image/fits', 'application/fits']
    PLAINTEXT_MIMETYPES = ['text/plain', 'text/csv']

    mimetypes.add_type('image/fits', '.fits')
    mimetypes.add_type('image/fits', '.fz')
    mimetypes.add_type('application/fits', '.fits')
    mimetypes.add_type('application/fits', '.fz')

    DEFAULT_WAVELENGTH_UNITS = units.angstrom
    DEFAULT_FLUX_CONSTANT = units.erg / units.cm ** 2 / units.second / units.angstrom

    def process_data(self, data_product):
        """
        Routes a spectroscopy processing call to a method specific to a file-format, then serializes the returned data.

        :param data_product: Spectroscopic DataProduct which will be processed into the specified format for database
        ingestion
        :type data_product: DataProduct

        :returns: python list of 2-tuples, each with a timestamp and corresponding data
        :rtype: list
        """

        mimetype = 'image/fits'
        print(f"this is the mimetype: {mimetype}")
        print("")
        print(f"this is our dataproduct: {data_product}")

        if mimetype in self.FITS_MIMETYPES:
            spectrum, obs_date = self._process_spectrum_from_fits(data_product)
        elif mimetype in self.PLAINTEXT_MIMETYPES:
            spectrum, obs_date = self._process_spectrum_from_plaintext(data_product)
        else:
            raise InvalidFileFormatException('Unsupported file type')

        print(f"the spectrum serializer is about to initiate!")

        serialized_spectrum = SpectrumSerializer().serialize(spectrum)

        return [(obs_date, serialized_spectrum)]

    def _process_spectrum_from_fits(self, data_product):
        """
        Processes the data from a spectrum from a fits file into a Spectrum1D object, which can then be serialized and
        stored as a ReducedDatum for further processing or display. File is read using specutils as specified in the
        below documentation.
        # https://specutils.readthedocs.io/en/doc-testing/specutils/read_fits.html

        :param data_product: Spectroscopic DataProduct which will be processed into a Spectrum1D
        :type data_product: tom_dataproducts.models.DataProduct

        :returns: Spectrum1D object containing the data from the DataProduct
        :rtype: specutils.Spectrum1D

        :returns: Datetime of observation, if it is in the header and the file is from a supported facility, current
            datetime otherwise
        :rtype: AstroPy.Time
        """

        flux = fits.getdata(data_product)
        header = fits.getheader(data_product)

        for facility_class in get_service_classes():
            facility = get_service_class(facility_class)()
            if facility.is_fits_facility(header):
                flux_constant = facility.get_flux_constant()
                date_obs = facility.get_date_obs_from_fits_header(header)
                break
        else:
            flux_constant = self.DEFAULT_FLUX_CONSTANT
            date_obs = datetime.now()

        dim = len(flux.shape)
        if dim == 3:
            flux = flux[0, 0, :]
        elif flux.shape[0] == 2:
            flux = flux[0, :]
        flux = flux * flux_constant

        header['CUNIT1'] = 'Angstrom'
        wcs = WCS(header=header, naxis=1)

        spectrum = Spectrum1D(flux=flux, wcs=wcs)

        return spectrum, Time(date_obs).to_datetime()

    def _process_spectrum_from_plaintext(self, data_product):   # this is not needed since file is fits file
        """
        Processes the data from a spectrum from a plaintext file into a Spectrum1D object, which can then be serialized
        and stored as a ReducedDatum for further processing or display. File is read using astropy as specified in
        the below documentation. The file is expected to be a multi-column delimited file, with headers for wavelength
        and flux. The file also requires comments containing, at minimum, 'DATE-OBS: [value]', where value is an
        Astropy Time module-readable date. It can optionally contain 'FACILITY: [value]', where the facility is a string
        matching the name of a valid facility in the TOM.
        # http://docs.astropy.org/en/stable/io/ascii/read.html

        Parameters
        ----------
        :param data_product: Spectroscopic DataProduct which will be processed into a Spectrum1D
        :type data_product: tom_dataproducts.models.DataProduct

        :returns: Spectrum1D object containing the data from the DataProduct
        :rtype: specutils.Spectrum1D

        :returns: Datetime of observation, if it is in the comments and the file is from a supported facility, current
            datetime otherwise
        :rtype: AstroPy.Time
        """

        data = ascii.read(data_product.data.path)
        if len(data) < 1:
            raise InvalidFileFormatException('Empty table or invalid file type')
        facility_name = None
        date_obs = datetime.now()
        comments = data.meta.get('comments', [])

        for comment in comments:
            if 'date-obs' in comment.lower():
                date_obs = comment.split(':')[1].strip()
            if 'facility' in comment.lower():
                facility_name = comment.split(':')[1].strip()

        facility = get_service_class(facility_name)() if facility_name else None
        wavelength_units = facility.get_wavelength_units() if facility else self.DEFAULT_WAVELENGTH_UNITS
        flux_constant = facility.get_flux_constant() if facility else self.DEFAULT_FLUX_CONSTANT

        spectral_axis = np.array(data['wavelength']) * wavelength_units
        flux = np.array(data['flux']) * flux_constant
        spectrum = Spectrum1D(flux=flux, spectral_axis=spectral_axis)

        return spectrum, Time(date_obs).to_datetime()