from datetime import datetime, timedelta

from django import template
from django.conf import settings

register = template.Library()

@register.inclusion_tag('panstarrs_app/partials/panstarrs_photometry_buttons.html')   #indexed further back to tempaltes?
def panstarrs_photometry_buttons(target):
    return {'target': target}