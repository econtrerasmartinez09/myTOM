from datetime import datetime, timedelta

from django import template
from django.conf import settings

register = template.Library()

@register.inclusion_tag('atlas_app/partials/photometry_buttons.html')   #indexed further back to tempaltes?
def photometry_buttons(target):
    return {'target': target}
