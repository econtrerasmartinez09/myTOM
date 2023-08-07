from datetime import datetime, timedelta

from django import template
from django.conf import settings

register = template.Library()

@register.inclusion_tag('ztf_app/partials/ztf_photometry_buttons.html')   #indexed further back to tempaltes?
def ztf_photometry_buttons(target):
    return {'target': target}