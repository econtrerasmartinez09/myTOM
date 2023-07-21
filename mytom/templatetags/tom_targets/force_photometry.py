from datetime import datetime, timedelta

from django import template
from django.conf import settings

register = template.Library()

@register.inclusion_tag('tom_targets/partials/photometry_buttons.html', takes_context=True)   #indexed further back to tempaltes?
def photometry_buttons(target):
    return {'target': target}
