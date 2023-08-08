import os
from http import HTTPStatus
import tempfile

from astropy import units
from astropy.io import fits
from astropy.table import Table
from datetime import date, time

from django.test import TestCase, override_settings
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from guardian.shortcuts import assign_perm

import numpy as np
from faker import Faker

from specutils import Spectrum1D

from unittest.mock import patch

from tom_dataproducts.exceptions import InvalidFileFormatException
from tom_dataproducts.forms import DataProductUploadForm
from tom_dataproducts.models import DataProduct, is_fits_image_file
from tom_dataproducts.processors.data_serializers import SpectrumSerializer
from tom_dataproducts.processors.photometry_processor import PhotometryProcessor
from tom_dataproducts.processors.spectroscopy_processor import SpectroscopyProcessor
from tom_dataproducts.utils import create_image_dataproduct
from tom_observations.tests.utils import FakeRoboticFacility
from tom_targets.models import Target
from tom_observations.tests.factories import SiderealTargetFactory, ObservingRecordFactory

from atlas_app.data_processor import run_data_processor



class TestDataProcessor(TestCase):
    def setUp(self):
        fake = Faker()

        self.fake_data = []

        self.fake_data.append(['MJD', 'm', 'dm', 'F'])

        # setting up a fake list of list of MJD, mag, mag_err, and filter_codes
        for i in range(len(rand.int(500,1000))):

            mjd = str(fake.pyfloat(min_value = 56000, max_value = 59000))
            mag = fake.pyfloat(min_value = 0, max_value = 25)
            mag_err = fake.pyfloat(min_value = 0, max_value = 10)

            filter_ltr = ['c', 'o']
            filter = filter_ltr[random.randint(0,1)]

            self.fake_data.append([mjd, mag, mag_err, filter])


        self.target = SiderealTargetFactory.create()

    def test_dataprocessor_pass(self):
        firstval = run_data_processor(self.fake_data, self.target)

        message = 'Data processor test was a success!'

        self.assertEqual(firstval,True,message)   # check if first val returned a data frame (i.e. True)

    #def test_dataprocessor_fail(self):
    #   firstval = run_data_processor(self.fake_data, self.target)

    #    message = 'Data processor test was not sucessful.'

    #    self.assertEqual(firstval, False, message)
