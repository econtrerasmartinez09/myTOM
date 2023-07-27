from django import forms
from .models import QueryModel
from tom_targets.models import Target, TargetList


from crispy_forms.helper import FormHelper
from crispy_forms.layout import ButtonHolder, Column, Layout, Row, Submit

class QueryForm(forms.Form):
	mjd = forms.FloatField(label='MJD')