from datetime import datetime
import logging
import os
import tempfile

from astropy.io import fits
from django.conf import settings
from django.core.files import File
from django.db import models
from django.core.exceptions import ValidationError
from fits2image.conversions import fits_to_jpg
from PIL import Image

from tom_targets.models import Target
from tom_alerts.models import AlertStreamMessage
from tom_observations.models import ObservationRecord

# Create your models here.

class QueryModel(models.Model):

    MJD = models.FloatField()

    def __str__(self):
        return self.title